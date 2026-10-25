"""Saluki plain-decoding validation after the global UUID mask change."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from saluki_backend import SalukiEngine
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021')
proof=[]
for mode in ('gpu5070','dual'):
    engine=SalukiEngine(OUT/('saluki-'+mode),mode=mode,acceleration='plain',system='Jawab persis permintaan pengguna.',max_output_tokens=16)
    try:
        start=time.monotonic();reply=engine.generate([{'role':'user','content':'Jawab satu kata: SIAP'}])
        row={'mode':mode,'reply':reply,'total_seconds':time.monotonic()-start,'load_seconds':engine.load_seconds,
             'uuid_mask':engine.visible_gpu_uuids,'devices':engine.devices,'model_gpu_buffers_mib':engine.model_gpu_buffers_mib,
             'microphone_opened':False,'tools_called':False}
        proof.append(row);print(json.dumps(row),flush=True)
    finally:engine.close()
(OUT/'saluki-isolation.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
