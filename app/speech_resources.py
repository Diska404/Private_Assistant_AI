"""Explicit speech-device policy. UUIDs avoid CUDA/nvidia-smi index mismatches."""
import csv
import subprocess

GPU_CHOICES = {'rtx5070': 'RTX 5070', 'rtx4050': 'RTX 4050', 'dual':'Dual · encoder 4050 + decoder 5070', 'auto':'Ikuti GPU pada rute percakapan'}
ASR_CHOICES = {'qwen_asr_06b': 'Qwen3-ASR 0.6B · GPU',
               'qwen_asr_17b': 'Qwen3-ASR 1.7B · GPU',
               'whisper_cpu': 'Whisper tiny/small · CPU · kompatibilitas'}
# Keep this worker policy standalone: external ASR/TTS environments do not load GUI modules.
AGENT_CHOICES = {'qwen4b': 'Qwen3.5 4B · Q4_K_M', 'saluki': '(Direkomendasikan) Saluki 27B · IQ2 mix', 'qwen35b': 'Qwen3.6 35B A3B · Q4 · tanpa LoRA', 'minicpm2b': '(Tidak Direkomendasikan) MiniCPM5 2B · Q8 · percakapan ringan · percakapan saja, tanpa agent', 'translator2b': '(Tidak Direkomendasikan) Gemma 4 E2B · Q8 · bahasa · percakapan saja, tanpa agent'}
from personal_models import PROFILES as PERSONAL_MODELS,choice_label as personal_choice_label
AGENT_CHOICES.update({key:personal_choice_label(key,'assistant') for key in PERSONAL_MODELS})
AGENT_GPU_CHOICES = {'auto':'Ikuti GPU pada rute', 'rtx4050':'RTX 4050', 'rtx5070':'RTX 5070', 'dual':'Dual GPU · pembagian layer'}

def agent_mode(route, preference='auto'):
    if preference not in AGENT_GPU_CHOICES:raise ValueError('invalid_agent_gpu')
    if route['gpu']=='none':return None
    return route['local_mode'] if preference=='auto' else {'rtx4050':'gpu4050','rtx5070':'gpu5070','dual':'dual'}[preference]

def pipeline_gpu(route, engine, preference='auto'):
    """Explicit engine selection overrides the route; disabling AI still wins."""
    if engine not in ('asr','tts'):raise ValueError('invalid_pipeline_engine')
    gpu=route['gpu']
    if gpu=='none':raise ValueError('pipeline_ai_disabled')
    if gpu not in ('rtx4050','rtx5070','dual'):raise ValueError('invalid_speech_gpu')
    allowed=('auto','rtx4050','rtx5070','dual') if engine=='asr' else ('auto','rtx4050','rtx5070')
    if preference not in allowed:raise ValueError('invalid_speech_gpu')
    if preference!='auto':return preference
    # audio.cpp v0.9.2 cannot split a TTS model. In the dual pipeline TTS has
    # an explicit 5070 assignment, alongside the genuinely split ASR/LLM.
    return 'rtx5070' if gpu=='dual' and engine=='tts' else gpu

def select_asr_devices(rows, model, preference):
    if model not in ('qwen_asr_06b','qwen_asr_17b'):raise ValueError('invalid_asr_model')
    if preference!='dual':return [select_gpu(rows,2200 if model=='qwen_asr_06b' else 5000,preference)]
    # Fixed explicit map, not device_map=auto (which can silently use one GPU/CPU).
    minima=(1000,1800) if model=='qwen_asr_06b' else (2200,4500)
    selected=[]
    for name,minimum in zip(('RTX 4050','RTX 5070'),minima):
        matches=[r for r in rows if name in r['name']]
        if len(matches)!=1:raise ValueError('speech_dual_gpu_missing')
        if matches[0]['free_mib']<minimum:raise ValueError('speech_dual_gpu_headroom_unavailable')
        selected.append(matches[0])
    if len({r['uuid'] for r in selected})!=2:raise ValueError('speech_dual_gpu_missing')
    return selected

def gpu_rows():
    result = subprocess.run(['nvidia-smi', '--query-gpu=uuid,name,memory.free', '--format=csv,noheader,nounits'],
        capture_output=True, text=True, timeout=8, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise ValueError('speech_gpu_unavailable')
    return [{'uuid':r[0].strip(), 'name':r[1].strip(), 'free_mib':int(r[2])}
            for r in csv.reader(result.stdout.splitlines()) if len(r)==3]

def select_gpu(rows, minimum, preference='auto', preferred='RTX 4050'):
    if preference not in ('auto','rtx4050','rtx5070'): raise ValueError('invalid_speech_gpu')
    name = {'rtx4050':'RTX 4050','rtx5070':'RTX 5070'}.get(preference)
    candidates = [r for r in rows if any(n in r['name'] for n in ('RTX 4050','RTX 5070'))
                  and (not name or name in r['name'])]
    for row in sorted(candidates,key=lambda r:(preferred not in r['name'],-r['free_mib'])):
        if row['free_mib'] >= minimum: return row
    raise ValueError('speech_gpu_headroom_unavailable')
