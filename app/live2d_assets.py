"""Private Cubism installation. Only hash-pinned manifest members are served."""
import hashlib,json,mimetypes
from functools import lru_cache
from pathlib import Path
ROOT=Path(r'D:\AI\AI Lokal Asisten\Github\Live2D-SDK')

def manifest():
    try:
        row=json.loads((ROOT/'leva-runtime-manifest.json').read_text(encoding='utf8'))
        if row.get('model_is_leva') is not False or not row.get('files'):raise ValueError()
        return row
    except (OSError,ValueError):raise ValueError('live2d_local_runtime_unavailable') from None

@lru_cache(maxsize=24)
def _read(path,mtime,size,digest):
    if not 0<size<=32*1024*1024:raise ValueError('live2d_resource_size')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('live2d_resource_hash_changed')
    return raw

def read(name):
    row=manifest();item=row['files'].get(name)
    if not item:raise ValueError('unknown_live2d_resource')
    path=(ROOT/item['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():raise ValueError('live2d_resource_unavailable')
    stat=path.stat();raw=_read(str(path),stat.st_mtime_ns,stat.st_size,item['sha256'])
    return raw,{'js':'text/javascript','json':'application/json','png':'image/png','moc3':'application/octet-stream'}.get(path.suffix[1:],'application/octet-stream')

def status():
    try:
        row=manifest()
        if not all((ROOT/item['path']).is_file() for item in row['files'].values()):raise ValueError()
        return {'available':True,'sdk_version':row['sdk_version'],'model':row['model'],'model_is_leva':False,'native_web_renderer':True}
    except (ValueError,OSError,KeyError):return {'available':False,'model_is_leva':False,'native_web_renderer':True}
