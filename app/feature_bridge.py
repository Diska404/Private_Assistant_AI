"""Owned external runtime for desktop, web, vision and telemetry dependencies."""
import json
import queue
import sys
import threading
import time
from pathlib import Path

from live_voice import LiveVoiceService
from paths import ROOT,DATA

PYTHON=DATA/'environments/voice-leva-bilingual/Scripts/python.exe'

def resource(name):
    return Path(sys._MEIPASS)/'assistant_runtime'/name if getattr(sys,'frozen',False) else ROOT/'app'/name

class FeatureBridge:
    def __init__(self):
        self.worker=LiveVoiceService([str(PYTHON),'-u','-B',str(resource('feature_worker.py'))])
        self.lock=threading.Lock();self.sequence=0
        self.last_activity=time.monotonic()
        self.browser_active=False

    def run(self,action,args,authorized=lambda:True,timeout=55):
        if not self.lock.acquire(blocking=False):return {'status':'failed','reply':'Alat desktop sedang dipakai. Coba sesaat lagi.'}
        try:
            if not authorized():return {'status':'cancelled','reply':'Tindakan dibatalkan.'}
            self.sequence+=1;ident=self.sequence
            payload={'id':ident,'action':action,'args':args}
            if not self.worker.active:self.worker.start(None,None,initial_message=payload)
            else:self.worker.send(payload)
            until=time.monotonic()+timeout
            while time.monotonic()<until:
                if not authorized():self.stop();return {'status':'cancelled','reply':'Tindakan dihentikan; periksa hasil yang mungkin sudah terjadi.'}
                try:event=self.worker.events.get_nowait()
                except queue.Empty:time.sleep(.03);continue
                if event.get('id')==ident:
                    result=event['result']
                    if action in ('browser_action','comfy_canvas','comfy_open','comfy_current','fooocus_open') and 'browser_active' in result:self.browser_active=result['browser_active']
                    return result
                if event.get('kind')=='error':break
            self.stop();return {'status':'failed','reply':'Alat melewati batas waktu atau worker berhenti. Tidak ada klaim tindakan berhasil.'}
        finally:self.last_activity=time.monotonic();self.lock.release()

    def stop(self):self.worker.stop();self.browser_active=False
    def expire_idle(self):
        if not self.lock.acquire(blocking=False):return
        try:
            if not self.browser_active and time.monotonic()-self.last_activity>120:self.stop()
        finally:self.lock.release()
