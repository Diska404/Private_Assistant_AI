"""Local VRM allowlist. GLB data is never an executable plugin or filesystem path API."""
import hashlib
import json
from pathlib import Path
import struct
from functools import lru_cache
from paths import DATA
FOLDER=DATA/'avatar-assets'
MAX_MODEL=64*1024*1024
LOCAL_LEVA_FOLDER=Path(r'D:\AI\AI Lokal Asisten\Model Avatar Leva')

def inspect(raw):
    if not 20<len(raw)<=MAX_MODEL or raw[:4]!=b'glTF':raise ValueError('avatar_requires_glb_vrm')
    version,total=struct.unpack_from('<II',raw,4)
    length,kind=struct.unpack_from('<II',raw,12)
    if version!=2 or total!=len(raw) or kind!=0x4e4f534a or not 0<length<=2*1024*1024:raise ValueError('invalid_avatar_glb')
    doc=json.loads(raw[20:20+length]);ext=doc.get('extensions',{})
    if not ('VRMC_vrm' in ext or 'VRM' in ext):raise ValueError('avatar_vrm_metadata_missing')
    for group in ('images','buffers'):
        if any(row.get('uri') for row in doc.get(group,[])):raise ValueError('avatar_external_resources_not_allowed')
    if len(doc.get('nodes',[]))>1000 or len(doc.get('materials',[]))>100 or sum(r.get('count',0) for r in doc.get('accessors',[]))>8000000:raise ValueError('avatar_complexity_limit')
    return ext.get('VRMC_vrm',ext.get('VRM',{})).get('meta',{})

@lru_cache(maxsize=4)
def _read(path,mtime,size,expected):
    raw=Path(path).read_bytes();inspect(raw)
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('avatar_model_hash_changed')
    return raw

def manifest(key):
    name={'pixiv_sample':'sample-manifest.json','pixiv_polished':'polished-sample-manifest.json','custom':'custom-manifest.json','leva_original':'leva-original-manifest.json'}.get(key)
    if not name:raise ValueError('unknown_avatar_model')
    try:row=json.loads((FOLDER/name).read_text('utf8'))
    except (OSError,ValueError):raise ValueError('avatar_model_unavailable') from None
    path=Path(row['path'])
    allowed=LOCAL_LEVA_FOLDER if key=='leva_original' else FOLDER
    if path.parent.resolve()!=allowed.resolve() or not path.is_file():raise ValueError('avatar_model_unavailable')
    if key=='leva_original' and (row.get('source_read_only') is not True or row.get('asset_identity')!='Leva GFL2'):
        raise ValueError('avatar_source_policy_missing')
    info=path.stat();_read(str(path),info.st_mtime_ns,info.st_size,row['sha256'])
    return row

def read(key):
    row=manifest(key);path=Path(row['path']);info=path.stat()
    return _read(str(path),info.st_mtime_ns,info.st_size,row['sha256'])

def choices():
    rows={'placeholder':'Placeholder orisinal · 2D'}
    for key in ('leva_original','pixiv_sample','pixiv_polished','custom'):
        try:rows[key]=manifest(key)['label']
        except (ValueError,KeyError,OSError):pass
    return rows

def register_local_leva(path):
    """Desktop-only registration of the supplied source; no rewrite/copy/conversion."""
    path=Path(path).resolve()
    if path.parent!=LOCAL_LEVA_FOLDER.resolve() or path.suffix.lower()!='.vrm':raise ValueError('invalid_local_leva_source')
    raw=path.read_bytes();meta=inspect(raw)
    if meta.get('title',meta.get('name','')).strip().lower()!='leva':raise ValueError('local_leva_identity_not_declared')
    if meta.get('allowedUserName')!='Everyone':raise ValueError('avatar_usage_not_allowed')
    row={'id':'leva_original','label':'Leva GFL2 · VRM asli · tanpa modifikasi','path':str(path),
         'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'meta':meta,'source_read_only':True,
         'asset_identity':'Leva GFL2','final_leva':False,'source':'user_downloaded_local_vrm',
         'usage':'private_noncommercial_avatar','modification_allowed':False,'redistribution_allowed':False}
    FOLDER.mkdir(parents=True,exist_ok=True)
    (FOLDER/'leva-original-manifest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    return row

def upload(raw):
    meta=inspect(raw);FOLDER.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(raw).hexdigest();target=FOLDER/(digest+'.vrm')
    target.write_bytes(raw)
    label=str(meta.get('name',meta.get('title','Avatar pribadi')))[:60]
    row={'id':'custom','label':label+' · VRM pribadi','path':str(target),'sha256':digest,'bytes':len(raw),
         'meta':meta,'final_leva':False,'source':'user_uploaded_private'}
    (FOLDER/'custom-manifest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    return {'id':'custom','label':row['label'],'bytes':len(raw)}
