"""Probe the installed audio.cpp binary's SSE contract, never open audio devices."""
import sys,json,time,os,subprocess,urllib.request,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from audio_cpp_voice import AudioCppVoice,RUNTIME
from paths import DATA
OUT=DATA/'verification/visual-voice-v027';folder=OUT/'stream-probe';folder.mkdir(parents=True,exist_ok=True)
engine=None;report={'microphone_opened':False,'speaker_opened':False,'events':[]}
try:
 engine=AudioCppVoice('higgs_leva',folder,'rtx5070');engine.close()
 config_path=folder/'audio-server.json';config=json.loads(config_path.read_text('utf8'));config['models'][0]['mode']='streaming';config['models'][0]['session_options']['higgs_audio_tts.codec_decode_graph_arena_mb']=512;config_path.write_text(json.dumps(config),encoding='utf8')
 env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=engine.gpu['uuid'],OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
 engine.log=(folder/'stream-server.log').open('w',encoding='utf8')
 engine.process=subprocess.Popen([str(RUNTIME/'audiocpp_server.exe'),'--config',str(config_path),'--no-ui'],cwd=RUNTIME,env=env,stdin=subprocess.DEVNULL,stdout=engine.log,stderr=engine.log,creationflags=0x08000000)
 until=time.monotonic()+25
 while time.monotonic()<until:
  if engine.process.poll() is not None:raise RuntimeError('installed_server_streaming_config_rejected')
  try:
   with engine.opener.open(engine.base+'/health',timeout=1) as r:
    if r.status==200:break
  except OSError:time.sleep(.1)
 body={'model':'leva-voice','input':'お帰りなさい。今日も一緒に予定を確認しましょう。','response_format':'pcm','stream_format':'sse','voice_ref':engine.reference['path'],'reference_text':engine.reference['text'],'options':{'seed':20261020,'max_tokens':1800,'stream_frames_per_event':8,'stream_chunk_policy':'fixed'}}
 began=time.monotonic();request=urllib.request.Request(engine.base+'/v1/audio/speech',data=json.dumps(body,ensure_ascii=False).encode('utf8'),headers={'Content-Type':'application/json'})
 with engine.opener.open(request,timeout=150) as response:
  report['content_type']=response.headers.get('Content-Type');event=''
  for line in response:
   if line.startswith(b'event:'):event=line[6:].decode().strip()
   elif line.startswith(b'data:'):
    row=json.loads(line[5:]);report['events'].append({'event':event,'keys':list(row),'at_s':time.monotonic()-began,'fields':{k:v for k,v in row.items() if not isinstance(v,str) or len(v)<150}})
    if len(report['events'])>100:raise ValueError('stream_probe_event_limit')
 report['supported']=any('delta' in e['fields'].get('type','') for e in report['events']) and any('done' in e['fields'].get('type','') for e in report['events']);report['wall_s']=time.monotonic()-began
except Exception as error:
 report['error_type']=type(error).__name__;report['error']=str(error)[:200];report['supported']=False
 if hasattr(error,'read'):report['server_error']=error.read(2500).decode('utf8','replace')
finally:
 if engine:engine.close()
 (OUT/'stream-probe.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
