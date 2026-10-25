"""Install an isolated official llama.cpp CUDA runtime for speculative tests."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cuda',choices=('12.4','13.4'),default='13.4');args=parser.parse_args()
    ROOT=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime')/('llamacpp-b11721-cuda'+args.cuda)
    ROOT.mkdir(parents=True,exist_ok=True)
    request=urllib.request.Request('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11721',headers={'User-Agent':'Leva'})
    with urllib.request.urlopen(request,timeout=30) as r: release=json.load(r)
    records=[a for a in release['assets'] if a['name'] in (f'llama-b11721-bin-win-cuda-{args.cuda}-x64.zip',f'cudart-llama-bin-win-cuda-{args.cuda}-x64.zip')]
    assert len(records)==2
    def get(asset):
        path=ROOT/asset['name']
        if not path.exists():
            subprocess.run(['curl.exe','-4','-fLsS','--retry','3','--connect-timeout','20','--max-time','900',
                '-o',str(path)+'.part',asset['browser_download_url']],check=True,creationflags=0x08000000)
            Path(str(path)+'.part').rename(path)
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        assert 'sha256:'+digest==asset['digest']
        return path
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: archives=list(pool.map(get,records))
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            assert all((ROOT/name).resolve().is_relative_to(ROOT.resolve()) for name in archive.namelist())
            archive.extractall(ROOT)
    (ROOT/'release.json').write_text(json.dumps({'tag':release['tag_name'],'assets':records},indent=2),encoding='utf-8')
    print(json.dumps({'installed':str(ROOT),'verified_archives':len(archives)}),flush=True)
