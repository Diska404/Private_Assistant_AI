"""Pinned Saluki target with mutually exclusive plain, MTP or DFlash2 decoding."""
import hashlib
import json
from pathlib import Path

from hybrid_engine import LocalEngine,EngineError

MODEL_ROOT=Path(r'D:\AI\AI Lokal Asisten\AI Models\Saluki-27B')
MODEL_NAME='Underdog-Saluki-27B-1.0-IQ2-mix-MTP.gguf'
DRAFT_NAME='Qwen3.8-27B-DFlash2-Q4_K_M.gguf'
SERVER=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4\llama-server.exe')
ACCELERATIONS=('auto','plain','mtp','dflash')

def chosen_acceleration(requested,mode='gpu5070'):
    if requested not in ACCELERATIONS:raise EngineError('invalid_saluki_acceleration')
    if requested!='auto':return requested
    try:
        profile=json.loads((MODEL_ROOT/'runtime-profile.json').read_text('utf-8'))
        if profile.get('blocked_auto'):
            raise EngineError('saluki_benchmark_pending')
        selected=profile['recommended_acceleration']
        if selected not in ('plain','mtp','dflash') or not profile['measured']:raise ValueError()
        # Historical measurements were on 5070 only. Do not extrapolate speculative
        # speedups or compatibility to a different topology without its own evidence.
        if profile.get('local_mode','gpu5070')!=mode:return 'plain'
        return selected
    except (OSError,ValueError,KeyError,TypeError):return 'plain'

def verify(name):
    try:
        record=json.loads((MODEL_ROOT/name.removesuffix('.gguf')/'manifest.json').read_text('utf-8'))
        path=MODEL_ROOT/name
        if not record['verified'] or path.stat().st_size!=record['bytes']:raise ValueError()
        with path.open('rb') as f:
            if f.read(4)!=b'GGUF':raise ValueError()
            f.seek(0); digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=record['sha256']:raise ValueError()
        return record
    except (OSError,ValueError,KeyError,TypeError):raise EngineError('saluki_assets_missing_or_unverified') from None

class SalukiEngine(LocalEngine):
    def __init__(self,data_dir,*,acceleration='auto',system='',max_output_tokens=512,mode='gpu5070'):
        self.acceleration=chosen_acceleration(acceleration,mode)
        extra=['--cache-type-k','q8_0','--cache-type-v','q8_0','--batch-size','512','--ubatch-size','512']
        if self.acceleration=='mtp':extra+=['--spec-type','draft-mtp','--spec-draft-n-max','2']
        elif self.acceleration=='dflash':
            extra+=['--spec-type','draft-dflash','--spec-draft-model',str(MODEL_ROOT/DRAFT_NAME),'--spec-draft-n-max','7']
        super().__init__(SERVER,MODEL_ROOT/MODEL_NAME,Path(data_dir),mode=mode,system=system,
            context_size=8192,max_output_tokens=max_output_tokens,sampling={'temperature':0},
            extra_server_args=tuple(extra),startup_timeout=180)
        self.assets=[]

    def start(self):
        if self.process:return
        self.assets=[verify(MODEL_NAME)]
        if self.acceleration=='dflash':self.assets.append(verify(DRAFT_NAME))
        super().start()
