"""Local candidate A adapter, reusing the proven v3 checkpoint migration and settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from voice_packs import MODELS, DATA
_CONTEXT=None

def asset_stamp(paths):
    return tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)

def synthesize(context,source,folder,reused,started=None):
    import time
    if asset_stamp(context['paths'])!=context['stamp']:raise ValueError('candidate_assets_changed')
    args=context['args'];torch=context['torch'];engine=context['engine']
    args.source=str(source);args.output=str(folder/'converted')
    started=time.perf_counter() if started is None else started
    torch.manual_seed(20261019)
    with torch.inference_mode():engine.main(args)
    torch.cuda.synchronize()
    result=Path(args.output)/f"vc_{source.name.split('.')[0]}_reference_A_1.0_30_0.7.wav"
    return result,{'conversion_and_load_seconds':round(time.perf_counter()-started,3),
        'gpu_name':torch.cuda.get_device_name(0),'reference_id':'A','streaming':False,
        'seed_model_reused':reused,'diffusion_steps':30}

def convert(source,folder):
    global _CONTEXT
    if _CONTEXT is not None:return synthesize(_CONTEXT,source,folder,True)
    manifest=json.loads((MODELS/'Leva-Bilingual-v3/manifest.json').read_text('utf-8'))
    profile=json.loads((MODELS/'Leva-GFL2/SeedVC-bilingual-candidate-v3/profile.json').read_text('utf-8'))
    prompt=next(p for p in profile['prompts'] if p['id']=='A')
    reference=MODELS/'Leva-GFL2/SeedVC-bilingual-candidate-v3/reference_A.wav'
    def sha(path):
        with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    if sha(reference)!=prompt['sha256']:raise ValueError('candidate_reference_mismatch')
    for row in manifest['files']:
        if row['repo']!='hexgrad/Kokoro-82M' and sha(row['path'])!=row['sha256']:
            raise ValueError('candidate_asset_mismatch')
    listing=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name','--format=csv,noheader'],text=True,creationflags=0x08000000)
    devices=[r.split(',',1)[0].strip() for r in listing.splitlines() if 'RTX 4050' in r]
    if len(devices)!=1:raise ValueError('candidate_gpu_unavailable')
    os.environ.update(CUDA_VISIBLE_DEVICES=devices[0],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        HF_HOME=str(DATA/'cache/hf-leva-bilingual'),HF_HUB_CACHE=str(DATA/'cache/hf-leva-bilingual/hub'),
        NUMBA_CACHE_DIR=str(DATA/'cache/numba-openvoice'),HF_HUB_DISABLE_TELEMETRY='1')
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or 'RTX 4050' not in torch.cuda.get_device_name(0):
        raise ValueError('candidate_gpu_unavailable')
    import yaml
    sys.path.insert(0,manifest['seed_vendor'])
    import inference as engine
    local={repo:Path(meta['local']) for repo,meta in manifest['repositories'].items()}
    def asset(repo,model_filename='pytorch_model.bin',config_filename=None):
        model=str(local[repo]/model_filename)
        return (model,str(local[repo]/config_filename)) if config_filename else model
    engine.load_custom_model_from_hf=asset
    def checkpoint(models,optimizer,path,**kwargs):
        state=torch.load(path,map_location='cpu',weights_only=True)
        for key in models:
            parameters={k.removeprefix('module.'):v for k,v in state['net'][key].items()}
            expected=models[key].state_dict()
            if key=='cfm':
                for name in ('estimator.t_embedder.freqs','estimator.t_embedder2.freqs'):
                    if name not in parameters and name in expected:parameters[name]=expected[name]
                name='estimator.input_pos'
                if name in parameters and parameters[name].shape!=expected[name].shape:
                    value=parameters[name]
                    if not torch.equal(value,torch.arange(value.numel(),dtype=value.dtype)):
                        raise ValueError('candidate_checkpoint_mismatch')
                    parameters[name]=expected[name]
                if 'estimator.f0_embedder.weight' not in expected:parameters.pop('estimator.f0_embedder.weight',None)
            models[key].load_state_dict(parameters,strict=True)
        return models,optimizer,0,0
    engine.load_checkpoint=checkpoint
    config=yaml.safe_load((local['Plachta/Seed-VC']/'config_dit_mel_seed_uvit_whisper_small_wavenet.yml').read_text('utf-8'))
    config['model_params']['vocoder']['name']=str(local['nvidia/bigvgan_v2_22khz_80band_256x'])
    config['model_params']['speech_tokenizer']['name']=str(local['openai/whisper-small'])
    config_path=folder/'seed-config.yml'
    config_path.write_text(yaml.safe_dump(config),encoding='utf-8')
    args=argparse.Namespace(f0_condition=False,fp16=True,
        checkpoint=str(local['Plachta/Seed-VC']/'DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth'),
        config=str(config_path),auto_f0_adjust=False,semi_tone_shift=0,length_adjust=1.0,
        diffusion_steps=30,inference_cfg_rate=0.7,source=str(source),target=str(reference),output=str(folder/'converted'))
    started=time.perf_counter()
    loaded=engine.load_models(args)
    engine.load_models=lambda _:loaded
    paths=[reference,MODELS/'Leva-Bilingual-v3/manifest.json',MODELS/'Leva-GFL2/SeedVC-bilingual-candidate-v3/profile.json']
    paths.extend(Path(r['path']) for r in manifest['files'] if r['repo']!='hexgrad/Kokoro-82M')
    _CONTEXT={'args':args,'torch':torch,'engine':engine,'paths':paths,'stamp':asset_stamp(paths)}
    return synthesize(_CONTEXT,source,folder,False,started)
