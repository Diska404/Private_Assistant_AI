"""Real llama.cpp requests with UUID visibility isolation; no tools/cloud/audio."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from hybrid_engine import LocalEngine
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021')
SERVER=Path('D:/AI/AI Lokal Asisten/Leva/runtime/llamacpp-b11721-cuda13.4/llama-server.exe')
MODEL=Path('D:/AI/AI Lokal Asisten/AI Models/MiniCPM5-2B/MiniCPM5-2B-Q8_0.gguf')
proof=[]
for mode in ('gpu4050','gpu5070','dual'):
    engine=LocalEngine(SERVER,MODEL,OUT/('llm-'+mode),mode=mode,context_size=512,max_output_tokens=32,
                       system='Jawab persis sesuai permintaan pengguna.',extra_server_args=('-lv','4'))
    try:
        t=time.monotonic();reply=engine.generate([{'role':'user','content':'Jawab satu kata saja: SIAP'}]);elapsed=time.monotonic()-t
        import psutil
        visible=psutil.Process(engine.process.pid).environ().get('CUDA_VISIBLE_DEVICES')
        assert visible==','.join(engine.visible_gpu_uuids)
        assert len(engine.devices)==(2 if mode=='dual' else 1)
        row={'mode':mode,'selected_devices':engine.devices,'cuda_visible_devices':visible,'load_seconds':engine.load_seconds,
             'model_gpu_buffers_mib':engine.model_gpu_buffers_mib,'total_seconds':elapsed,'reply':reply,'gpu_before':engine.gpu_snapshot_before,'gpu_loaded':engine.gpu_snapshot_loaded,
             'microphone_opened':False,'agent_tools_called':False}
        proof.append(row);print(json.dumps(row),flush=True)
    finally:engine.close()
OUT.mkdir(parents=True,exist_ok=True);(OUT/'llm-isolation.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
