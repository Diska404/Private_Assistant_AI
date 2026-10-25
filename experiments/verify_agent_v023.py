"""Exact user transcript -> real Saluki -> read-only starter vault, with old-task context."""
import json,queue,sys,time,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from second_brain import SecondBrain
from preferences import Preferences
from saluki_backend import SalukiEngine
from agent_runtime import _run_agent
from task_journal import TaskJournal
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/web-v023');OUT.mkdir(parents=True,exist_ok=True)
goal='Leva menurut catatan obsidian saya apa prioritas pengembangan untuk suara live eh bisakah sebutkan sebenernya'
with tempfile.TemporaryDirectory(dir=OUT) as folder:
    prefs=Preferences(Path(folder)/'preferences.db');prefs.set('obsidian_vault','D:/AI/AI Lokal Asisten/Leva/SecondBrain')
    service=SecondBrain(prefs,Path(folder)/'index')
    journal=TaskJournal(Path(folder)/'tasks.db');old=journal.begin('buatkan website pesawat 3D free cam');journal.wait_for_input(old,'Pilih path workspace proyek yang ingin digunakan terlebih dahulu.')
    assert journal.continuation(goal) is None
    model=SalukiEngine(OUT/'model-runtime',mode='dual',acceleration='plain',max_output_tokens=2048)
    commands=queue.Queue();receipts=[];start=time.perf_counter()
    def emit(event):
        if event.get('kind')!='tool_call':return
        result=service.run(event['args']) if event['name']=='obsidian_action' else {'status':'failed','reply':'Only read-only vault access is provided in this regression.'}
        receipts.append({'tool':event['name'],'args':event['args'],'status':result['status'],'sources':[r['path'] for r in result.get('sources',[])]})
        print(json.dumps(receipts[-1]),flush=True)
        commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
    try:
        result=_run_agent({'id':1,'mode':'local','time_budget_seconds':180,'messages':[{'role':'user','content':'buatkan website pesawat 3D free cam'},{'role':'assistant','content':'Pilih path workspace proyek yang ingin digunakan terlebih dahulu.'},{'role':'user','content':goal}]},model,commands,emit)
        answer=result.get('response','')
        proof={'input':goal,'real_model':'Saluki 27B IQ2 mix','mode':'dual','starter_vault_read_only':True,'old_task_not_resumed':True,'seconds':round(time.perf_counter()-start,2),'receipts':receipts,'result':result,
               'ok':bool(receipts) and all(r['tool']=='obsidian_action' for r in receipts) and any('04_Decisions/Suara dan Prioritas.md' in r['sources'] for r in receipts) and bool(answer) and not result.get('incomplete')}
    except Exception as error:proof={'ok':False,'code':str(error),'receipts':receipts,'seconds':round(time.perf_counter()-start,2)}
    finally:model.close();prefs.close()
    (OUT/'real-agent-regression.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in proof.items() if k!='result'}),flush=True)
    if not proof['ok']:raise SystemExit(1)
