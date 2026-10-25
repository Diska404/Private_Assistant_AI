"""Actual new Japanese audio through the app adapter; no microphone or network."""
import json
from pathlib import Path
import shutil
import sys
import time
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from voice_pack_service import VoicePackService
from paths import DATA

out=DATA/'verification/japanese-v010';out.mkdir(parents=True,exist_ok=True)
service=VoicePackService(persistent=True)
proof={'status':'running','network_used':False,'microphone_opened':False,'rows':[]}
def save():(out/'source-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
try:
    for i,text in enumerate(('こんにちは、レヴァです。いつでもお手伝いします。','おかえりなさい。今日は何をしましょうか。'),1):
        started=time.monotonic();service.generate('leva_gfl2',text,language='ja')
        until=time.monotonic()+150
        while time.monotonic()<until:
            while not service.events.empty():
                event=service.events.get_nowait()
                if event.get('kind')=='error':raise RuntimeError(event)
                if event.get('kind')=='generated':service.accept_generated(event)
            if service.generated:break
            time.sleep(.03)
        else:raise TimeoutError('Japanese voice timed out')
        path=out/f'japanese-{i}.wav';shutil.copyfile(service.generated,path)
        row={'text':text,'language':'ja','elapsed_seconds':round(time.monotonic()-started,3),'audio':str(path),'metadata':service.last_result}
        proof['rows'].append(row);save();print(json.dumps(row,ensure_ascii=True),flush=True)
        service.finish()
    proof['status']='completed'
except Exception as error:proof.update(status='failed',error=str(error))
finally:service.stop();proof['worker_released']=not service.loaded;save()
