"""Owned ASR-only worker; existing assistant tools and microphone are never imported."""
import contextlib
import json
from pathlib import Path
import queue
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))

BASE=Path('D:/AI/AI Lokal Asisten/Leva/evaluation/asr-lab/audio').resolve()

def transcribe(request,engine,phase):
    started=time.perf_counter()
    path=Path(request['path']).resolve()
    if not path.is_relative_to(BASE) or path.suffix.lower()!='.wav' or not path.is_file() or path.stat().st_size>12*1024*1024:
        raise ValueError('invalid_lab_audio')
    import soundfile as sf
    from scipy.signal import resample_poly
    from math import gcd
    import numpy as np
    samples,rate=sf.read(path,dtype='float32')
    if samples.ndim==2:samples=samples.mean(axis=1)
    if not 8000<=rate<=96000 or not .2<=len(samples)/rate<=45 or not np.isfinite(samples).all():raise ValueError('invalid_audio_duration_or_samples')
    duration=len(samples)/rate
    audio={'duration_seconds':round(duration,4),'sample_rate':rate,'samples':len(samples),
        'peak':float(np.max(np.abs(samples))),'rms_dbfs':round(20*float(np.log10(max(1e-9,float(np.sqrt(np.mean(samples*samples)))))),2),
        'clipped_fraction':float(np.mean(np.abs(samples)>=.999)), 'bytes':path.stat().st_size}
    if rate!=16000:
        common=gcd(rate,16000);samples=resample_poly(samples,16000//common,rate//common)
    from local_audio_core import Segmenter
    segmenter=Segmenter();complete=0;voiced_frames=0
    for start in range(0,len(samples)-319,320):
        frame=samples[start:start+320];rms=float(np.sqrt(np.mean(frame*frame)))
        emitted,_,voiced=segmenter.push((np.clip(frame,-1,1)*32767).astype(np.int16).tobytes(),rms,awake=True)
        complete+=emitted is not None;voiced_frames+=voiced
    audio['app_vad_simulation']={'voiced_ms':voiced_frames*20,'completed_segments':complete,
        'buffered_frames_at_manual_stop':len(segmenter.frames),'minimum_rms':.009,
        'end_silence_ms':560,'simulation_only':True,
        'note':'Simulasi segmenter lokal dari WAV, tanpa referensi gema. Lab tetap mentranskripsikan seluruh rekaman manual.'}
    preprocess_ms=round((time.perf_counter()-started)*1000,2)
    import torch
    for i in range(len(engine.devices)):
        torch.cuda.synchronize(i);torch.cuda.reset_peak_memory_stats(i)
    phase('inference')
    result=engine.transcribe(samples,request.get('language','id'),request.get('context',''))
    for i in range(len(engine.devices)):torch.cuda.synchronize(i)
    device_memory=[{'uuid':d['uuid'],'name':d['name'],'peak_allocated_mib':round(torch.cuda.max_memory_allocated(i)/2**20,2),
        'peak_reserved_mib':round(torch.cuda.max_memory_reserved(i)/2**20,2),
        'allocated_after_mib':round(torch.cuda.memory_allocated(i)/2**20,2)} for i,d in enumerate(engine.devices)]
    return {**result,'audio':audio,'preprocess_ms':preprocess_ms,
        'real_time_factor':round(result['asr_ms']/1000/duration,4),
        'torch_peak_allocated_mib':sum(d['peak_allocated_mib'] for d in device_memory),
        'torch_peak_reserved_mib':sum(d['peak_reserved_mib'] for d in device_memory),
        'torch_allocated_after_mib':sum(d['allocated_after_mib'] for d in device_memory),
        'torch_device_memory':device_memory,
        'dtype':'float16','attention':'sdpa','cpu_threads':4,'batch_size':1,'max_new_tokens':256,
        'gpu_uuid':engine.gpu['uuid'],'microphone_opened':False,'agent_called':False,'confidence_available':False}

def main():
    protocol=sys.stdout;commands=queue.Queue();ready=threading.Event()
    def reader():
        while True:
            ready.wait();ready.clear();line=sys.stdin.readline()
            if not line:commands.put({'cmd':'stop'});return
            try:commands.put(json.loads(line))
            except ValueError:commands.put({'cmd':'stop'})
    threading.Thread(target=reader,daemon=True).start()
    engine=None
    while True:
        ready.set()
        try:request=commands.get(timeout=180)
        except queue.Empty:return
        if request.get('cmd')=='stop':return
        started=time.perf_counter();reused=engine is not None
        def phase(name):
            protocol.write(json.dumps({'id':request['id'],'phase':name})+'\n');protocol.flush()
        try:
            with contextlib.redirect_stdout(sys.stderr):
                init_ms=0
                if engine is None:
                    phase('model_load')
                    before=time.perf_counter()
                    from speech_asr import SpeechASR
                    engine=SpeechASR('qwen_asr_06b',request['gpu'])
                    init_ms=round((time.perf_counter()-before)*1000,2)
                phase('preprocess');result=transcribe(request,engine,phase)
                import importlib.metadata as meta
                result['runtime']={p:meta.version(p) for p in ('torch','qwen-asr','transformers','numpy')}
                from speech_asr import MODEL_PATHS
                import hashlib
                manifest=(MODEL_PATHS['qwen_asr_06b']/'leva-download-proof.json').read_bytes()
                result['model_provenance']={'revision':json.loads(manifest)['revision'],
                    'download_manifest_sha256':hashlib.sha256(manifest).hexdigest(),
                    'note':'Manifest unduhan yang sebelumnya diverifikasi; seluruh bobot tidak dihash ulang pada setiap uji.'}
            row={'ok':True,'id':request['id'],**result,'model_reused':reused,'model_init_total_ms':init_ms,
                 'weights_load_ms':engine.load_ms if not reused else 0,'worker_request_ms':round((time.perf_counter()-started)*1000,2)}
        except Exception as error:
            row={'ok':False,'id':request.get('id'),'error':type(error).__name__+': '+str(error)[:400]}
        protocol.write(json.dumps(row,ensure_ascii=True)+'\n');protocol.flush()

if __name__=='__main__':main()
