"""Exercise the actual frozen worker and prove its owned model is stopped."""
import hashlib
import json
from pathlib import Path
import queue
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from live_voice import LiveVoiceService

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\microturn-lora')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    executable=ROOT/'program/Leva/Leva.exe'
    with executable.open('rb') as source: digest=hashlib.file_digest(source,'sha256').hexdigest()
    service=LiveVoiceService(worker_command=[str(executable),'--duplex-worker'])
    proof={'packaged':True,'exe_sha256':digest,'microphone_opened':False,'speaker_opened':False,'events':[],'status':'starting'}
    def event(timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try: return service.events.get_nowait()
            except queue.Empty: time.sleep(.05)
        raise TimeoutError('packaged_microturn_timeout')
    try:
        service.start(0,0,initial_message={'kind':'start','backend':'microturn'})
        while True:
            item=event(300)
            proof['events'].append(item)
            if item['kind']=='error': raise RuntimeError(item.get('code','worker_error'))
            if item['kind']=='ready':
                if not item.get('lora_loaded'): raise RuntimeError('lora_not_verified_ready')
                break
        history=[]
        for i,heard in enumerate(['I was wondering','<no voice>','whether I should','learn the piano.','<no voice>'],1):
            service.send({'kind':'tick','id':i,'heard':heard,'history':history})
            while True:
                item=event(45)
                proof['events'].append(item)
                if item['kind']=='error': raise RuntimeError(item.get('code','worker_error'))
                if item['kind']=='result' and item['id']==i:
                    history.append((heard,item['text']))
                    break
        proof['status']='packaged_lora_inference_completed'
    except Exception as error:
        proof['status']='failed'; proof['error']=str(error)
    finally:
        service.stop()
        proof['service_active_after_stop']=service.active
        (OUT/'packaged-check.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)
    return 0 if proof['status']=='packaged_lora_inference_completed' and not service.active else 1

if __name__=='__main__': raise SystemExit(main())
