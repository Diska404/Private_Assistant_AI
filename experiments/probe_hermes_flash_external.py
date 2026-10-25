"""Guarded Flash-Next external-runtime diagnostic; never changes Hermes config."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from hybrid_engine import LocalEngine
from probe_flash_next_v034 import MODEL, SERVER, stream

OUT = Path(r'D:\AI\AI Lokal Asisten\Leva\verification\hermes-flash-repair-20261024')
HOME = Path(r'C:\Users\Raizei\AppData\Local\hermes')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # A previous diagnostic restored the file; reload restores its in-memory copy too.
    key = (HOME/'runtimes/llamacpp/.api_key').read_text('utf8').strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('http://127.0.0.1:18434/models?reload=1',
        headers={'Authorization': 'Bearer '+key})
    with opener.open(req, timeout=20) as response:
        rows = json.load(response)['data']
    model = next(r for r in rows if r['id'] == 'Qwen3.8-Flash-Next-UD-IQ4_XS')
    args = model.get('status', {}).get('args', [])
    proof = {'status': 'starting', 'managed_preset_restored': '65536' in args,
        'managed_model_status': model.get('status', {}).get('value'),
        'context_size': 4096, 'runtime': str(SERVER), 'cases': [], 'resources': []}
    def save():
        (OUT/'external-probe.json').write_text(json.dumps(proof, indent=2, ensure_ascii=False), encoding='utf8')
    save()
    if model.get('status', {}).get('value') != 'unloaded':
        proof['status'] = 'managed_model_busy'; save(); return
    if psutil.virtual_memory().available < 8*1024**3:
        proof['status'] = 'insufficient_available_ram'; save(); return
    os.environ['GGML_CUDA_NO_PINNED'] = '1'  # This diagnostic and its child only.
    engine = LocalEngine(SERVER, MODEL, OUT/'external-dual', mode='dual',
        context_size=4096, max_output_tokens=32, thinking_budget=0, startup_timeout=210,
        extra_server_args=('--load-mode','mmap','--lazy-mode','on','--no-host',
            '--cpu-moe','--override-tensor','per_layer_token_embd=CPU',
            '--moe-cache-mib','256','--no-repack','--no-warmup',
            '--batch-size','128','--ubatch-size','64','--no-context-shift',
            '--gpu-layers','99','--fit','off','--tensor-split','3,1'))
    done = threading.Event()
    started = time.monotonic()
    def guard():
        while not done.wait(1):
            memory = psutil.virtual_memory()
            proof['resources'].append({'seconds': round(time.monotonic()-started, 2),
                'available_ram_bytes': memory.available, 'cpu_percent': psutil.cpu_percent()})
            if memory.available < 2*1024**3 or time.monotonic()-started > 360:
                proof['guard'] = 'ram_below_2GiB' if memory.available < 2*1024**3 else 'time_limit'
                save(); engine.close(); return
    thread = threading.Thread(target=guard, daemon=True); thread.start()
    try:
        engine.start()
        proof.update(status='loaded', startup_seconds=round(time.monotonic()-started, 2),
            devices=engine.devices, gpu_buffers_mib=engine.model_gpu_buffers_mib,
            gpu_loaded=engine.gpu_snapshot_loaded)
        save(); print(json.dumps({'status':'loaded','seconds':proof['startup_seconds']}), flush=True)
        for prompt in ('Jawab persis: Halo.', 'Berapa hasil 17 dikali 23? Jawab angka saja.'):
            result=stream(engine, prompt); proof['cases'].append(result);save()
            print(json.dumps(result, ensure_ascii=True), flush=True)
        proof['status']='completed' if all(r.get('finish_reason')=='stop' for r in proof['cases']) else 'incomplete'
    except Exception as error:
        proof.update(status='failed', error=type(error).__name__+': '+str(error)[:500])
    finally:
        done.set(); thread.join(2); engine.close()
        proof['owned_worker_released']=engine.process is None
        proof['elapsed_seconds']=round(time.monotonic()-started, 2);save()
        print(json.dumps({k:v for k,v in proof.items() if k not in ('resources','gpu_loaded')}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
