"""Actual Saluki + harness, writes only to a new verification workspace."""
import hashlib,json,queue,sys,time
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from agent_runtime import _run_agent
from saluki_backend import SalukiEngine
from project_workspace import ProjectWorkspace
from file_workspace import FileWorkspace
from terminal_service import TerminalService

out=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-agent-v0216');out.mkdir(parents=True,exist_ok=True)
workspace=out/('agent-workspace-'+str(time.time_ns()));workspace.mkdir()
project=ProjectWorkspace(out/'patch-history');files=FileWorkspace(out/'file-history');files.observed.add(str(workspace))
terminal=TerminalService(out/'preview-terminal');commands=queue.Queue();receipts=[];started=time.monotonic()
goal='Coba buatkan sebuah website dengan kode HTML/CSS. Desain ringkas, tampilkan bumi berbentuk bola dengan CSS sederhana. Isi index.html maksimal 1400 karakter untuk uji ini. Boleh menggunakan Hermes Agent, tetapi alat internal juga boleh. Buat file index.html, baca kembali untuk memeriksa. Tidak perlu internet atau memasang paket. Setelah berkas dibuat dan dibaca kembali, jalankan pratinjau localhost memakai terminal action serve di workspace uji dan berikan URL hasil host. Workspace uji: '+str(workspace)
local=SalukiEngine(out/'saluki-runtime',mode='dual',acceleration='plain',max_output_tokens=2048)
def execute(name,args):
    if name=='project_action':
        action=args['action']
        if args.get('root') and Path(args['root']).resolve()!=workspace.resolve():raise ValueError('fixture_workspace_only')
        if action=='info':return {'status':'done','reply':'Workspace uji aktif.','root':str(workspace)}
        if action=='preview':return project.preview(workspace,args['patch'])
        if action=='apply':return project.change(args['patch_id'],expected_root=workspace)
        if action=='read':return project.read(workspace,args['path'],args.get('start') or 1,args.get('limit') or 80)
        if action=='search':return project.search(workspace,args['query'])
    if name=='file_action':
        for key in ('path','dest'):
            if args.get(key) and not Path(args[key]).resolve().is_relative_to(workspace.resolve()):raise ValueError('fixture_workspace_only')
        return files.run(args,goal)
    if name=='terminal' and args.get('action')=='serve':
        if not Path(args.get('cwd','')).resolve().is_relative_to(workspace.resolve()):raise ValueError('fixture_workspace_only')
        return terminal.serve(Path(args['cwd']))
    if name=='task_plan':return {'status':'done','reply':'Rencana uji dicatat.'}
    if name=='discover_tools':return {'status':'done','reply':'Gunakan development pada workspace uji.'}
    return {'status':'needs_input','reply':'Uji ini hanya menyediakan operasi proyek/berkas. Gunakan project_action atau file_action; tidak perlu terminal/browser.'}
def emit(event):
    if event.get('kind')!='tool_call':return
    try:result=execute(event['name'],event['args'])
    except (ValueError,OSError,KeyError) as error:result={'status':'failed','reply':str(error),'code':str(error) if isinstance(error,ValueError) else type(error).__name__,'retryable':str(error)=='file_path_not_observed' or isinstance(error,FileNotFoundError)}
    receipts.append({'name':event['name'],'action':event['args'].get('action'),'status':result['status'],'url':result.get('url'),'http_status':result.get('http_status')})
    print(json.dumps(receipts[-1]),flush=True)
    commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
try:
    result=_run_agent({'id':1,'mode':'local','speech_language':'id','time_budget_seconds':300,
        'messages':[{'role':'user','content':goal}],'tool_context':{'workspace_root':str(workspace)}},local,commands,emit)
    artifacts=[]
    for path in workspace.rglob('*.html'):
        text=path.read_text(encoding='utf8');parser=HTMLParser();parser.feed(text)
        artifacts.append({'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'has_html': '<html' in text.lower(),'has_body':'<body' in text.lower()})
    proof={'real_model':True,'model':'Saluki 27B IQ2 mix','gpu':'dual','workspace':str(workspace),
        'seconds':round(time.monotonic()-started,2),'receipts':receipts,'result':result,'artifacts':artifacts,
        'ok':any(r.get('http_status')==200 for r in receipts) and bool(artifacts) and not result.get('incomplete') and any(r['action']=='read' and r['status']=='done' for r in receipts)}
finally:
    local.close();terminal.stop_all()
(out/'real-agent-preview-small.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in proof.items() if k!='result'}),flush=True)
if not proof['ok']:raise SystemExit(1)
