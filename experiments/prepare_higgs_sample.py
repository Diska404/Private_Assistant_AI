"""Prepare a pinned, isolated Higgs/audio.cpp sample runtime on drive D."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

DATA = Path(r'D:\AI\AI Lokal Asisten\Leva')
MODELS = Path(r'D:\AI\AI Lokal Asisten\AI Models\Higgs-TTS-3-GGUF')
OUT = DATA / 'verification/higgs-naturalness-20261020'
RUNTIME = DATA / 'runtime/audio-cpp-higgs-v092'
DOWNLOADS = DATA / 'downloads/higgs-naturalness-20261020'

def metadata(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Leva-local-sample/1.0'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def download(job):
    url, dest, expected, size = job
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == size and sha(dest) == expected:
        return {'path':str(dest),'sha256':expected,'bytes':size,'url':url,'reused':True}
    partial = dest.with_name(dest.name+'.part')
    print(json.dumps({'downloading':dest.name,'bytes':size}), flush=True)
    with dest.with_suffix(dest.suffix+'.download.log').open('w',encoding='utf-8') as log:
        subprocess.run(['curl.exe','-4','-fL','--retry','2','--connect-timeout','25',
            '--max-time','1800', '-o',str(partial),url],
            check=True, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=0x08000000)
    actual = sha(partial)
    if partial.stat().st_size != size or actual != expected:
        raise RuntimeError('download_verification_failed: '+dest.name)
    partial.replace(dest)
    print(json.dumps({'verified':dest.name,'sha256':actual}), flush=True)
    return {'path':str(dest),'sha256':actual,'bytes':size,'url':url}

def main():
    for folder in (MODELS, OUT, RUNTIME, DOWNLOADS): folder.mkdir(parents=True,exist_ok=True)
    release = metadata('https://api.github.com/repos/0xShug0/audio.cpp/releases/latest')
    (OUT/'release.json').write_text(json.dumps(release,indent=2),encoding='utf-8')
    repo = metadata('https://huggingface.co/api/models/audio-cpp/audio.cpp-gguf?blobs=true')
    rev = repo['sha']
    name = 'Higgs-Audio-v3-TTS-4B-GGUF/higgs-audio-v3-tts-4b-q8_0.gguf'
    model = next(row for row in repo['siblings'] if row['rfilename']==name)
    jobs = [('https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/'+rev+'/'+name,
             MODELS/Path(name).name,model['lfs']['sha256'],model['lfs']['size'])]
    for suffix in ('-bin-windows-x64-cuda13.3.zip','-cudart-windows-x64-cuda13.3.zip'):
        asset = next(a for a in release['assets'] if a['name'].endswith(suffix))
        jobs.append((asset['browser_download_url'], DOWNLOADS/asset['name'],
                     asset['digest'].removeprefix('sha256:'),asset['size']))
    manifest = {'release':release['tag_name'],'model_revision':rev,'model_repo':repo['id'],
                'precision':'Q8_0','files':[],'runtime':str(RUNTIME),'model':str(jobs[0][1])}
    (OUT/'download-plan.json').write_text(json.dumps(manifest|{'jobs':[{'path':str(j[1]),'bytes':j[3]} for j in jobs]},indent=2),encoding='utf-8')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        manifest['files'] = list(pool.map(download,jobs))
    for row in manifest['files'][1:]:
        with zipfile.ZipFile(row['path']) as archive:
            for member in archive.infolist():
                if not (RUNTIME/member.filename).resolve().is_relative_to(RUNTIME.resolve()):
                    raise RuntimeError('unsafe_archive_path')
            archive.extractall(RUNTIME)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'prepared':manifest}),flush=True)

if __name__=='__main__': main()
