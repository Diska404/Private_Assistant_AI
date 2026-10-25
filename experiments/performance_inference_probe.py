"""Bounded, synthetic validation of the unchanged local runtime; no production DB."""
import json
import os
from pathlib import Path
import sys
import threading
import time

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from hybrid_engine import LocalEngine
from probe_flash_next_v034 import stream
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\performance-20261024')

def main():
    proof={'status':'starting','synthetic_prompts_only':True,'models_or_preferences_changed':False,
        'model':'Qwen3.5 4B Q4_K_M','context':8192,'gpu':'RTX 5070','cases':[],'samples':[]}
    def save():(OUT/'inference-validation.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    if psutil.virtual_memory().available<8*1024**3:
        proof['status']='NOT TESTED: insufficient RAM headroom';save();return
    engine=LocalEngine(Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4\llama-server.exe'),
        Path(r'D:\AI\AI Lokal Asisten\AI Models\Qwen3.5-4B\Qwen3.5-4B-Q4_K_M.gguf'),
        OUT/'inference-runtime',mode='gpu5070',context_size=8192,max_output_tokens=512,
        thinking_budget=0,startup_timeout=75,extra_server_args=('--cache-type-k','q8_0','--cache-type-v','q8_0'))
    stop=threading.Event();started=time.monotonic()
    def monitor():
        while not stop.wait(1):
            memory=psutil.virtual_memory()
            proof['samples'].append({'seconds':round(time.monotonic()-started,2),'available_ram_bytes':memory.available,'cpu_percent':psutil.cpu_percent()})
            if memory.available<4*1024**3 or time.monotonic()-started>180:
                proof['guard']='ram_headroom' if memory.available<4*1024**3 else 'time_limit'
                engine.close();return
    worker=threading.Thread(target=monitor,daemon=True);worker.start()
    try:
        engine.start();proof['load_seconds']=engine.load_seconds
        proof['gpu_buffers_mib']=engine.model_gpu_buffers_mib;save()
        for phase,prompt in [('cold_first','Berapa 17 dikali 23? Jawab hanya angkanya.'),
            ('warm_repeat_1','Berapa 17 dikali 23? Jawab hanya angkanya.'),
            ('warm_repeat_2','Berapa 17 dikali 23? Jawab hanya angkanya.'),
            ('warm_changed','Berapa 19 dikali 21? Jawab hanya angkanya.')]:
            row=stream(engine,prompt);row['phase']=phase
            row['expected_present']=('399' if phase=='warm_changed' else '391') in row['text']
            proof['cases'].append(row);save()
        proof['status']='completed' if all(r['expected_present'] and r['finish_reason']=='stop' for r in proof['cases']) else 'response_unverified'
    except Exception as error:proof.update(status='failed',error=type(error).__name__+':'+str(error)[:240])
    finally:
        stop.set();worker.join(2);engine.close();proof['owned_worker_released']=engine.process is None
        proof['total_seconds']=round(time.monotonic()-started,2);save()
    print(json.dumps({k:v for k,v in proof.items() if k!='samples'},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
