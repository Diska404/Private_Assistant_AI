"""Selected Higgs reference, early PCM vs old buffer; optional real LLM co-residency."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from audio_cpp_voice import AudioCppVoice
from chat_service import make_local
from benchmark_personal_models_v033 import Monitor
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\realtime-voice-avatar-20261025')
def main():
 proof={'status':'running','runs':[],'speaker_opened':False,'microphone_opened':False,'voice':'higgs_leva','changed_voice_identity':False,
   'llm':'Qwen3.5 4B existing D; Hauhau files on Y unavailable on 25 October'}
 def save():(OUT/'early-pcm.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
 llm=None;voice=None;monitor=Monitor();monitor.start()
 try:
  llm=make_local({'local_model':'qwen4b','local_mode':'gpu5070','purpose':'room_companion_avatar'})
  llm.data_dir=OUT/'coexist-llm';llm.start();proof['llm_buffers_mib']=llm.model_gpu_buffers_mib
  voice=AudioCppVoice('higgs_leva',OUT/'early-sse','rtx5070',streaming=True);voice.early_audio=True
  for i in range(10):
   row={'trial':i};proof['runs'].append(row);start=time.perf_counter();first=[];events=[];reply={}
   def generate():
    try:reply['text']=llm.generate([{'role':'user','content':'Balas singkat satu kalimat, beri semangat belajar.'}])
    except Exception as e:reply['error']=type(e).__name__
   thread=threading.Thread(target=generate,daemon=True);thread.start()
   row['gpu_before']=subprocess.check_output(['nvidia-smi','--query-gpu=name,clocks.sm,pstate,memory.used','--format=csv,noheader'],text=True,creationflags=0x08000000).splitlines()
   def emit(e):
    if not first:first.append(time.perf_counter()-start)
    events.append({'sequence':e['sequence'],'at_s':time.perf_counter()-start})
   result=voice.synthesize('レヴァだよ。いつでも手伝うよ。' if i%2==0 else '今日もお疲れさま。一緒に少し休もう。',OUT/('early-'+str(i)+'.wav'),'ja','assistant',emit)
   thread.join(10);row.update(result=result,first_pcm_s=first[0] if first else None,total_s=time.perf_counter()-start,events=events,llm=reply);save()
  proof['status']='completed'
 except Exception as e:proof['status']='failed';proof['error']=type(e).__name__+': '+str(e)[:300]
 finally:
  if voice:voice.close()
  if llm:llm.close()
  monitor.close();proof['resources']=monitor.rows;proof['owned_workers_released']=True;save()
 print(json.dumps({'status':proof['status'],'runs':len(proof['runs']),'error':proof.get('error')}))
if __name__=='__main__':main()
