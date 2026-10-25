"""Real Saluki -> host ComfyUI API -> one saved image. No unrelated process control."""
import hashlib,json,queue,sys,time,urllib.parse,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from agent_runtime import _run_agent
from desktop_service import DesktopService
from preferences import Preferences
from saluki_backend import SalukiEngine
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/comfy-reliability-v0261');OUT.mkdir(parents=True,exist_ok=True)
prefs=Preferences();desktop=DesktopService(preferences=prefs);tools=desktop.tools
local=SalukiEngine(OUT/'saluki-runtime',mode='dual',acceleration='plain',max_output_tokens=1536)
proof={'real_model':'Saluki 27B IQ2-mix','gpu':'dual','cases':[],'outputs':[]}
goals=[
 'Buatkan template ComfyUI sederhana SDXL dengan checkpoint juggernautXL_v8Rundiffusion.safetensors yang sudah ada, prompt kabin kayu di tepi danau, 512x512, 12 steps. Gunakan VAE bawaan checkpoint. Simpan ke pustaka. Jangan generate dahulu. Tidak perlu membuka browser pada uji ini.',
 'bisakah leva buat 1 generat gambar dengan ComfyUI dan template bebas, gunakan model yang sudah ada, ukuran 512x512 dan 12 steps. Langsung generate satu gambar saja.'
]
try:
    for index,goal in enumerate(goals):
        commands=queue.Queue();receipts=[];started=time.monotonic()
        def emit(event):
            if event.get('kind')!='tool_call':return
            name=event['name'];args=event['args']
            if name not in ('comfy_action','image_action','task_plan','discover_tools'):raise RuntimeError('unexpected_probe_tool:'+name)
            if args.get('action') in ('open','canvas','stop_server'):raise RuntimeError('probe_api_only')
            result=tools.execute(name,args,goal)
            receipts.append({'name':name,'args':args,'status':result.get('status'),'code':result.get('code'),'workflow_id':result.get('workflow_id'),'job_id':result.get('job_id')})
            print(json.dumps({'case':index,**receipts[-1]}),flush=True)
            commands.put({'kind':'tool_result','id':index+1,'call_id':event['call_id'],'result':result})
        result=_run_agent({'id':index+1,'mode':'local','speech_language':'id','time_budget_seconds':240,'messages':[{'role':'user','content':goal}],
                          'tool_context':tools.context(goal)},local,commands,emit)
        case={'case':index,'seconds':round(time.monotonic()-started,2),'receipts':receipts,'response':result.get('response'),'incomplete':result.get('incomplete',False),'token_budget':getattr(local,'last_tool_budget',{})}
        proof['cases'].append(case)
        if index==0:
            ident=next((r['workflow_id'] for r in reversed(receipts) if r.get('workflow_id') and r['status']=='done'),None)
            if not ident:raise RuntimeError('template_not_prepared')
            record=tools.comfy_service._record(ident);case['published']=record.get('published');case['selection']=record['selection']
            if record.get('submission_attempted') or not record.get('published') or record['selection'].get('vae'):raise RuntimeError('template_goal_not_met')
        else:
            ident=next((r.get('job_id') or r.get('workflow_id') for r in reversed(receipts) if r.get('job_id') or r.get('workflow_id')),None)
            if not ident:raise RuntimeError('generation_not_submitted')
            until=time.monotonic()+240
            while time.monotonic()<until:
                observed=tools.comfy_service.poll(ident)
                if observed['status']!='running':break
                time.sleep(2)
            case['generation']=observed
            if observed['status']!='done' or not observed.get('outputs'):raise RuntimeError('generation_not_verified')
            from image_jobs import ImageJobs
            ImageJobs().acknowledge('comfyui',ident)
            for item in observed['outputs']:
                query=urllib.parse.urlencode({k:item[k] for k in ('filename','subfolder','type')})
                with tools.comfy_service.client.opener.open(tools.comfy_service.client.base+'/view?'+query,timeout=8) as response:raw=response.read(8_000_000)
                target=OUT/Path(item['filename']).name;target.write_bytes(raw)
                proof['outputs'].append({'path':str(target),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        (OUT/'real-comfy-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'case':index,'verified':True,'seconds':case['seconds'],'token_budget':case['token_budget']}),flush=True)
finally:
    local.close();desktop.stop_owned_processes();prefs.close()
    (OUT/'real-comfy-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
