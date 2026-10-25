"""Pinned, resumable GGUF downloads; public metadata and full SHA256 verification."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request

ROOT=Path(r'D:\AI\AI Lokal Asisten\AI Models')
ALTERNATE=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\personal-models-v033')
TARGETS=[('qwen3_8b','Qwen3-8B','Qwen/Qwen3-8B-GGUF','Qwen3-8B-Q4_K_M.gguf'),
 ('stheno8b','Stheno-8B','bartowski/L3-8B-Stheno-v3.2-GGUF','L3-8B-Stheno-v3.2-Q4_K_M.gguf'),
 ('rpmax12b','ArliAI-RPMax-12B','mradermacher/Mistral-Nemo-12B-ArliAI-RPMax-v1.1-GGUF','Mistral-Nemo-12B-ArliAI-RPMax-v1.1.Q4_K_M.gguf')]
CHUNK=32*1024*1024
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def metadata(target):
    key,folder,repo,name=target
    with urllib.request.urlopen('https://huggingface.co/api/models/'+repo+'?blobs=true',timeout=45) as r:meta=json.load(r)
    row=next(s for s in meta['siblings'] if s['rfilename']==name)
    return {**dict(zip(('key','folder','repo','name'),target)),'revision':meta['sha'],'bytes':row['lfs']['size'],'sha256':row['lfs']['sha256'],'license':meta.get('cardData',{}).get('license')}
def download(record):
    target=Path(record['path']);folder=target.parent;folder.mkdir(parents=True,exist_ok=True)
    expected=record['sha256'];size=record['bytes'];part=target.with_suffix('.gguf.part');checkpoint=folder/'download-progress.json'
    (folder/'source.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    if target.exists():
        if target.stat().st_size!=size or sha(target)!=expected:raise RuntimeError('existing_asset_mismatch_'+record['key'])
    else:
        done=set()
        if checkpoint.exists() and part.exists() and part.stat().st_size==size:
            previous=json.loads(checkpoint.read_text('utf8'))
            if previous['revision']==record['revision']:done=set(previous['completed'])
        if not part.exists():
            with part.open('wb') as stream:stream.truncate(size)
        count=(size+CHUNK-1)//CHUNK;lock=threading.Lock()
        def block(index):
            start=index*CHUNK;end=min(size,start+CHUNK)-1;tmp=folder/f'.chunk-{index:04d}'
            url=f'https://huggingface.co/{record["repo"]}/resolve/{record["revision"]}/{record["name"]}?download=true&part={index}'
            result=subprocess.run(['curl.exe','-4','-fLsS','--retry','4','--connect-timeout','20','--max-time','240','--range',f'{start}-{end}','--max-filesize',str(end-start+1),'-o',str(tmp),'--write-out','%{http_code}',url],capture_output=True,text=True,creationflags=0x08000000)
            if result.returncode or result.stdout.strip()!='206' or tmp.stat().st_size!=end-start+1:raise RuntimeError(f'range_failed_{record["key"]}_{index}_{result.returncode}')
            with tmp.open('rb') as src,part.open('r+b') as dst:
                dst.seek(start);shutil.copyfileobj(src,dst,1024*1024)
            tmp.unlink()
            with lock:
                done.add(index);temp=checkpoint.with_suffix('.tmp');temp.write_text(json.dumps({'revision':record['revision'],'completed':sorted(done)}),encoding='utf8');temp.replace(checkpoint)
                if len(done)%20==0 or len(done)==count:print(json.dumps({'model':record['key'],'chunks':len(done),'total':count}),flush=True)
        print(json.dumps({'starting':record['key'],'resumed':len(done),'chunks':count}),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(block,[i for i in range(count) if i not in done]))
        if sha(part)!=expected:raise RuntimeError('sha256_mismatch_'+record['key'])
        with part.open('rb') as stream:
            if stream.read(4)!=b'GGUF':raise RuntimeError('invalid_gguf')
        part.rename(target)
    record.update(verified=True)
    (folder/'manifest.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps({'verified':record['key'],'bytes':size}),flush=True)
    return record
if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);ROOT.mkdir(parents=True,exist_ok=True)
    rows=list(concurrent.futures.ThreadPoolExecutor(3).map(metadata,TARGETS));remaining=shutil.disk_usage(ROOT).free
    for row in rows:
        existing=ROOT/row['folder']/row['name'];required=0 if existing.exists() else row['bytes']
        base=ROOT if remaining-required>=5*1024**3 else ALTERNATE/'Leva-Personal-Models'
        if base!=ROOT and shutil.disk_usage(ALTERNATE).free<required+2*1024**3:raise RuntimeError('insufficient_storage')
        row['path']=str(base/row['folder']/row['name'])
        if base==ROOT:remaining-=required
    (OUT/'download-plan.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    print(json.dumps({'planned_bytes':sum(r['bytes'] for r in rows),'d_remaining_after':remaining,'locations':[r['path'] for r in rows]}),flush=True)
    started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:completed=list(pool.map(download,rows))
    (OUT/'downloads.json').write_text(json.dumps({'files':completed,'seconds':round(time.monotonic()-started,2)},indent=2),encoding='utf8')
