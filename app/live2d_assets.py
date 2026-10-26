"""Private Cubism installation. Only hash-pinned manifest members are served."""
import hashlib,json
from functools import lru_cache
from pathlib import Path
from paths import DATA
ROOT=Path(r'D:\AI\AI Lokal Asisten\Github\Live2D-SDK')
MODELS=DATA/'avatar-assets/live2d'
LOCAL_MODELS=Path(r'D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D')
CHARACTERS={'leva_ssr':('leva-ssr-manifest.json','CHA_Levva_SSR_01'),
            'leva_rig_r02':('leva-rig-r02-manifest.json','Leva_Editable_R01/runtime_initial_rig_r02c'),
            'leva_rig_r03':('leva-rig-r03-manifest.json','Leva_Advanced_R03/runtime'),
            'leva_artwork_r04a':('leva-artwork-r04a-manifest.json','Leva_Artwork_R04/R04A_v3/runtime')}

def character_manifest(key):
    if key not in CHARACTERS:raise ValueError('unknown_live2d_model')
    filename,relative_root=CHARACTERS[key]
    try:
        row=json.loads((MODELS/filename).read_text(encoding='utf8'))
        if row.get('id')!=key or row.get('source_read_only') is not True or row.get('model_is_leva') is not True:raise ValueError()
        root=Path(row['root']).resolve()
        if root!= (LOCAL_MODELS/relative_root).resolve() or not row.get('files'):raise ValueError()
        return row,root
    except (ValueError,OSError,KeyError):raise ValueError('live2d_character_unavailable') from None

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
    if name.startswith('models/'):
        parts=name.split('/',2)
        if len(parts)!=3:raise ValueError('unknown_live2d_resource')
        row,root=character_manifest(parts[1]);item=row['files'].get(parts[2]);relative=item['path'] if item else ''
    else:
        row=manifest();root=ROOT.resolve();item=row['files'].get(name);relative=item['path'] if item else ''
    if not item:raise ValueError('unknown_live2d_resource')
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('live2d_resource_unavailable')
    stat=path.stat();raw=_read(str(path),stat.st_mtime_ns,stat.st_size,item['sha256'])
    return raw,{'js':'text/javascript','json':'application/json','png':'image/png','moc3':'application/octet-stream'}.get(path.suffix[1:],'application/octet-stream')

def status():
    try:
        row=manifest()
        if not all((ROOT/item['path']).is_file() for item in row['files'].values()):raise ValueError()
        models={'hiyori':{'label':row['model'],'index':'Hiyori.model3.json','model_is_leva':False,'kind':'official_sdk_sample'}}
        for key in CHARACTERS:
            try:
                character,root=character_manifest(key)
                if all((root/item['path']).is_file() for item in character['files'].values()):
                    models[key]={k:character[k] for k in ('label','index','model_is_leva','kind')}
                    models[key]['rig_capabilities']=character.get('rig_capabilities',{})
            except (ValueError,OSError,KeyError):pass
        return {'available':True,'sdk_version':row['sdk_version'],'model':row['model'],'model_is_leva':False,'native_web_renderer':True,'models':models}
    except (ValueError,OSError,KeyError):return {'available':False,'model_is_leva':False,'native_web_renderer':True}

def choices():return {key:row['label'] for key,row in status().get('models',{}).items()}
