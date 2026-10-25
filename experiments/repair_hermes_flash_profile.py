"""Apply a backed-up, model-only low-memory preset to the existing Hermes router.

No application code, account credentials, model weights or unrelated presets are changed.
"""
import configparser
import json
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.request

import psutil

HOME=Path(r'C:\Users\Raizei\AppData\Local\hermes')
RUNTIME=HOME/'runtimes/llamacpp'
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\hermes-flash-repair-20261024')
MODEL='Qwen3.8-Flash-Next-UD-IQ4_XS'
BASE='http://127.0.0.1:18434'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    key=(RUNTIME/'.api_key').read_text('utf8').strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(route,payload=None,timeout=8):
        req=urllib.request.Request(BASE+route,data=None if payload is None else json.dumps(payload).encode(),
              headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        with opener.open(req,timeout=timeout) as response:return json.load(response)
    path=RUNTIME/'presets.ini'
    raw=path.read_bytes().decode('utf8')
    before=configparser.ConfigParser(interpolation=None);before.read_string(raw)
    if MODEL not in before:raise ValueError('flash_preset_not_found')
    fields=dict(before[MODEL])
    fields.update({'ctx-size':'4096','batch-size':'128','ubatch-size':'64','load-mode':'mmap',
        'lazy-mode':'on','repack':'off','no-host':'on','warmup':'off','gpu-layers':'99',
        'split-mode':'layer','tensor-split':'3,1','device':'CUDA0,CUDA1','threads':'8','threads-batch':'8',
        'override-tensor':r'blk\.\d+\.ffn_.*_exps\.weight=CPU,per_layer_token_embd=CPU',
        'temp':'0.7','top-p':'0.8'})
    replacement='['+MODEL+']\r\n'+'\r\n'.join(k+' = '+v for k,v in fields.items())+'\r\n'
    revised,count=re.subn(r'(?ms)^\['+re.escape(MODEL)+r'\]\r?\n.*?(?=^\[|\Z)',lambda _:replacement,raw)
    if count!=1:raise ValueError('flash_preset_section_count')
    after=configparser.ConfigParser(interpolation=None);after.read_string(revised)
    if any(dict(before[s])!=dict(after[s]) for s in before.sections() if s!=MODEL):raise ValueError('unrelated_preset_changed')
    backup=OUT/'presets-original.ini'
    if not backup.exists():shutil.copy2(path,backup)
    (OUT/'presets-low-memory.ini').write_bytes(revised.encode('utf8'))
    temp=path.with_suffix('.leva-tmp');temp.write_bytes(revised.encode('utf8'));temp.replace(path)
    proof={'status':'profile_applied','backup':str(backup),'preset_path':str(path),'model':MODEL,
           'experimental_context':4096,'unrelated_presets_unchanged':True,'tests':[],'resource_samples':[]}
    def save():(OUT/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    save()
    try:
        models=request('/models?reload=1',timeout=20)
        rows=models.get('data',models.get('models',[]))
        found=next(row for row in rows if row.get('id',row.get('name'))==MODEL)
        args=found.get('status',{}).get('args',[])
        proof['router_model_status']=found.get('status',{}).get('value')
        proof['router_accepted_overrides']=all(str(value) in args for value in ('4096','mmap','128','64'))
        proof['router_args_without_credentials']=[str(a) for a in args if 'key' not in str(a).lower() and a!=key]
        save()
        if not proof['router_accepted_overrides']:raise ValueError('router_did_not_accept_profile_reload')
        done=threading.Event()
        def guard():
            started=time.monotonic()
            while not done.wait(1):
                free=psutil.virtual_memory().available
                proof['resource_samples'].append({'time':time.time(),'available_ram_bytes':free,'cpu_percent':psutil.cpu_percent()})
                if free<2*1024**3 or time.monotonic()-started>420:
                    proof['resource_guard']='free_ram_below_2GiB' if free<2*1024**3 else 'probe_time_limit'
                    try:request('/models/unload',{'model':MODEL},timeout=15)
                    except Exception:pass
                    return
        thread=threading.Thread(target=guard,daemon=True);thread.start()
        try:
            for prompt,expected in [('Jawab persis: Halo.','Halo.'),('Berapa 17 dikali 23? Jawab angka saja.','391')]:
                started=time.perf_counter()
                try:
                    result=request('/v1/chat/completions',{'model':MODEL,'messages':[{'role':'user','content':prompt}],
                        'temperature':0,'max_tokens':24,'chat_template_kwargs':{'enable_thinking':False}},timeout=360)
                    choice=result['choices'][0]
                    text=choice['message'].get('content','')
                    proof['tests'].append({'prompt':prompt,'response':text,'finish_reason':choice.get('finish_reason'),
                         'elapsed_ms':round((time.perf_counter()-started)*1000,2),'timings':result.get('timings'),
                         'expected_present':expected.lower() in text.lower()})
                    save()
                except Exception as error:
                    proof['tests'].append({'prompt':prompt,'error':type(error).__name__+':'+str(error)[:500],
                        'elapsed_ms':round((time.perf_counter()-started)*1000,2)})
                    raise
            proof['status']='inference_verified' if all(t.get('expected_present') and t.get('finish_reason')=='stop' for t in proof['tests']) else 'response_unverified'
        finally:
            done.set();thread.join(2)
    except Exception as error:
        proof.update(status='not_verified',error=type(error).__name__+':'+str(error)[:500])
    finally:
        # Diagnostic overrides are temporary. Never overwrite a concurrent user edit.
        if path.read_bytes() == revised.encode('utf8'):
            restore = path.with_suffix('.leva-restore-tmp')
            restore.write_bytes(raw.encode('utf8')); restore.replace(path)
            proof['preset_file_restored'] = True
            try:
                request('/models?reload=1', timeout=20)
                proof['router_preset_restored'] = True
            except Exception as error:
                proof['router_restore_error'] = type(error).__name__
        else:
            proof['preset_restore_skipped'] = 'file_changed_after_diagnostic'
        save()
    print(json.dumps({k:v for k,v in proof.items() if k not in ('resource_samples','router_args_without_credentials')},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
