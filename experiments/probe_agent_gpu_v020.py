"""A bounded local-model probe of Saluki on 5070 and actual two-GPU allocation.

No host tools, desktop actions, microphone or playback. Existing user GPU workloads
are left running, so these observations are not a controlled hardware comparison.
"""
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from saluki_backend import SalukiEngine

OUT=DATA/'verification/responsive-v020';OUT.mkdir(parents=True,exist_ok=True)
proof={'host_actions':False,'microphone_opened':False,'speaker_opened':False,
       'controlled_hardware_benchmark':False,'unchanged_model_and_quantization':True,'samples':[]}
for mode in ('gpu5070','dual'):
    engine=None;started=time.monotonic()
    try:
        engine=SalukiEngine(OUT/('saluki-'+mode),mode=mode,acceleration='plain',
            system='Jawab tepat sesuai teks yang diminta. Tanpa penjelasan.',max_output_tokens=32)
        engine.start();loaded=time.monotonic()
        answers=[]
        for _ in range(2):
            before=time.monotonic();text=engine.generate([{'role':'user','content':'Jawab persis satu kata: SIAP'}])
            answers.append({'seconds':round(time.monotonic()-before,3),'response':text,'exact_match':text.strip()=='SIAP'})
        log=(OUT/('saluki-'+mode)/('local-runtime-'+mode+'.log')).read_text('utf-8',errors='replace')
        import re
        row={'mode':mode,'acceleration':'plain','load_seconds_including_asset_verification':round(loaded-started,3),
             'devices':engine.devices,'snapshot_before':engine.gpu_snapshot_before,
             'snapshot_loaded':engine.gpu_snapshot_loaded,'answers':answers,
             'offload_log':[line for line in log.splitlines() if re.search(r'offload|model buffer size|KV buffer size',line,re.I)][-18:]}
    except Exception as error:row={'mode':mode,'error':str(error),'elapsed_seconds':round(time.monotonic()-started,3)}
    finally:
        if engine:engine.close()
    proof['samples'].append(row)
    (OUT/'saluki-gpu-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(row),flush=True)
