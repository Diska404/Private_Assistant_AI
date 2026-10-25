"""Reproduce both installed image engines on distinct GPUs; preserve original workflows."""
import concurrent.futures
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from comfy_service import ComfyService, ComfyError
from fooocus_service import FooocusService

OUT = Path(r'D:\AI\AI Lokal Asisten\Leva\verification\image-repair-v034')
FOO = Path(r'F:\AI\Fooocus_win64_2-5-0')
COMFY = Path(r'F:\AI\ComfyUI_windows_portable')
SAVE_LOCK = threading.Lock()


def save(value):
    path = OUT / 'proof.json'
    tmp = path.with_suffix('.tmp')
    with SAVE_LOCK:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
        tmp.replace(path)


def repair_config():
    path = FOO / 'Fooocus/config.txt'
    raw = path.read_text('utf-8-sig')
    try:
        json.loads(raw)
        return {'changed': False}
    except ValueError:
        # Repair only the observed missing closing checkpoint-list delimiter.
        fixed = raw.replace('"path_loras":', '],\n    "path_loras":', 1)
        parsed = json.loads(fixed)
        backup = OUT / 'fooocus-config-original.txt'
        if not backup.exists(): shutil.copy2(path, backup)
        path.write_text(json.dumps(parsed, indent=4, ensure_ascii=False), encoding='utf8')
        return {'changed': True, 'backup': str(backup), 'reason': 'missing checkpoint list closing bracket and comma'}


def run_engine(name, service, proof):
    row = proof[name] = {'started_at': time.time()}
    try:
        row['start'] = service.start()
        save(proof)
        for _ in range(120):
            state = service.status()
            if state['status'] == 'done': break
            if service.process and service.process.poll() is not None:
                raise RuntimeError('server_exited:' + str(service.process.returncode))
            time.sleep(2)
        else: raise TimeoutError('server_start_timeout')
        row['ready'] = state
        prompt = 'A tiny wooden cabin beside a quiet lake, morning sunlight, pine forest, photographic landscape'
        if name == 'comfy':
            catalog = service.catalog(category='checkpoints')
            row['catalog'] = catalog
            models = catalog['catalog']['checkpoints']['matches']
            model = next((m for m in models if 'juggernautxl_v8' in m.lower()), None)
            if not model: raise ValueError('juggernaut_checkpoint_not_in_comfy_catalog')
            prepared = service.prepare(model, prompt, width=768, height=768, steps=12, seed=231024)
            ident = prepared['workflow_id']
            row['prepared'] = prepared
            row['published'] = service.publish(ident)
            row['submitted'] = service.submit(ident)
        else:
            row['submitted'] = service.generate('juggernautXL_v8Rundiffusion.safetensors', prompt, width=768, height=768, steps=12, seed=231024)
            ident = row['submitted']['job_id']
        row['submitted_at'] = time.time()
        save(proof)
        for _ in range(450):
            try:
                result = service.poll(ident)
            except ComfyError as error:
                row['observation_errors']=row.get('observation_errors',0)+1
                row['last_observation_error']=str(error)
                if service.process and service.process.poll() is not None: raise RuntimeError('server_exited_during_generation')
                time.sleep(2)
                continue
            row['result'] = result
            if result['status'] not in ('running',): break
            time.sleep(2)
        else: raise TimeoutError('generation_timeout')
        row['finished_at'] = time.time()
        row['seconds_since_submission'] = round(row['finished_at'] - row['submitted_at'], 3)
        if result.get('task_verified') is not True: raise RuntimeError('generation_not_verified')
        if name == 'comfy':
            from PIL import Image
            verified = []
            for image in result['outputs']:
                path = COMFY / 'ComfyUI/output' / image['subfolder'] / image['filename']
                with Image.open(path) as im:
                    dimensions = im.size
                    im.verify()
                verified.append({'path': str(path), 'size': dimensions, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            if not verified: raise RuntimeError('no_saved_output')
            row['verified_files'] = verified
        row['passed'] = True
    except Exception as error:
        row.update(passed=False, error=str(error))
    finally:
        save(proof)
    return row


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--engine',choices=['both','comfy','fooocus','comfy-dual'],default='both')
    settings=parser.parse_args()
    OUT=OUT/('stream-'+settings.engine)
    OUT.mkdir(parents=True, exist_ok=True)
    proof = {'status': 'running', 'purpose': 'single image with staged denoising and VAE on distinct GPUs' if settings.engine=='comfy-dual' else 'actual installed image engine generation; parallel jobs only when both selected', 'samples': []}
    proof['config_repair'] = repair_config()
    foo = FooocusService(FOO, storage=OUT / 'fooocus')
    comfy = ComfyService(COMFY, storage=OUT / 'comfy')
    if settings.engine=='comfy-dual':
        original_command=comfy.server_command
        def dual_command(*args):
            command=original_command(*args)
            command[command.index('--cuda-device')]='--default-device'
            return command
        comfy.server_command=dual_command
        original_prepare=comfy.prepare
        def dual_prepare(*args,**kwargs):
            prepared=original_prepare(*args,**kwargs)
            graph=json.loads(Path(prepared['files']['api']).read_text('utf8'))
            schema=comfy.client.schemas(['LevaVAEDecodeDevice'])['LevaVAEDecodeDevice']
            choices=schema['input']['required']['device'][0]
            target=next(device for device in choices if '4050' in device)
            for node in graph.values():
                if node['class_type']=='VAEDecode':
                    node['class_type']='LevaVAEDecodeDevice';node['inputs'].update(device=target,tile_size=256)
            return comfy.prepare_graph(graph,'Leva SDXL · 5070 denoising + 4050 tiled VAE',{'split':'5070 denoising / 4050 VAE'})
        comfy.prepare=dual_prepare
    save(proof)
    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            selected=[(name,service) for name,service in [('fooocus', foo), ('comfy', comfy)] if settings.engine=='both' or settings.engine==name or settings.engine=='comfy-dual' and name=='comfy']
            pending = [pool.submit(run_engine, name, service, proof) for name, service in selected]
            while not all(p.done() for p in pending):
                sampled = subprocess.run(['nvidia-smi', '--query-gpu=uuid,name,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=8)
                import psutil
                proof['samples'].append({'time': time.time(), 'gpu_csv': sampled.stdout.strip(),
                                         'ram_used_bytes':psutil.virtual_memory().used,'cpu_percent':psutil.cpu_percent()})
                save(proof)
                time.sleep(2)
            for item in pending: item.result()
        proof['status'] = 'completed'
    finally:
        foo.stop(); comfy.stop()
        for service in (foo, comfy):
            if service.process:
                try: service.process.wait(timeout=20)
                except subprocess.TimeoutExpired: pass
        proof['owned_workers_released'] = True
        save(proof)
    print(json.dumps({k: v for k, v in proof.items() if k != 'samples'}, ensure_ascii=True), flush=True)


if __name__ == '__main__': main()
