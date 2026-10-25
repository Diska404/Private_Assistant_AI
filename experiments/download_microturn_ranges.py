"""Bounded parallel range download into one file; never duplicates the 22 GB base."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import subprocess
import threading

from prepare_microturn_lora import MODELS,META,sha

NAME='Qwen3.6-35B-A3B-UD-Q4_K_M.gguf'
REPO='unsloth/Qwen3.6-35B-A3B-GGUF'
CHUNK=64*1024*1024

def main():
    meta=json.loads((META/'unsloth--Qwen3.6-35B-A3B-GGUF.json').read_text('utf-8'))
    item=next(r for r in meta['siblings'] if r['rfilename']==NAME)
    size=item['lfs']['size']; expected=item['lfs']['sha256']
    part=MODELS/(NAME+'.part'); target=MODELS/NAME
    checkpoint=META/'range-progress.json'
    done=set()
    if checkpoint.exists():
        old=json.loads(checkpoint.read_text('utf-8'))
        if old['revision']==meta['sha'] and old['chunk_bytes']==CHUNK and part.exists() and part.stat().st_size==size:
            done=set(old['completed'])
    existing=part.stat().st_size if part.exists() else 0
    if not checkpoint.exists() and 0<existing<size:
        # Preserve completed contiguous chunks from the interrupted ordinary curl.
        done=set(range(existing//CHUNK))
    if not part.exists() or existing!=size:
        if shutil.disk_usage(MODELS).free<max(0,size-existing)+1_000_000_000:
            raise RuntimeError('insufficient_disk_headroom')
        with part.open('r+b' if part.exists() else 'wb') as f: f.truncate(size)
    checkpoint.write_text(json.dumps({'revision':meta['sha'],'chunk_bytes':CHUNK,'completed':sorted(done),
                                      'total':(size+CHUNK-1)//CHUNK}),encoding='utf-8')
    print(json.dumps({'resumed_chunks':len(done),'total':(size+CHUNK-1)//CHUNK}),flush=True)
    lock=threading.Lock()
    total=(size+CHUNK-1)//CHUNK
    def download(index):
        start=index*CHUNK; end=min(size,start+CHUNK)-1
        path=META/f'range-{index:04d}.chunk'
        url=f'https://huggingface.co/{REPO}/resolve/{meta["sha"]}/{NAME}?download=true&part={index}'
        result=subprocess.run(['curl.exe','-4','-fLsS','--retry','3','--connect-timeout','20','--max-time','180',
            '--range',f'{start}-{end}','--max-filesize',str(end-start+1),'-o',str(path),
            '--write-out','%{http_code}',url],capture_output=True,text=True,creationflags=0x08000000)
        if result.returncode or result.stdout.strip()!='206' or path.stat().st_size!=end-start+1:
            raise RuntimeError(f'range_download_failed_{index}_http_{result.stdout.strip()}')
        with path.open('rb') as src,part.open('r+b') as dst:
            dst.seek(start)
            shutil.copyfileobj(src,dst,1024*1024)
        path.unlink()
        with lock:
            done.add(index)
            temp=checkpoint.with_suffix('.tmp')
            temp.write_text(json.dumps({'revision':meta['sha'],'chunk_bytes':CHUNK,'completed':sorted(done),'total':total}),encoding='utf-8')
            temp.replace(checkpoint)
            if len(done)%10==0 or len(done)==total:
                print(json.dumps({'chunks':len(done),'total':total,'percent':round(len(done)/total*100,1)}),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for _ in pool.map(download,[i for i in range(total) if i not in done]): pass
    print('Checking complete model SHA-256',flush=True)
    if sha(part)!=expected: raise RuntimeError('complete_model_hash_mismatch')
    part.replace(target)
    manifest=json.loads((MODELS/'manifest.partial.json').read_text('utf-8'))
    manifest['files']=[r for r in manifest['files'] if r['name']!=NAME]
    manifest['files'].append({'repo':REPO,'revision':meta['sha'],'name':NAME,'path':str(target),
                              'bytes':size,'sha256':expected,'lfs_hash_verified':True})
    (MODELS/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'status':'downloaded_hash_verified','bytes':size,'manifest':str(MODELS/'manifest.json')}),flush=True)

if __name__=='__main__': main()
