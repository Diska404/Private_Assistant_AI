"""Owned loopback audio.cpp server, one GPU/model at a time, offline inference."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

from paths import DATA
from speech_style import higgs_text

RUNTIME=DATA/'runtime/audio-cpp-higgs-v092'
MODELS=DATA.parent/'AI Models'
PACKS={
    'higgs_leva':('higgs_audio_tts',MODELS/'Higgs-TTS-3-GGUF/higgs-audio-v3-tts-4b-q8_0.gguf','cfa5cc01adcd199dfcf1baf0f610aa474cda83418fd1802aa6defa82d956a0e4',True),
    'higgs_native':('higgs_audio_tts',MODELS/'Higgs-TTS-3-GGUF/higgs-audio-v3-tts-4b-q8_0.gguf','cfa5cc01adcd199dfcf1baf0f610aa474cda83418fd1802aa6defa82d956a0e4',False),
    'higgs_jp_identity':('higgs_audio_tts',MODELS/'Higgs-TTS-3-GGUF/higgs-audio-v3-tts-4b-q8_0.gguf','cfa5cc01adcd199dfcf1baf0f610aa474cda83418fd1802aa6defa82d956a0e4',True),
    'omnivoice_leva':('omnivoice',MODELS/'OmniVoice-GGUF/omnivoice-q8_0.gguf','0e5a721edd1b08d9067ef66f40ded609a6b14f5a8445c703f9869736cabd350a',True),
    'omnivoice_native':('omnivoice',MODELS/'OmniVoice-GGUF/omnivoice-q8_0.gguf','0e5a721edd1b08d9067ef66f40ded609a6b14f5a8445c703f9869736cabd350a',False),
}

def available(pack):
    if pack=='higgs_jp_identity' and not (MODELS/'Leva-GFL2/Higgs-JP-native-reference-v1/profile.json').is_file():return False
    return pack in PACKS and PACKS[pack][1].is_file() and (RUNTIME/'audiocpp_server.exe').is_file() and (DATA/'verification/leva-bilingual-v3/proof.json').is_file()

def choose_gpu(rows,family,preference='auto'):
    capable=[r for r in rows if ('RTX 4050' in r['name'] or 'RTX 5070' in r['name'])]
    # Persistent Higgs sessions have less headroom than one-shot CLI on 6 GB.
    preferred='RTX 5070' if family=='higgs_audio_tts' else 'RTX 4050'
    # v0.36 measured selected Higgs Q8 at ~4.5 GiB incremental peak on 5070.
    # Retain 6 GiB free admission on 12 GiB hardware; 4050 is still unqualified.
    minimum=6000 if family=='higgs_audio_tts' else 2400
    if family=='higgs_audio_tts':capable=[r for r in capable if 'RTX 5070' in r['name']]
    if preference not in ('auto','rtx4050','rtx5070'):raise ValueError('invalid_speech_gpu')
    explicit={'rtx4050':'RTX 4050','rtx5070':'RTX 5070'}.get(preference)
    if explicit:capable=[r for r in capable if explicit in r['name']]
    ordered=sorted(capable,key=lambda r:(preferred not in r['name'],-r['free_mib']))
    for row in ordered:
        if row['free_mib']>=minimum:return row
    raise ValueError('voice_gpu_headroom_unavailable')

class AudioCppVoice:
    def __init__(self,pack,folder,gpu_preference='auto',streaming=False):
        self.streaming=streaming
        self.early_audio=False
        self.pack=pack;self.process=None;self.log=None;self.folder=Path(folder);self.gpu_preference=gpu_preference
        family,model,expected,self.clone=PACKS[pack]
        with model.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('voice_model_hash_mismatch')
        old=json.loads((DATA/'verification/leva-bilingual-v3/proof.json').read_text('utf-8'))
        self.reference=next(r for r in old['prompts'] if r['id']=='A')
        if pack=='higgs_jp_identity':self.reference=json.loads((MODELS/'Leva-GFL2/Higgs-JP-native-reference-v1/profile.json').read_text('utf-8'))
        if self.clone:
            with Path(self.reference['path']).open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.reference['sha256']:raise ValueError('voice_reference_hash_mismatch')
        listing=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.free','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000)
        rows=[]
        for line in listing.splitlines():
            uuid,name,free=[part.strip() for part in line.split(',')]
            rows.append({'uuid':uuid,'name':name,'free_mib':int(free)})
        self.gpu=choose_gpu(rows,family,gpu_preference)
        self.folder.mkdir(parents=True,exist_ok=True)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        self.base='http://127.0.0.1:'+str(port)
        entry={'id':'leva-voice','family':family,'path':str(model),'task':'tts','mode':'streaming' if streaming else 'offline'}
        if family=='higgs_audio_tts':entry['session_options']={'higgs_audio_tts.reference_prefill_mode':'exact'}
        if streaming:entry['session_options']['higgs_audio_tts.codec_decode_graph_arena_mb']=512
        config={'host':'127.0.0.1','port':port,'backend':'cuda','device':0,'threads':4,'lazy_load':True,
                'max_loaded_models':1,'idle_unload_ms':120000,'models':[entry]}
        config_path=self.folder/'audio-server.json';config_path.write_text(json.dumps(config),encoding='utf-8')
        env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=self.gpu['uuid'],OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
        self.log=(self.folder/'audio-server.log').open('w',encoding='utf-8')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.family=family
        self.process=subprocess.Popen([str(RUNTIME/'audiocpp_server.exe'),'--config',str(config_path),'--no-ui'],
            cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log,creationflags=0x08000000)
        try:
            until=time.monotonic()+25
            while time.monotonic()<until:
                if self.process.poll() is not None:raise RuntimeError('voice_server_exited')
                try:
                    with self.opener.open(self.base+'/health',timeout=1) as response:
                        if response.status==200:return
                except (OSError,urllib.error.URLError):time.sleep(.15)
            raise RuntimeError('voice_server_start_timeout')
        except BaseException:self.close();raise

    def synthesize(self,text,output,language,style,emit=None):
        options={'seed':20261020,'text_chunk_size':160 if language=='ja' else 480,
                 'text_chunk_mode':'japanese' if language=='ja' else 'default'}
        if self.family=='higgs_audio_tts':options['max_tokens']=1800;spoken=higgs_text(text,style)
        else:
            spoken=text;options.update(language=language,num_inference_steps=32)
            # Upstream OmniVoice does not accept Higgs emotion tokens.
        body={'model':'leva-voice','input':spoken,'response_format':'wav','options':options}
        if self.streaming:
            body.update(response_format='pcm',stream_format='sse')
            options.update(stream_frames_per_event=8,stream_chunk_policy='grow' if self.early_audio else 'fixed')
        if self.clone:body.update(voice_ref=self.reference['path'],reference_text=self.reference['text'])
        start=time.perf_counter()
        request=urllib.request.Request(self.base+'/v1/audio/speech',data=json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
        if self.streaming:
            from speech_stream import receive_pcm
            with self.opener.open(request,timeout=150) as response:stream_info=receive_pcm(response,output,emit,first_chunk_ms=160 if self.early_audio else 640)
        else:
            with self.opener.open(request,timeout=150) as response:audio=response.read(12*1024*1024+1)
            if len(audio)>12*1024*1024 or not audio.startswith(b'RIFF'):raise ValueError('invalid_voice_server_audio')
            Path(output).write_bytes(audio)
            stream_info={}
        return {'backend':'audio.cpp · '+self.family+' · Q8 · '+self.gpu['name'],'voice_style':style,
                'style_control_applied':self.family=='higgs_audio_tts','engine_request_seconds':round(time.perf_counter()-start,4),
                'reference_conditioned':self.clone,'streaming':self.streaming,'gpu_name':self.gpu['name'],**stream_info}

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=4)
        if self.log:self.log.close();self.log=None

def synthesize(pack,text,output,language,style,cache=None,gpu_preference='auto',emit=None,early_audio=False):
    own=cache is None;cache={} if own else cache
    engine=cache.get('audio_cpp')
    streaming=emit is not None and pack.startswith('higgs_')
    if engine is None or engine.pack!=pack or engine.gpu_preference!=gpu_preference or engine.streaming!=streaming:
        if engine:engine.close()
        # The server config/log must outlive a transient preview directory.
        import tempfile
        folder=Path(tempfile.mkdtemp(prefix='audio-cpp-',dir=DATA/'tmp'))
        try:engine=AudioCppVoice(pack,folder,gpu_preference,streaming=streaming)
        except BaseException:raise
        cache['audio_cpp']=engine
    engine.early_audio=early_audio is True
    try:return engine.synthesize(text,output,language,style,emit)
    finally:
        if own:engine.close()
