"""Opt-in real 9Router inference with a benign host clock tool; never logs keys."""
from datetime import datetime
import json
from pathlib import Path
import sys
import time
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from chat_service import ChatService
from command_resolution import WIB
from paths import DATA


def main():
    if '--run-live' not in sys.argv:raise SystemExit('Pass --run-live to send the synthetic clock prompt to the configured gateway.')
    model=sys.argv[sys.argv.index('--model')+1]
    exe=sys.argv[sys.argv.index('--exe')+1]
    service=ChatService([exe,'--chat-session-worker'],persistent=True)
    service.online_paused=True  # Simulate Google quota pause; no Google API call.
    calls=[]
    def host(name,args,authorized):
        if not authorized() or name!='get_time' or args!={}:raise ValueError('Only the benign clock tool is allowed by this probe')
        calls.append(name)
        return {'status':'done','reply':'Waktu komputer '+datetime.now(WIB).strftime('%H.%M')+' WIB.','source':'system_clock'}
    proof={'model':model,'packaged':True,'google_quota_simulated':True,'real_router_request':True}
    started=time.monotonic()
    try:
        r=service.ask('Jam berapa sekarang? Gunakan get_time lalu jawab satu kalimat dalam bahasa Indonesia.',
                      'cascade',local_model='saluki',keep_warm=False,tool_executor=host,
                      router_config={'url':'http://127.0.0.1:20128/v1','model':model})
        proof.update(provider=r.get('provider'),response=r.get('response'),seconds=round(time.monotonic()-started,3),
                     host_calls=calls,google_paused=r.get('google_paused'),provider_failures=r.get('provider_failures'),
                     incomplete=bool(r.get('incomplete')))
        proof['passed']=r.get('provider')=='9router' and calls==['get_time'] and not r.get('incomplete')
    except Exception as e:
        from hybrid_engine import EngineError
        proof.update(passed=False,error=str(e) if isinstance(e,EngineError) else type(e).__name__)
    finally:
        service.cancel();proof['worker_released']=service.process is None
        out=DATA/'verification/9router-v013/live-provider-20261020';out.mkdir(parents=True,exist_ok=True)
        (out/'packaged-live-proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True))
    return 0 if proof['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
