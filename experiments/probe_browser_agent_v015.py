"""Real router model operating the actual DOM backend on an owned local fixture."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from unittest.mock import Mock,patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from probe_remote_v015 import Handler
from browser_runtime import BrowserRuntime
from assistant_tools import AssistantTools
from agent_runtime import run_agent
from task_journal import TaskJournal
from hybrid_engine import EngineError
from router_provider import RouterClient

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\remote-v015');out.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='leva-browser-agent-') as folder:
        runtime=BrowserRuntime(headless=True,profile=Path(folder)/'edge')
        tools=AssistantTools.__new__(AssistantTools);tools.allowed_web_urls=set()
        class Bridge:
            def run(self,name,args,authorized,timeout):return runtime.run(args)
        tools._bridge=Bridge()
        prompt=f'Buka halaman web http://127.0.0.1:{server.server_port}/ dalam browser terkelola. Isi kolom Name dengan Leva agent test, klik tombol Save local preview, lalu periksa bahwa halaman menampilkan Saved Leva agent test. Gunakan browser_action saja. Jangan menekan Submit external atau memakai browser pribadi.'
        commands=queue.Queue();calls=[]
        def emit(event):
            if event['name']!='browser_action':raise ValueError('unexpected_tool_for_browser_fixture')
            result=tools.execute(event['name'],event['args'],prompt)
            calls.append({'name':event['name'],'action':event['args'].get('action'),'url':event['args'].get('url'),'status':result.get('status'),'code':result.get('code')})
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        local=Mock();local.propose_tool.side_effect=EngineError('router_probe_does_not_load_local_model')
        start=time.perf_counter();proof={'scope':'real 9Router inference -> actual browser DOM backend -> owned headless Edge, loopback-only fixture'}
        failures=[];original=RouterClient.propose_tool
        def observed_call(client,*args,**kwargs):
            try:return original(client,*args,**kwargs)
            except EngineError as error:failures.append(str(error));raise
        try:
            with patch('task_journal.TaskJournal',side_effect=lambda:TaskJournal(Path(folder)/'tasks.sqlite3')),patch.object(RouterClient,'propose_tool',observed_call):
                result=run_agent({'id':1,'mode':'router','messages':[{'role':'user','content':prompt}]},local,commands,emit)
            verified=any(r['name']=='browser_action' and r['args'].get('action')=='inspect' and 'Saved Leva agent test' in r['result'].get('content','') for r in result.get('tool_receipts',[]))
            proof.update(provider=result.get('provider'),calls=calls,result_verified=verified,reply=result.get('response'),incomplete=result.get('incomplete',False))
        except Exception as error:proof.update(status='failed',error=str(error) if isinstance(error,EngineError) else type(error).__name__,calls=calls)
        finally:runtime.stop();server.shutdown();server.server_close()
        proof['elapsed_seconds']=round(time.perf_counter()-start,3)
        proof['router_failures']=failures
        (out/'browser-real-router.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(proof,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
