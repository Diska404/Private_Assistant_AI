"""Download the matched official MicroTurn adapter and tested base quant to D."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

MODELS=Path(r'D:\AI\AI Lokal Asisten\AI Models\MicroTurn-Duplex')
META=Path(r'D:\AI\AI Lokal Asisten\Leva\downloads\microturn-duplex')
MODELS.mkdir(parents=True,exist_ok=True)
META.mkdir(parents=True,exist_ok=True)

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def curl(url,path,maximum,timeout=180):
    subprocess.run(['curl.exe','-4','-fLsS','--retry','2','--connect-timeout','25','--max-time',str(timeout),
                    '--max-filesize',str(maximum),'-o',str(path),url],check=True,creationflags=0x08000000)

def main():
    wanted={
        'codacus/Qwen3.6-35B-A3B-MicroTurn-Duplex-LoRA':['microturn-duplex-lora.gguf','microturn_client.py','README.md'],
        'unsloth/Qwen3.6-35B-A3B-GGUF':['Qwen3.6-35B-A3B-UD-Q4_K_M.gguf'],
    }
    manifest={'base_model':'Qwen3.6-35B-A3B','protocol':'MicroTurn Duplex LoRA','files':[],'repositories':{}}
    tasks=[]
    for repo,names in wanted.items():
        path=META/(repo.replace('/','--')+'.json')
        curl('https://huggingface.co/api/models/'+repo+'?blobs=true',path,8_000_000)
        metadata=json.loads(path.read_text('utf-8'))
        rev=metadata['sha']
        manifest['repositories'][repo]=rev
        for name in names:
            record=next(r for r in metadata['siblings'] if r['rfilename']==name)
            size=record.get('lfs',{}).get('size',record.get('size',0))
            tasks.append((repo,rev,name,size,record.get('lfs',{}).get('sha256')))
    required=sum(t[3] for t in tasks if not (MODELS/t[2]).exists())
    free=shutil.disk_usage(MODELS).free
    print(json.dumps({'required_bytes':required,'free_bytes':free,'assets':[{'name':t[2],'bytes':t[3]} for t in tasks]}),flush=True)
    if free<required+3_000_000_000: raise RuntimeError('insufficient_disk_headroom')
    for repo,rev,name,size,expected in tasks:
        path=MODELS/name
        if not path.exists() or (expected and sha(path)!=expected):
            part=path.with_name(path.name+'.part')
            curl('https://huggingface.co/'+repo+'/resolve/'+rev+'/'+name,part,max(size+100000,2_000_000),3600)
            if expected and sha(part)!=expected: raise RuntimeError('download_hash_mismatch: '+name)
            part.replace(path)
        actual=sha(path)
        if expected and actual!=expected: raise RuntimeError('asset_hash_mismatch: '+name)
        if name.endswith('.gguf'):
            with path.open('rb') as f:
                if f.read(4)!=b'GGUF': raise RuntimeError('invalid_gguf')
        manifest['files'].append({'repo':repo,'revision':rev,'name':name,'path':str(path),'bytes':path.stat().st_size,
                                  'sha256':actual,'lfs_hash_verified':bool(expected)})
        (MODELS/'manifest.partial.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps({'verified':name,'bytes':path.stat().st_size}),flush=True)
    (MODELS/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'status':'downloaded_hash_verified','manifest':str(MODELS/'manifest.json')}),flush=True)

if __name__=='__main__': main()
