"""Profile the installed Higgs voice, without microphone/speakers or production changes."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from audio_cpp_voice import AudioCppVoice
from benchmark_personal_models_v033 import Monitor
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\realtime-voice-avatar-20261025')
def main():
 OUT.mkdir(parents=True,exist_ok=True);proof={'status':'running','voice_pack':'higgs_leva','speaker_opened':False,'microphone_opened':False,'runs':[]}
 def save():(OUT/'higgs-baseline.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
 for streaming in (False,True):
  engine=None;monitor=Monitor();monitor.start();mode='sse' if streaming else 'sentence';start=time.perf_counter()
  try:
   engine=AudioCppVoice('higgs_leva',OUT/mode,'rtx5070',streaming=streaming)
   initialization=time.perf_counter()-start
   for i,text in enumerate(['レヴァだよ。いつでも手伝うよ。','今日もお疲れさま。少し休んでから、一緒に予定を確認しよう。','レヴァだよ。いつでも手伝うよ。']):
    row={'mode':mode,'trial':i,'text':text,'initialization_s':initialization};proof['runs'].append(row);save();events=[];first=[None];start=time.perf_counter()
    def emit(event):
     if first[0] is None:first[0]=time.perf_counter()-start
     events.append({'kind':event['kind'],'at_s':time.perf_counter()-start,'sequence':event.get('sequence')})
    result=engine.synthesize(text,OUT/(mode+'-'+str(i)+'.wav'),'ja','assistant',emit if streaming else None)
    row.update(result=result,total_s=time.perf_counter()-start,first_pcm_s=first[0],events=events);save()
   proof['runs'][-1]['gpu']=engine.gpu
  except Exception as e:proof.setdefault('errors',[]).append({'mode':mode,'type':type(e).__name__,'error':str(e)[:300]})
  finally:
   if engine:engine.close()
   monitor.close();proof.setdefault('resources',{})[mode]=monitor.rows;save()
 proof['status']='completed';save();print(json.dumps({'status':'completed','runs':len(proof['runs']),'errors':proof.get('errors',[])}))
if __name__=='__main__':main()
