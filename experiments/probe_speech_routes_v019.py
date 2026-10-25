"""Owned local inference only: no microphone, playback, user apps or network."""
import json
from pathlib import Path
import sys
import time
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from chat_service import make_local,run_worker
from conversation_frontend import parse_frontend
from pipeline_routing import route_spec
from paths import DATA

root=DATA/'verification/speech-v019';root.mkdir(parents=True,exist_ok=True)
proof={'microphone_opened':False,'playback':False,'network':False,'routes':[]}
for label in ('RTX 4050','RTX 5070','Dual GPU'):
    spec=route_spec(label)
    request={'messages':[{'role':'user','content':'Hai Leva. Jawab singkat bahwa kamu siap membantu.'}],
        'mode':spec['mode'],'local_mode':spec['local_mode'],'local_model':'minicpm2b','purpose':'frontend','speech_language':'id'}
    local=make_local(request)
    try:
        started=time.monotonic();result=run_worker(request,local,False)
        elapsed=round(time.monotonic()-started,3)
        began=time.monotonic();warm=run_worker(request,local,False)
        row={'route':label,'local_mode':spec['local_mode'],'devices':local.devices,
             'elapsed_seconds':elapsed,'warm_seconds':round(time.monotonic()-began,3),'warm_result':warm,'result':result,
             'gpu_before':local.gpu_snapshot_before,'gpu_loaded':local.gpu_snapshot_loaded,
             'parsed':parse_frontend(result,request['messages'][0]['content']),
             'gpu_allocations':local.process_gpu_allocations(),'folder':str(local.data_dir)}
        proof['routes'].append(row)
    except Exception as error:
        proof['routes'].append({'route':label,'error':type(error).__name__+': '+str(error)})
    finally:local.close()
    (root/'local-route-proof-warm.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof['routes'][-1],ensure_ascii=True),flush=True)
