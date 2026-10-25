"""Explicit experimental assets; model content style never grants host capabilities."""
from pathlib import Path
import json
import hashlib
from functools import lru_cache
from paths import DATA

TRIALS={
 'hauhau_qwen35_4b':{'label':'HauhauCS Qwen3.5 4B · Q4_K_M','file':'Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf','sha256':'79e28ecacf84e75b6056cf4059636d435aa9eb67795780f7b7dbc7d32a962741','source':'HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive'},
 'hauhau_qwen35_9b':{'label':'HauhauCS Qwen3.5 9B · Q4_K_M','file':'Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf','sha256':'2ca636d9e81d3d23ca9b60c234fe185d30ec082eeba69ce770fdb0c76559a4f5','source':'HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive'},
 'rocinante_x_12b':{'label':'Rocinante X 12B · Q4_K_M · trial','file':'TheDrummer_Rocinante-X-12B-v1-Q4_K_M.gguf','sha256':'1ca25853a19d6b15f9a94f7e5bc86f4cc88bd0c9dea12a00ea55452b4208ade6','source':'bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF'}}
REGISTRY=DATA/'model-trial-registry.json'

def records(path=None):
    try:
        value=json.loads((Path(path) if path else REGISTRY).read_text('utf8'))
        if value.get('schema')!='leva.model-registry.v1' or not isinstance(value.get('models'),dict):return {}
        return {k:v for k,v in value['models'].items() if k in TRIALS and isinstance(v,dict)
            and v.get('sha256')==TRIALS[k]['sha256'] and v.get('quant')=='Q4_K_M' and v.get('verified') is True}
    except (OSError,ValueError,TypeError,AttributeError):return {}

@lru_cache(maxsize=8)
def verify_bytes(path,mtime,size,expected):
    with Path(path).open('rb') as file:actual=hashlib.file_digest(file,'sha256').hexdigest()
    if actual!=expected:raise ValueError('trial_model_hash_changed')
    return True

def model_path(key,path=None,verify=False):
    if key not in TRIALS:raise ValueError('unknown_trial_model')
    row=records(path).get(key)
    if not row:raise ValueError('trial_model_unverified_or_missing')
    target=Path(row.get('path',''))
    if not target.is_absolute() or str(target).startswith(('\\\\','//')) or target.name!=TRIALS[key]['file'] or not target.is_file():raise ValueError('trial_model_unavailable')
    if target.stat().st_size!=row.get('bytes'):raise ValueError('trial_model_size_changed')
    if verify:
        info=target.stat();verify_bytes(str(target),info.st_mtime_ns,info.st_size,TRIALS[key]['sha256'])
    return target

def choices(mode):
    if mode not in ('assistant','chat','secret','companion_avatar'):raise ValueError('invalid_workspace')
    rows={};known=records()
    for key,profile in TRIALS.items():
        row=known.get(key,{})
        rating='discouraged' if mode=='assistant' else row.get('ratings',{}).get(mode,'pending')
        prefix={'recommended':'(Direkomendasikan)','balanced':'(Seimbang)','discouraged':'(Tidak Direkomendasikan)'}.get(rating,'(Belum dinilai)')
        try:model_path(key);available=True
        except ValueError:available=False
        rows[key]=prefix+' '+profile['label']+' · Eksperimental'+(' · percakapan saja, tanpa agent' if mode=='assistant' else '')+(' · belum tersedia' if not available else '')
    return rows

def resolve(mode,selected,*,opt_in,fallback=None):
    """Local-only selection. Never silently change model or permission policy."""
    if mode not in ('assistant','chat','secret','companion_avatar'):raise ValueError('invalid_workspace')
    if selected not in TRIALS:raise ValueError('unknown_trial_model')
    if not opt_in:raise ValueError('experimental_model_opt_in_required')
    try:path=model_path(selected,verify=True)
    except ValueError as error:
        return {'status':'unavailable','selected_model':selected,'fallback_model':fallback,
            'fallback_requires_confirmation':True,'reason':str(error),'tool_policy':'none','provider':'local'}
    return {'status':'ready','selected_model':selected,'path':str(path),'provider':'local',
        'tool_policy':'none','experimental':True,'context_tested':records()[selected].get('context_tested',0)}
