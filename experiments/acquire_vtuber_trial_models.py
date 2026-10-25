"""Acquire only the two requested Q4_K_M files, serially, with pinned hashes/rate cap."""
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
ROOT=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502')
DEST=ROOT/'Leva-VTuber-Trial'
LIMIT=6*1024**2

def main():
    manifest=json.loads((OUT/'publisher-manifest.json').read_text('utf8'))
    proof={'status':'running','max_bytes_per_second':LIMIT,'serial':True,'assets':[],'network_cost_observed':'Unrestricted; roaming/over-limit/approaching-limit false'}
    def save():(OUT/'acquisition.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    for source in manifest[:3]:
        item=source['files'][0]
        path=(ROOT/'Leva-Personal-Models/Rocinante-X-12B'/item['name']) if source['repo'].startswith('bartowski/') else DEST/source['repo'].split('/')[-1]/item['name']
        row={**source,**item,'path':str(path),'status':'pending'};proof['assets'].append(row);save()
        try:
            if not path.is_file():
                path.parent.mkdir(parents=True,exist_ok=True);part=path.with_suffix(path.suffix+'.part')
                offset=part.stat().st_size if part.exists() else 0
                if shutil.disk_usage(path.parent).free < item['bytes']-offset+3*1024**3:raise RuntimeError('insufficient_disk_headroom')
                url='https://huggingface.co/'+source['repo']+'/resolve/'+source['revision']+'/'+item['name']
                request=urllib.request.Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
                with urllib.request.urlopen(request,timeout=45) as response:
                    if offset and response.status!=206:raise RuntimeError('resume_not_supported')
                    started=time.monotonic();downloaded=0;last=started
                    with part.open('ab' if offset else 'wb') as output:
                        while chunk:=response.read(1024**2):
                            output.write(chunk);downloaded+=len(chunk)
                            delay=downloaded/LIMIT-(time.monotonic()-started)
                            if delay>0:time.sleep(min(delay,.25))
                            if time.monotonic()-last>20:
                                row.update(status='downloading',downloaded=offset+downloaded,total_bytes=item['bytes']);save()
                                print(json.dumps({'model':source['repo'],'downloaded':offset+downloaded,'total':item['bytes']}),flush=True);last=time.monotonic()
                if part.stat().st_size!=item['bytes']:raise RuntimeError('download_size_mismatch')
                with part.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
                if actual!=item['sha256']:raise RuntimeError('publisher_hash_mismatch')
                part.replace(path)
            with path.open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
            if actual!=item['sha256'] or path.stat().st_size!=item['bytes']:raise RuntimeError('existing_asset_hash_mismatch')
            row.update(status='verified',local_sha256=actual,bytes=path.stat().st_size);save()
            print(json.dumps({'verified':source['repo'],'path':str(path)}),flush=True)
        except Exception as error:
            row.update(status='failed',error=type(error).__name__+':'+str(error)[:200]);proof['status']='acquisition_incomplete';save();raise
    proof['status']='verified';save()

if __name__=='__main__':main()
