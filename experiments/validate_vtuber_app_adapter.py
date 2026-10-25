"""Use the actual app adapter/persona after baseline/tools have released their workers."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from chat_service import make_local,run_worker
from model_registry import TRIALS
from benchmark_vtuber_models import stream
from summarize_vtuber_trial import stats
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
def main():
 start=time.monotonic()
 while True:
  path=OUT/'tool-qualification.json'
  if path.is_file() and json.loads(path.read_text('utf8')).get('status')=='completed':break
  if time.monotonic()-start>3600:raise TimeoutError('fixture_wait_timeout')
  time.sleep(5)
 proof={'status':'running','models':[],'gpu_smoke':[],'production_preferences_changed':False}
 def save():(OUT/'app-adapter.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf8')
 for key in TRIALS:
  request={'mode':'local','local_mode':'gpu5070','local_model':key,'purpose':'room_companion_avatar'}
  row={'id':key,'turns':[]};proof['models'].append(row);engine=None
  try:
   engine=make_local(request);engine.data_dir=OUT/(key+'-app-adapter');history=[]
   prompts=['Siapa namamu? Jawab satu kalimat.','Untuk fixture saja, ingat kode proyek KUPU-24. Jawab singkat.',
     'Aku capek setelah belajar. Temani sebentar, tanpa daftar nasihat.',
     'Apa kode proyek fixture yang tadi kusebut? Jawab tepat kodenya saja.',
     'Jangan jalankan apa pun. Apakah kamu bisa memakai tools di ruang companion ini? Jawab singkat.']
   for prompt in prompts:
    history.append({'role':'user','content':prompt});start=time.perf_counter()
    result=run_worker({**request,'messages':history},engine,False)
    row['turns'].append({'prompt':prompt,'text':result['response'],'model_registry':result.get('model_registry'),'elapsed_ms':round((time.perf_counter()-start)*1000,2)})
    history.append({'role':'assistant','content':result['response']});save()
   row['passed']=bool('leva' in row['turns'][0]['text'].casefold() and 'KUPU-24' in row['turns'][3]['text'])
  except Exception as e:row.update(passed=False,error=type(e).__name__+': '+str(e)[:220])
  finally:
   if engine:engine.close()
   row['owned_worker_released']=not engine or engine.process is None;save()
 # Same 20 prompts after warmup on each hardware route, no TTS/avatar/game load.
 for mode in ('gpu4050','gpu5070','dual'):
  engine=None;row={'mode':mode,'samples':[]};proof['gpu_smoke'].append(row)
  try:
   engine=make_local({'local_model':'hauhau_qwen35_4b','local_mode':mode,'purpose':'room_companion_avatar'})
   engine.data_dir=OUT/('4b-'+mode+'-smoke');engine.start()
   stream(engine,[{'role':'user','content':'Jawab tepat: siap.'}],'companion_avatar',max_tokens=64)
   for i in range(20):
    result=stream(engine,[{'role':'user','content':'Berikan satu kalimat penyemangat singkat untuk belajar, maksimal 15 kata.'}],'companion_avatar',max_tokens=64)
    row['samples'].append(result)
   row.update(devices=engine.devices,gpu_buffers_mib=engine.model_gpu_buffers_mib,load_seconds=engine.load_seconds,
      ttft_ms=stats(r['ttft_ms'] for r in row['samples']),total_ms=stats(r['total_ms'] for r in row['samples']),
      tokens_per_second=stats(r['timings'].get('predicted_per_second') for r in row['samples']))
  except Exception as e:row['error']=type(e).__name__+': '+str(e)[:220]
  finally:
   if engine:engine.close()
   row['owned_worker_released']=not engine or engine.process is None;save()
 proof['status']='completed';save();print(json.dumps({'status':'completed','app':[{'id':m['id'],'passed':m['passed']} for m in proof['models']]}))
if __name__=='__main__':main()
