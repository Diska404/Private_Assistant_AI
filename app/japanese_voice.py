"""Offline Japanese base TTS, reusing the verified Kokoro/Misaki research assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from voice_packs import MODELS,DATA


def synthesize_japanese(text,output,cache):
    manifest=json.loads((MODELS/'Leva-Bilingual-v3/manifest.json').read_text('utf-8'))
    files=[r for r in manifest['files'] if r['repo']=='hexgrad/Kokoro-82M']
    stamp=tuple((r['path'],Path(r['path']).stat().st_size,Path(r['path']).stat().st_mtime_ns) for r in files)
    context=cache.get('kokoro')
    reused=bool(context and context['stamp']==stamp)
    if not reused:
        for row in files:
            with Path(row['path']).open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=row['sha256']:raise ValueError('japanese_asset_mismatch')
        listing=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name','--format=csv,noheader'],text=True,creationflags=0x08000000)
        devices=[r.split(',',1)[0].strip() for r in listing.splitlines() if 'RTX 4050' in r]
        if len(devices)!=1:raise ValueError('candidate_gpu_unavailable')
        os.environ.update(CUDA_VISIBLE_DEVICES=devices[0],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
            HF_HOME=str(DATA/'cache/hf-leva-bilingual'),HF_HUB_DISABLE_TELEMETRY='1')
        import torch
        torch.set_num_threads(4)
        if not torch.cuda.is_available() or 'RTX 4050' not in torch.cuda.get_device_name(0):raise ValueError('candidate_gpu_unavailable')
        from kokoro import KModel
        from misaki.ja import JAG2P
        folder=Path(manifest['repositories']['hexgrad/Kokoro-82M']['local'])
        model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(folder/'config.json'),model=str(folder/'kokoro-v1_0.pth')).to('cuda:0').eval()
        voice=torch.load(folder/'voices/jf_alpha.pt',map_location='cpu',weights_only=True)
        context={'stamp':stamp,'model':model,'voice':voice,'g2p':JAG2P(version='cutlet'),'torch':torch}
        cache['kokoro']=context
    import soundfile as sf
    import numpy as np
    torch=context['torch']
    # G2P expansion varies with kanji; split again if a segment exceeds the engine budget.
    def generate(value):
        phonemes,_=context['g2p'](value.replace('四時','よじ'))
        if '❓' in phonemes:raise ValueError('unsupported_japanese_phonemes')
        if not phonemes:return []
        if len(phonemes)>490:
            if len(value)<2:raise ValueError('japanese_phonemes_too_long')
            middle=len(value)//2
            return generate(value[:middle])+generate(value[middle:])
        torch.manual_seed(20261019)
        with torch.inference_mode():audio=context['model'](phonemes,context['voice'][len(phonemes)-1],speed=1.0).numpy()
        return [audio]
    pieces=generate(text)
    if not pieces:raise ValueError('empty_japanese_audio')
    audio=np.concatenate(pieces)
    sf.write(output,audio,24000,subtype='PCM_16')
    torch.cuda.synchronize()
    return {'base_engine':'Kokoro-82M','base_voice':'jf_alpha','japanese_model_reused':reused}
