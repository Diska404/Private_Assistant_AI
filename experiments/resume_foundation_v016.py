"""Resume the actual interrupted fixture using persisted receipts; never replay its patch."""
import json
from pathlib import Path
import queue
import sys
import time
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from assistant_tools import AssistantTools
from terminal_service import TerminalService
from project_workspace import ProjectWorkspace
from file_workspace import FileWorkspace
from task_journal import TaskJournal
from agent_runtime import run_agent
from hybrid_engine import EngineError

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\agent-foundation-v016')
    before=json.loads((out/'local-fallback-interruption.json').read_text('utf-8'))['fixtures'][0]
    folder=Path(before['directory']);root=folder/'project';journal=TaskJournal(folder/'tasks.sqlite3')
    recovered=journal.recover_dead_owners();task=journal.get(before['tasks'][0][0]);source=(root/'calc.py').read_bytes()
    class Prefs:
        def get(self,key):return str(root) if key=='workspace_root' else False
        def set(self,*args):pass
    tools=AssistantTools.__new__(AssistantTools);tools.desktop=Mock(preferences=Prefs());tools.files=FileWorkspace(folder/'files');tools.projects=ProjectWorkspace(folder/'patches');tools._terminal=TerminalService(folder/'terminal');tools._continuation=task;tools._resume_goal=task['goal']
    prompt='Lanjut tugas '+task['id']+'. Patch sebelumnya sudah diterapkan sebelum gangguan. Jangan preview/apply patch lagi. Baca calc.py untuk mengamati keadaan terbaru, lalu jalankan terminal python code exec(open("test_calc.py").read()) dan poll process_id sampai exit code 0 dan TESTS PASSED.'
    commands=queue.Queue();calls=[]
    def emit(event):
        if event['name'] not in ('terminal','project_action','task_plan','list_tasks','resume_task'):raise ValueError('unexpected_recovery_probe_tool')
        result=tools.execute(event['name'],event['args'],prompt)
        calls.append({'name':event['name'],'action':event['args'].get('action'),'status':result.get('status'),'exit_code':result.get('exit_code'),'output':result.get('output','')[:200]})
        commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
    local=Mock();local.propose_tool.side_effect=EngineError('recovery_probe_does_not_load_gpu')
    start=time.perf_counter();proof={'scope':'actual interrupted fixture and persisted journal; real router decisions, no patch replay','dead_owner_recovered':recovered,'previous_task_status':task['status']}
    try:
        with patch('task_journal.TaskJournal',return_value=journal):
            result=run_agent({'id':1,'mode':'router','time_budget_seconds':90,'messages':[{'role':'user','content':prompt}],'tool_context':{'workspace_root':str(root),'continuation':task}},local,commands,emit)
        proof.update(provider=result.get('provider'),response=result.get('response'),incomplete=result.get('incomplete'))
    except Exception as error:proof['error']=str(error) if isinstance(error,EngineError) else type(error).__name__
    finally:tools._terminal.stop_all()
    proof.update(calls=calls,test_passed=any(r['exit_code']==0 and 'TESTS PASSED' in r['output'] for r in calls),source_preserved=(root/'calc.py').read_bytes()==source,patch_replayed=any(r['name']=='project_action' and r['action'] in ('preview','apply') for r in calls),elapsed_seconds=round(time.perf_counter()-start,3))
    (out/'real-router-recovery.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
