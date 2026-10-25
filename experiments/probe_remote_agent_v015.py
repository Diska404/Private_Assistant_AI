"""Real selected 9Router model -> Leva tools -> temporary file -> re-read verification."""
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from assistant_tools import AssistantTools
from file_workspace import FileWorkspace
from workflow_skills import WorkflowSkills
from agent_runtime import run_agent
from task_journal import TaskJournal
from hybrid_engine import EngineError

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\remote-v015');out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='leva-agent-v015-') as folder:
        root=Path(folder);target=root/'memo.txt'
        tools=AssistantTools.__new__(AssistantTools);tools.files=FileWorkspace(root/'history');tools.workflows=WorkflowSkills()
        prompt='Buat file teks di '+str(target)+'. Tulis persis "Belajar matematika diskrit pukul 19:00 WIB." lalu baca kembali file itu untuk memeriksa isi. Gunakan file_action, jangan aplikasi desktop atau shell.'
        commands=queue.Queue();calls=[]
        def emit(event):
            if event['name'] not in ('file_action','list_workflows','use_workflow','discover_tools'):raise ValueError('unexpected_tool_in_fixture_probe')
            result=tools.execute(event['name'],event['args'],prompt)
            calls.append({'name':event['name'],'action':event['args'].get('action'),'status':result.get('status')})
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        local=Mock();local.propose_tool.side_effect=EngineError('router_probe_does_not_load_local_model')
        start=time.perf_counter();proof={'scope':'real configured 9Router inference; host file operations in temporary directory; no local LLM loaded'}
        try:
            with patch('task_journal.TaskJournal',side_effect=lambda:TaskJournal(root/'tasks.sqlite3')):
                result=run_agent({'id':1,'mode':'router','speech_language':'id','messages':[{'role':'user','content':prompt}],'tool_context':{'workflow_guidance':tools.workflows.relevant(prompt)}},local,commands,emit)
            proof.update(provider=result.get('provider'),calls=calls,reply=result.get('response'),file_content_matches=target.is_file() and target.read_text('utf-8')=='Belajar matematika diskrit pukul 19:00 WIB.',read_receipt=any(r['name']=='file_action' and r['args'].get('action')=='read' and r['result'].get('status')=='done' for r in result.get('tool_receipts',[])),local_model_loaded=False)
        except Exception as error:proof.update(status='failed',error=str(error) if isinstance(error,EngineError) else type(error).__name__,calls=calls)
        proof['elapsed_seconds']=round(time.perf_counter()-start,3)
        (out/'agent-real-router.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(proof,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
