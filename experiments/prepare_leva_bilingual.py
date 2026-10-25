"""Pin public Seed-VC/Kokoro assets; download only, no user audio uploads."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r'D:\AI\AI Lokal Asisten\Leva')
MODELS = Path(r'D:\AI\AI Lokal Asisten\AI Models')
DOWNLOADS = DATA / 'downloads/leva-bilingual-v3'
DOWNLOADS.mkdir(parents=True, exist_ok=True)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def get(url, path, maximum=2_000_000_000):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.part')
    subprocess.run(['curl.exe','-4','-fLsS','--retry','2','--connect-timeout','25','--max-time','900',
                    '--max-filesize',str(maximum),'-o',str(temporary),url],check=True,creationflags=0x08000000)
    temporary.replace(path)
    return path

def prepare():
    meta = json.loads(get('https://api.github.com/repos/Plachtaa/seed-vc/commits/main',DOWNLOADS/'source.json',2_000_000).read_text('utf-8'))
    commit = meta['sha']
    archive = DOWNLOADS / f'seed-vc-{commit}.zip'
    if not archive.exists(): get(f'https://codeload.github.com/Plachtaa/seed-vc/zip/{commit}',archive,100_000_000)
    vendor = ROOT / 'experiments/vendor' / ('seed-vc-'+commit)
    if not vendor.exists():
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (vendor.parent/name).resolve().is_relative_to(vendor.resolve()): raise ValueError('unsafe_archive')
            z.extractall(vendor.parent)
    requests = {
      'Plachta/Seed-VC': ['DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth','config_dit_mel_seed_uvit_whisper_small_wavenet.yml'],
      'funasr/campplus': ['campplus_cn_common.bin'],
      'nvidia/bigvgan_v2_22khz_80band_256x': ['config.json','bigvgan_generator.pt'],
      'openai/whisper-small': ['config.json','preprocessor_config.json','model.safetensors'],
      'hexgrad/Kokoro-82M': ['config.json','kokoro-v1_0.pth','voices/jf_alpha.pt','voices/jf_nezumi.pt'],
    }
    manifest = {'seed_source_commit':commit,'seed_vendor':str(vendor),'seed_source_sha256':sha(archive),'repositories':{},'files':[]}
    jobs=[]
    for repo,names in requests.items():
        metadata=json.loads(get('https://huggingface.co/api/models/'+repo+'?blobs=true',DOWNLOADS/(repo.replace('/','--')+'.json'),8_000_000).read_text('utf-8'))
        rev=metadata['sha']
        manifest['repositories'][repo]={'revision':rev,'local':str(MODELS/'Leva-Bilingual-v3'/repo.replace('/','--'))}
        for name in names:
            item=next(r for r in metadata['siblings'] if r['rfilename']==name)
            target=Path(manifest['repositories'][repo]['local'])/name
            expected=item.get('lfs',{}).get('sha256')
            jobs.append((repo,name,target,expected,'https://huggingface.co/'+repo+'/resolve/'+rev+'/'+name))
    def run(job):
        repo,name,target,expected,url=job
        if not target.exists() or (expected and sha(target)!=expected): get(url,target)
        actual=sha(target)
        if expected and actual!=expected: raise ValueError('hash_mismatch: '+name)
        row={'repo':repo,'name':name,'path':str(target),'sha256':actual,'lfs_hash_verified':bool(expected),'bytes':target.stat().st_size,'url':url}
        print(json.dumps({'downloaded':name,'bytes':row['bytes']}),flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        manifest['files']=list(pool.map(run,jobs))
    path=MODELS/'Leva-Bilingual-v3/manifest.json'
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'manifest':str(path),'vendor':str(vendor)}),flush=True)

if __name__=='__main__': prepare()
