"""Download pinned Saluki MTP and DFlash2 GGUFs; verify authoritative LFS hashes."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import urllib.request

ROOT=Path(r'D:\AI\AI Lokal Asisten\AI Models\Saluki-27B')
TARGETS=[('Kujira/Underdog-Saluki-27B-1.0-MTP-GGUF','Underdog-Saluki-27B-1.0-IQ2-mix-MTP.gguf'),
         ('z-lab/Qwen3.8-27B-DFlash2-GGUF','Qwen3.8-27B-DFlash2-Q4_K_M.gguf')]
CHUNK=64*1024*1024

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def download(repo,name):
    folder=ROOT/name.removesuffix('.gguf')
    folder.mkdir(parents=True,exist_ok=True)
    metadata=folder/'source.json'
    if not metadata.exists():
        subprocess.run(['curl.exe','-4','-fLsS','--connect-timeout','15','--max-time','60',
            '-o',str(metadata),f'https://huggingface.co/api/models/{repo}?blobs=true'],check=True,creationflags=0x08000000)
    meta=json.loads(metadata.read_text('utf-8'))
    row=next(r for r in meta['siblings'] if r['rfilename']==name)
    size=row['lfs']['size']; expected=row['lfs']['sha256']
    target=ROOT/name
    if target.exists():
        if target.stat().st_size!=size or sha(target)!=expected:raise RuntimeError('existing_asset_mismatch')
    else:
        part=ROOT/(name+'.part'); checkpoint=folder/'progress.json'
        done=set()
        if checkpoint.exists() and part.exists() and part.stat().st_size==size:
            old=json.loads(checkpoint.read_text('utf-8'))
            if old['revision']==meta['sha']:done=set(old['completed'])
        if not part.exists():
            if shutil.disk_usage(ROOT).free<size+2*1024**3:raise RuntimeError('insufficient_storage')
            with part.open('wb') as stream:stream.truncate(size)
        total=(size+CHUNK-1)//CHUNK
        lock=threading.Lock()
        print(json.dumps({'download':name,'total_chunks':total,'resumed':len(done)}),flush=True)
        def block(index):
            start=index*CHUNK; end=min(size,start+CHUNK)-1
            tmp=folder/f'{index:04d}.chunk'
            url=f'https://huggingface.co/{repo}/resolve/{meta["sha"]}/{name}?download=true&part={index}'
            r=subprocess.run(['curl.exe','-4','-fLsS','--retry','3','--connect-timeout','20','--max-time','180',
                '--range',f'{start}-{end}','--max-filesize',str(end-start+1),'-o',str(tmp),
                '--write-out','%{http_code}',url],capture_output=True,text=True,creationflags=0x08000000)
            if r.returncode or r.stdout.strip()!='206' or tmp.stat().st_size!=end-start+1:
                raise RuntimeError(f'range_failed_{index}_{r.returncode}_{r.stdout.strip()}')
            with tmp.open('rb') as src,part.open('r+b') as dst:
                dst.seek(start); shutil.copyfileobj(src,dst,1024*1024)
            tmp.unlink()
            with lock:
                done.add(index)
                checkpoint.write_text(json.dumps({'revision':meta['sha'],'completed':sorted(done)}),encoding='utf-8')
                if len(done)%10==0 or len(done)==total:
                    print(json.dumps({'name':name,'chunks':len(done),'total':total}),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for _ in pool.map(block,[i for i in range(total) if i not in done]):pass
        if sha(part)!=expected:raise RuntimeError('asset_hash_mismatch')
        with part.open('rb') as stream:
            if stream.read(4)!=b'GGUF':raise RuntimeError('not_gguf')
        part.rename(target)
    record={'repo':repo,'revision':meta['sha'],'name':name,'bytes':size,'sha256':expected,'path':str(target),'verified':True}
    (folder/'manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'verified':name,'bytes':size}),flush=True)
    return record

if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    records=[download(*target) for target in TARGETS]
    (ROOT/'manifest.json').write_text(json.dumps({'files':records},indent=2),encoding='utf-8')
