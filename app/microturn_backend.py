"""Matched Codacus MicroTurn GGUF+LoRA protocol; no audio or desktop tools.

Protocol adapted from the author's Apache-2.0 microturn_client.py.
Exact upstream prompt and append-only ChatML completion format are preserved.
"""
import hashlib
import json
import math
from pathlib import Path
import time

from hybrid_engine import LocalEngine, DEFAULT_SERVER, EngineError

MODEL_ROOT=Path(r'D:\AI\AI Lokal Asisten\AI Models\MicroTurn-Duplex')
MODEL_NAME='Qwen3.6-35B-A3B-UD-Q4_K_M.gguf'
ADAPTER_NAME='microturn-duplex-lora.gguf'
LISTEN='<listen>'
NO_VOICE='<no voice>'
LISTEN_THRESHOLD=0.3
SYSTEM=("You are a voice assistant in a live phone call; both sides can talk at the same time. Every "
        "0.6 seconds you get what the microphone heard in that moment, as a streaming transcript fragment, or "
        "<no voice>. You reply with up to three new words to say next, or <listen> to add nothing.")

def validated_context(history,heard):
    if not isinstance(heard,str) or not heard.strip() or len(heard)>600:
        raise ValueError('invalid_tick_input')
    if not isinstance(history,(tuple,list)) or len(history)>64:
        raise ValueError('invalid_tick_history')
    pairs=[]
    for pair in history:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or not all(isinstance(v,str) and 0<len(v)<=600 for v in pair):
            raise ValueError('invalid_tick_history')
        pairs.append(pair)
    for text in [heard]+[text for pair in pairs for text in pair]:
        if '<|' in text or '|>' in text:
            raise ValueError('chat_template_token_in_input')
    return pairs

def completion_body(history,heard):
    pairs=validated_context(history,heard)
    prompt=f'<|im_start|>system\n{SYSTEM}<|im_end|>\n'
    for user,assistant in pairs:
        prompt+=f'<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n{assistant}<|im_end|>\n'
    prompt+=f'<|im_start|>user\n{heard}<|im_end|>\n<|im_start|>assistant\n'
    return {'prompt':prompt,'n_predict':64,'temperature':0,'stop':['<|im_end|>'],
            'cache_prompt':True,'n_probs':8,'id_slot':0}

def listen_probability(response):
    try:
        top=response['completion_probabilities'][0]['top_logprobs']
        candidates=[(int(p['id']),str(p['token']),float(p['logprob'])) for p in top]
    except (KeyError,IndexError,TypeError,ValueError):
        raise EngineError('microturn_probabilities_unavailable') from None
    if not candidates or any(not math.isfinite(p) for _,_,p in candidates):
        raise EngineError('microturn_invalid_probabilities')
    ids=[ident for ident,token,_ in candidates if token.startswith('<')]
    probability=sum(math.exp(p) for _,token,p in candidates if token.startswith('<'))
    if probability>1.0001: raise EngineError('microturn_invalid_probabilities')
    return probability,ids

def microturn_tick(request,history,heard):
    body=completion_body(history,heard)
    started=time.monotonic()
    result=request('/completion',body,timeout=30)
    output=result.get('content','').strip()
    probability,ids=listen_probability(result)
    retried=False
    first_timings=result.get('timings',{})
    if output.startswith('<') and probability<LISTEN_THRESHOLD and ids:
        body={**body,'logit_bias':[[ident,False] for ident in ids],'n_probs':0}
        result=request('/completion',body,timeout=30)
        output=result.get('content','').strip()
        retried=True
    if not output or len(output)>600 or result.get('truncated') is True:
        raise EngineError('microturn_incomplete_output')
    if '<|im_' in output: raise EngineError('microturn_invalid_output')
    return {'text':LISTEN if output.startswith('<') else output,
            'raw_output':output,'listen_probability':round(probability,6),
            'decoding_retry':retried,'backend_ms':round((time.monotonic()-started)*1000,2),
            'timings':result.get('timings',{}),'first_pass_timings':first_timings}

def verify_assets(root=MODEL_ROOT):
    try:
        manifest=json.loads((root/'manifest.json').read_text('utf-8'))
        by_name={row['name']:row for row in manifest['files']}
        records=[]
        for name in (MODEL_NAME,ADAPTER_NAME):
            path=root/name
            row=by_name[name]
            if path.stat().st_size!=row['bytes'] or not row['lfs_hash_verified']:
                raise ValueError('asset_size_or_provenance_mismatch')
            with path.open('rb') as f:
                if f.read(4)!=b'GGUF': raise ValueError('invalid_gguf')
                f.seek(0)
                digest=hashlib.file_digest(f,'sha256').hexdigest()
            if digest!=row['sha256']: raise ValueError('asset_hash_mismatch')
            records.append({'name':name,'sha256':digest,'bytes':row['bytes']})
        return records
    except (OSError,KeyError,TypeError,ValueError):
        raise EngineError('microturn_assets_missing_or_unverified') from None

def runtime_profile():
    path=MODEL_ROOT/'runtime-profile.json'
    if not path.exists():return {'mode':'gpu5070','cpu_moe_layers':24,'threads':4,'load_mode':'mmap'}
    try:
        profile=json.loads(path.read_text('utf-8'))
        return {key:profile[key] for key in ('mode','cpu_moe_layers','threads','load_mode')}
    except (OSError,ValueError,KeyError,TypeError):raise EngineError('microturn_runtime_profile_invalid') from None

class MicroTurnEngine(LocalEngine):
    def __init__(self,data_dir,*,cpu_moe_layers=None,mode=None,threads=None,load_mode=None):
        profile=runtime_profile()
        cpu_moe_layers=profile['cpu_moe_layers'] if cpu_moe_layers is None else cpu_moe_layers
        mode=profile['mode'] if mode is None else mode
        threads=profile['threads'] if threads is None else threads
        load_mode=profile['load_mode'] if load_mode is None else load_mode
        if cpu_moe_layers not in (16,20,24,28,32) or mode not in ('gpu5070','dual') or threads not in (4,8,12) or load_mode not in ('mmap','none'):
            raise EngineError('microturn_runtime_profile_invalid')
        super().__init__(DEFAULT_SERVER,MODEL_ROOT/MODEL_NAME,Path(data_dir),mode=mode,
            context_size=8192,thinking_budget=0,extra_server_args=(
                '--lora',str(MODEL_ROOT/ADAPTER_NAME),'--n-cpu-moe',str(cpu_moe_layers),
                '--ubatch-size','512','--batch-size','512','--threads',str(threads),
                '--threads-batch',str(threads),'--load-mode',load_mode),startup_timeout=240)
        self.cpu_moe_layers=cpu_moe_layers
        self.threads=threads
        self.load_mode=load_mode
        self.asset_records=[]
        self.adapter_status=None

    def start(self):
        if self.process: return
        self.asset_records=verify_assets()
        super().start()
        try:
            status=self.request('/lora-adapters',timeout=5)
            adapters=status if isinstance(status,list) else status.get('adapters',[])
            if len(adapters)!=1 or Path(adapters[0].get('path','')).name!=ADAPTER_NAME or float(adapters[0].get('scale',0))!=1:
                raise EngineError('microturn_adapter_not_applied')
            self.adapter_status=adapters
        except BaseException:
            self.close()
            raise

    def tick(self,history,heard):
        if not self.process or not self.adapter_status:
            raise EngineError('microturn_not_started')
        return microturn_tick(self.request,history,heard)
