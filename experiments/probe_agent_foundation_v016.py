"""Real selected router -> project patch -> owned Python tests in a temporary workspace."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from assistant_tools import AssistantTools
from terminal_service import TerminalService
from project_workspace import ProjectWorkspace
from file_workspace import FileWorkspace
from workflow_skills import WorkflowSkills
from task_journal import TaskJournal
from agent_runtime import run_agent
from hybrid_engine import EngineError
from router_provider import RouterClient

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\agent-foundation-v016');out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='leva-foundation-') as folder:
        root=Path(folder)/'project';root.mkdir();(root/'calc.py').write_text('def add(a, b):\n    return a - b\n',encoding='utf-8')
        (root/'test_calc.py').write_text('from calc import add\nassert add(2, 3) == 5, "addition failed"\nprint("TESTS PASSED")\n',encoding='utf-8')
        class Prefs:
            def get(self,key):return str(root) if key=='workspace_root' else False
            def set(self,*args):pass
        tools=AssistantTools.__new__(AssistantTools);tools.desktop=Mock(preferences=Prefs());tools.files=FileWorkspace(Path(folder)/'files')
        tools.projects=ProjectWorkspace(Path(folder)/'patches');tools._terminal=TerminalService(Path(folder)/'terminal');tools.workflows=WorkflowSkills();tools._continuation=None
        prompt='Perbaiki proyek Python di '+str(root)+'. Jalankan test_calc.py lebih dulu menggunakan terminal python dengan code exec(open("test_calc.py").read()). Baca hasil gagal, cari bug di calc.py, gunakan project_action read/preview/apply untuk memperbaiki penjumlahan, lalu jalankan perintah tes yang sama lagi dan periksa exit code 0 serta TESTS PASSED. Jangan ubah test_calc.py.'
        commands=queue.Queue();calls=[];failures=[]
        def emit(event):
            if event['name'] not in ('terminal','project_action','task_plan','list_workflows','use_workflow','discover_tools'):raise ValueError('unexpected_probe_tool')
            result=tools.execute(event['name'],event['args'],prompt)
            calls.append({'name':event['name'],'action':event['args'].get('action'),'status':result.get('status'),'code':result.get('code'),'process_id':result.get('process_id') or event['args'].get('process_id'),'exit_code':result.get('exit_code'),'output':result.get('output','')[:150]})
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        if '--allow-local-fallback' in sys.argv:
            from chat_service import make_local
            local=make_local({'local_model':'qwen4b','local_mode':'gpu4050'})
        else:
            local=Mock();local.propose_tool.side_effect=EngineError('probe_does_not_load_local_gpu_model')
        original=RouterClient.propose_tool
        def record_failure(client,*args,**kwargs):
            try:return original(client,*args,**kwargs)
            except EngineError as error:failures.append(str(error));raise
        journal=TaskJournal(Path(folder)/'tasks.sqlite3');start=time.perf_counter();proof={'scope':'real 9Router, real temporary project and owned Python processes; no personal project modified'}
        try:
            with patch('task_journal.TaskJournal',return_value=journal),patch.object(RouterClient,'propose_tool',record_failure):
                result=run_agent({'id':1,'mode':'router','messages':[{'role':'user','content':prompt}],'tool_context':{'workspace_root':str(root)}},local,commands,emit)
            proof.update(provider=result.get('provider'),response=result.get('response'),incomplete=result.get('incomplete',False))
        except Exception as error:proof.update(error=str(error) if isinstance(error,EngineError) else type(error).__name__)
        finally:tools._terminal.stop_all();local.close()
        proof.update(calls=calls,router_failures=failures,final_source=(root/'calc.py').read_text('utf-8'),initial_test_failed=any(r['exit_code'] not in (None,0) for r in calls),final_test_passed=any(r['exit_code']==0 and 'TESTS PASSED' in r['output'] for r in calls),test_unchanged=(root/'test_calc.py').read_text('utf-8').startswith('from calc import add\nassert add(2, 3) == 5'),elapsed_seconds=round(time.perf_counter()-start,3))
        (out/'real-router-project.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
