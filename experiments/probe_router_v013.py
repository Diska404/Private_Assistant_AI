"""Gateway protocol fixture + actual unauthenticated 9Router -> local fallback.
No browser/desktop actions. A fixture response is never a cloud-model proof.
"""
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from chat_service import ChatService
from command_resolution import WIB
from paths import DATA
from router_provider import KEY_FILE

calls=[];clock=''
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(payload)
        action='get_time' if len(calls)==1 else 'respond'
        args={} if action=='get_time' else {'text':clock,'speech_text':clock}
        result={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':action,'arguments':json.dumps(args)}}]}}]}
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())

def host(name,args,authorized):
    global clock
    assert authorized() and name=='get_time' and args=={}
    clock='Waktu komputer '+datetime.now(WIB).strftime('%H.%M')+' WIB.'
    return {'status':'done','reply':clock,'source':'system_clock'}

server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
command=[sys.argv[sys.argv.index('--exe')+1],'--chat-session-worker'] if '--exe' in sys.argv else None
service=ChatService(command,persistent=True);chain='--chain' in sys.argv
if chain:service.online_paused=True
proof={'packaged':command is not None,'cloud_model_inference_verified':False,'desktop_actions':False,'mode':'cascade' if chain else 'router','google_quota_simulated':chain}
out=DATA/'verification/9router-v013';out.mkdir(parents=True,exist_ok=True)
try:
    start=time.monotonic()
    result=service.ask('Jam berapa sekarang? Gunakan jam komputer.','cascade' if chain else 'router',local_model='saluki',keep_warm=True,tool_executor=host,router_config={'url':'http://127.0.0.1:'+str(server.server_port)+'/v1','model':'fixture/free'})
    assert result['provider']=='9router' and len(calls)==2 and result['response']==clock
    proof['protocol_fixture']={'status':'passed','seconds':round(time.monotonic()-start,3),'result':result,'http_calls':len(calls),'model':'fixture only'}
    service.cancel();service.history=[]
    status=None
    try:
        with urllib.request.urlopen('http://127.0.0.1:20128/v1/models',timeout=5) as r:status=r.status
    except urllib.error.HTTPError as error:status=error.code;error.close()
    except OSError:pass
    proof['actual_gateway_models_http']=status
    if status==401 and not KEY_FILE.exists():
        start=time.monotonic()
        result=service.ask('Jam berapa sekarang? Gunakan get_time lalu jawab satu kalimat.','cascade' if chain else 'router',local_model='saluki',keep_warm=False,tool_executor=host,router_config={'url':'http://127.0.0.1:20128/v1','model':'__leva_unconfigured_probe__'})
        assert result['provider']=='local' and result['fallback_reason']=='router_authentication'
        assert any(r['name']=='get_time' for r in result.get('tool_receipts',[]))
        proof['actual_auth_fallback']={'status':'passed','seconds':round(time.monotonic()-start,3),'result':result}
    else:proof['actual_auth_fallback']={'status':'not_run','reason':'Gateway authentication condition changed; no upstream model was selected automatically.'}
    proof['status']='passed'
except Exception as error:proof.update(status='failed',error=str(error))
finally:
    service.cancel();server.shutdown();server.server_close();thread.join();proof['worker_released']=service.process is None
    (out/(('chain-' if chain else '')+('packaged-proof.json' if command else 'source-proof.json'))).write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=True))
if proof['status']!='passed':sys.exit(1)
