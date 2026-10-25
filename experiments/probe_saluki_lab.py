"""Exercise Saluki prompt-only turns through the actual packaged Duplex Lab worker."""
import json
from pathlib import Path
import queue
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from live_voice import LiveVoiceService
from duplex_core import parse_decision
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\saluki-v08')

if __name__=='__main__':
    service=LiveVoiceService([str(ROOT/'program/Leva/Leva.exe'),'--duplex-worker'])
    proof={'status':'starting','rows':[],'microphone_opened':False,'speaker_opened':False}
    def event(timeout):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:return service.events.get_nowait()
            except queue.Empty:time.sleep(.03)
        raise TimeoutError('saluki_lab_timeout')
    try:
        service.start(0,0,initial_message={'kind':'start','backend':'saluki','acceleration':'auto'})
        while True:
            item=event(180)
            if item['kind']=='error':raise RuntimeError(item['code'])
            if item['kind']=='ready':proof['ready']=item;break
        history=[]
        for ident,heard in enumerate(['Halo Leva.','<no voice>','Saya ingin belajar','bermain piano.',
            '<no voice>','Apa langkah pertama?','<no voice>','<no voice>'],1):
            service.send({'kind':'tick','id':ident,'heard':heard,'history':history})
            while True:
                item=event(45)
                if item['kind']=='error':raise RuntimeError(item['code'])
                if item['kind']=='result':break
            try:decision=parse_decision(item['text'])[0];valid=True
            except ValueError:decision='invalid';valid=False
            proof['rows'].append({'heard':heard,**item,'grammar_valid':valid,'decision':decision})
            if valid:history.append((heard,item['text']))
        proof['status']='packaged_saluki_lab_completed'
    except Exception as error:proof.update(status='failed',error=str(error))
    finally:
        service.stop();proof['worker_released']=not service.active
        (OUT/'lab-proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)
