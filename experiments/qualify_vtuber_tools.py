"""Real agent core, synthetic browser/time, file IO restricted to this verification tree."""
import json
from pathlib import Path
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from hybrid_engine import LocalEngine
import benchmark_personal_models_v033 as fixtures
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
SERVER=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4\llama-server.exe')
def main():
 started=time.monotonic()
 while True:
  benchmark=json.loads((OUT/'benchmark-status.json').read_text('utf8'))
  if benchmark['status']=='completed':break
  if time.monotonic()-started>4200:raise TimeoutError('benchmark_wait_timeout')
  time.sleep(10)
 fixtures.OUT=OUT/'tool-fixtures';proof={'status':'running','models':[],'real_browser':False,'real_clock':False,'file_io':'verification tree only'}
 def save():(OUT/'tool-qualification.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
 for row in benchmark['models']:
  model={'id':row['id'],'cases':[],'status':'not_qualified'};proof['models'].append(model);save()
  if row['status']!='completed' or sum(v.get('passed',False) for v in row['native_tools'])!=2:
   model['reason']='native_proposal_gate_failed';save();continue
  engine=LocalEngine(SERVER,Path(row['source']['path']),OUT/(row['id']+'-harness'),mode='gpu5070',context_size=8192,
    max_output_tokens=2048,thinking_budget=0,startup_timeout=100,
    sampling={'temperature':.25,'top_p':.8,'top_k':20},extra_server_args=('--cache-type-k','q8_0','--cache-type-v','q8_0'))
  try:
   engine.start()
   for trial in range(3):
    for case in ('time','browsers','files'):
     start=time.perf_counter()
     try:result=fixtures.agent_case(engine,row['id'],case);result['passed']=all(result['checks'].values())
     except Exception as e:result={'passed':False,'error':type(e).__name__+': '+str(e)[:240]}
     model['cases'].append({'case':case,'trial':trial,'elapsed_ms':round((time.perf_counter()-start)*1000,2),**result});save()
   model['status']='fixture_gate_passed' if all(v['passed'] for v in model['cases']) else 'fixture_gate_failed'
   # Cancellation is limited to the child just created by this experiment.
   engine.max_output_tokens=4096;cancel_result={}
   def request():
    try:engine.generate([{'role':'user','content':'Tulis 200 paragraf cerita original tentang bintang.'}]);cancel_result['returned']=True
    except Exception as e:cancel_result['interrupted']=type(e).__name__
   worker=threading.Thread(target=request,daemon=True);worker.start();time.sleep(.35)
   start=time.perf_counter();engine.close();worker.join(5)
   model['cancel']={'owned_worker_released':engine.process is None,'request_thread_finished':not worker.is_alive(),'release_ms':round((time.perf_counter()-start)*1000,2),**cancel_result}
  except Exception as e:model['status']='error';model['error']=type(e).__name__+': '+str(e)[:240]
  finally:engine.close();model['owned_worker_released']=engine.process is None;save()
  print(json.dumps({'model':model['id'],'status':model['status'],'passed':sum(v['passed'] for v in model['cases'])}),flush=True)
 proof['status']='completed';save()
if __name__=='__main__':main()
