"""Verify each new GGUF through the frozen app's actual worker IPC, without audio."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from chat_service import ChatService
from personal_models import PROFILES,model_path
from paths import DATA
EXE=DATA/'program/0.34.0/Leva/Leva.exe';OUT=DATA/'verification/model-expansion-v034'
rows=[]
for key in ('qwen35_9b','hermes4_14b','ministral3_8b','gemma3_12b','rocinante12b'):
    service=ChatService([str(EXE),'--chat-session-worker'],persistent=True);started=time.perf_counter()
    row={'key':key,'model_path':str(model_path(key)),'gpu':'RTX 5070','microphone':False,'speaker':False}
    try:
        result=service.ask('Jawab satu kalimat singkat dalam bahasa Indonesia bahwa kamu Leva dan siap menemani percakapan.','local','gpu5070',local_model=key,keep_warm=False,purpose='room_secret')
        row.update(result=result,ok=result.get('provider')=='local' and bool(result.get('response')))
    except Exception as error:row.update(ok=False,error=str(error))
    finally:service.cancel();row['elapsed_ms']=round((time.perf_counter()-started)*1000,2)
    rows.append(row);(OUT/'packaged-inference.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'model':key,'ok':row['ok'],'ms':row['elapsed_ms']}),flush=True)
if not all(r['ok'] for r in rows):raise SystemExit(1)
