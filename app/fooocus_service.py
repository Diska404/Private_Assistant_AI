"""Connector to a Leva-owned session of the user's installed Fooocus, without updating it."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.request
import uuid

from comfy_service import ComfyService,ComfyClient,ComfyError
from paths import DATA,ROOT


class FooocusClient(ComfyClient):
    def __init__(self,base,token):super().__init__(base);self.token=token
    def headers(self):return {'X-Leva-Token':self.token}
    def request(self,route,payload=None,timeout=8):
        route={'/system_stats':'/leva/status','/queue':'/leva/queue'}.get(route,route)
        return super().request(route,payload,timeout)


class FooocusService(ComfyService):
    def __init__(self,root='',base='http://127.0.0.1:7866',storage=None,extra_roots=()):
        super().__init__(root,base,storage or DATA/'fooocus')
        self.extra_roots=[Path(path) for path in extra_roots]
        path=self.storage/'session-token'
        if not path.exists():path.write_text(secrets.token_urlsafe(32),encoding='utf-8')
        self.client=FooocusClient(base,path.read_text('utf-8'))

    def installation(self):
        root=self.root
        if root and (root/'Fooocus/webui.py').is_file() and (root/'python_embeded/python.exe').is_file():return root/'Fooocus',root/'python_embeded/python.exe',root
        raise ComfyError('fooocus_portable_installation_required')

    def gpu_query(self):
        return 'import torch,json;arch=max(int(a.split("_")[1]) for a in torch.cuda.get_arch_list() if a.startswith("sm_"));print(json.dumps([{"index":i,"name":torch.cuda.get_device_name(i),"total":torch.cuda.get_device_properties(i).total_memory,"compatible":sum(a*b for a,b in zip(torch.cuda.get_device_capability(i),(10,1)))<=arch} for i in range(torch.cuda.device_count())]))'

    def pick_gpu(self,devices):
        supported=[row for row in devices if row.get('compatible')]
        if not supported:raise ComfyError('fooocus_no_compatible_cuda_gpu')
        return max(supported,key=lambda row:row['total'])

    def model_roots(self):
        code,_,_=self.installation();roots=[code/'models/checkpoints',Path(r'D:\AI\checkpoints'),*self.extra_roots]
        original=code/'config.txt'
        warning=''
        if original.is_file():
            try:
                config=json.loads(original.read_text('utf-8-sig'))
                values=config.get('path_checkpoints',[])
                if isinstance(values,str):values=[values]
                roots.extend(Path(v) for v in values if isinstance(v,str))
            except (ValueError,TypeError):warning='Konfigurasi asli Fooocus tidak valid; sesi Leva memakai konfigurasi terpisah, bukan menimpa berkas asli.'
        roots=list(dict.fromkeys(str(path.resolve()) for path in roots if path.is_dir()))
        return roots,warning

    def catalog(self,query='',category=''):
        roots,warning=self.model_roots();rows=[];seen={}
        for folder in roots:
            for path in Path(folder).rglob('*.safetensors'):
                # Read header only: do not load tensors merely to inspect architecture.
                try:
                    with path.open('rb') as file:
                        size=int.from_bytes(file.read(8),'little')
                        if not 2<size<16_000_000:continue
                        header=json.loads(file.read(size))
                    family='sdxl' if any(k.startswith('conditioner.embedders.1.') for k in header) else 'unknown'
                except (OSError,ValueError):continue
                name=str(path.relative_to(folder))
                if query.casefold() not in name.casefold():continue
                if name in seen:seen[name]['ambiguous']=True;continue
                row={'name':name,'family':family,'size_gib':round(path.stat().st_size/2**30,2),'ambiguous':False};seen[name]=row;rows.append(row)
        return {'status':'done','reply':'Checkpoint lokal diperiksa dari header tanpa memuat bobot. Fooocus memakai checkpoint SDXL yang sesuai.','models':rows[:100],'roots':roots,'warning':warning,'untrusted_data':True}

    def session_config(self):
        code,_,_=self.installation();roots,warning=self.model_roots()
        catalog=self.catalog()['models'];eligible=[r for r in catalog if r['family']=='sdxl' and not r['ambiguous']]
        if not eligible:raise ComfyError('fooocus_no_verified_sdxl_checkpoint')
        chosen=next((r for r in eligible if 'juggernautxl_v8' in r['name'].lower()),eligible[0])
        output=self.storage/'outputs';output.mkdir(exist_ok=True)
        config={'path_checkpoints':roots,'path_loras':[str(code/'models/loras')],'path_outputs':str(output),
                'default_model':chosen['name'],'default_refiner':'None','default_loras':[],
                'checkpoint_downloads':{},'lora_downloads':{},'embeddings_downloads':{},'vae_downloads':{},'default_styles':[],
                'temp_path':str(self.storage/'temp'),'temp_path_cleanup_on_launch':False,'default_image_number':1}
        path=self.storage/'session-config.json';path.write_text(json.dumps(config,indent=2),encoding='utf-8')
        return path

    def server_command(self,code,python,cwd,gpu,port):
        worker=Path(sys._MEIPASS)/'assistant_runtime/fooocus_worker.py' if getattr(sys,'frozen',False) else ROOT/'app/fooocus_worker.py'
        self.session_config()
        return [str(python),'-s','-u',str(worker),'--root',str(code),'--storage',str(self.storage),'--port',str(port)]

    def server_environment(self,gpu):
        env=os.environ.copy();env.update(CUDA_VISIBLE_DEVICES=str(gpu['index']),GRADIO_ANALYTICS_ENABLED='False',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        return env

    def start(self,authorized=lambda:True):
        result=super().start(authorized)
        result['reply']=result['reply'].replace('ComfyUI','Fooocus')
        return result

    def status(self):
        result=super().status();result['reply']=result['reply'].replace('ComfyUI','Fooocus');return result

    def generate(self,model='',positive='',negative='',steps=20,width=768,height=768,authorized=lambda:True,seed=None):
        generation=self.generation
        available=[row for row in self.catalog()['models'] if row['family']=='sdxl' and not row['ambiguous']]
        if model:
            matches=[row for row in available if row['name']==model or model.casefold() in row['name'].casefold()]
            if len(matches)!=1:raise ComfyError('fooocus_model_missing_or_ambiguous')
            chosen=matches[0]
        else:chosen=next((row for row in available if 'juggernautxl_v8' in row['name'].lower()),next(iter(available),None))
        if chosen is None:raise ComfyError('fooocus_no_verified_sdxl_checkpoint')
        if not 1<=int(steps)<=60 or not 256<=int(width)<=1536 or not 256<=int(height)<=1536 or int(width)%8 or int(height)%8:raise ComfyError('fooocus_parameter_range')
        if generation!=self.generation or not authorized():return {'status':'cancelled','reply':'Generation Fooocus dibatalkan sebelum dikirim.'}
        ident=uuid.uuid4().hex[:12]
        payload={'id':ident,'model':chosen['name'],'positive':positive.strip() or 'A cozy wooden cabin beside a lake, morning mist, warm sunlight, cinematic photography, detailed natural landscape',
                 'negative':negative,'steps':int(steps),'width':int(width),'height':int(height),'seed':secrets.randbits(32) if seed is None else int(seed)}
        record={'id':ident,'base':self.client.base,'title':'Fooocus image','state':'submission_unknown','selection':payload,'prompt_id':ident,'submission_attempted':True}
        self._save(record)  # Persist identity before POST; a missing reply never permits blind resubmission.
        self.last_submission_id=ident
        result=self.client.request('/leva/generate',payload,timeout=15)
        record['state']=result['state'];self._save(record)
        return {'status':'running','reply':'Fooocus menerima generation. Periksa job_id sampai berkas gambar selesai diverifikasi.','job_id':ident,'workflow_id':ident,'model':chosen['name'],'positive':payload['positive'],'engine':'fooocus'}

    def poll(self,ident):
        record=self._record(ident);job=self.client.request('/leva/jobs/'+ident)
        state=job.get('state','unknown');record['state']=state;self._save(record)
        success=state=='completed' and bool(job.get('outputs'))
        return {'status':'done' if success else 'running' if state in ('queued','running') else 'failed',
                'reply':'Gambar Fooocus selesai dan berkas output diverifikasi.' if success else 'Job Fooocus '+state+'.',
                'job_id':ident,'workflow_id':ident,'engine':'fooocus','workflow_state':state,'outputs':job.get('outputs',[]),'error':job.get('error',''),
                'elapsed_seconds':job.get('elapsed_seconds'),'task_verified':success}
