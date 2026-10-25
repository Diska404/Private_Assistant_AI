"""Bounded, owner-scoped voice drafts. Audio lives in memory and is never an agent command."""
import base64
import hashlib
import io
import re
import threading
import time
import wave

MAX_WAV=1_920_044


def validate_wav(raw):
    if not 44<len(raw)<=MAX_WAV:raise ValueError('audio_max_60_seconds')
    with wave.open(io.BytesIO(raw),'rb') as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate(),audio.getcomptype())!=(1,2,16000,'NONE'):raise ValueError('audio_requires_mono_pcm16_16000')
        frames=audio.getnframes();pcm=audio.readframes(frames)
        if not 3200<=frames<=960000 or len(pcm)!=frames*2:raise ValueError('audio_incomplete_or_duration')
    return pcm,frames/16000


class RemoteSpeech:
    def __init__(self):
        self.lock=threading.RLock();self.jobs={};self.worker=None;self.running=None;self.closed=False
    def submit(self,ident,owner,raw):
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,100}',ident):raise ValueError('invalid_recording_id')
        pcm,seconds=validate_wav(raw)
        fingerprint=hashlib.sha256(pcm).hexdigest()
        with self.lock:
            self.expire()
            if self.closed:raise ValueError('speech_service_stopped')
            if ident in self.jobs:
                if self.jobs[ident]['owner']!=owner or self.jobs[ident]['fingerprint']!=fingerprint:raise ValueError('recording_idempotency_conflict')
                return self.public(self.jobs[ident])
            if sum(j['status'] in ('queued','running') for j in self.jobs.values())>=2:raise ValueError('speech_queue_full')
            row={'id':ident,'owner':owner,'status':'queued','pcm':pcm,'fingerprint':fingerprint,'seconds':round(seconds,2),'created':time.monotonic(),'text':''}
            self.jobs[ident]=row;return self.public(row)
    def public(self,row):return {k:v for k,v in row.items() if k not in ('owner','pcm','created','fingerprint')}
    def get(self,ident,owner):
        with self.lock:
            self.expire();row=self.jobs.get(ident)
            return self.public(row) if row and row['owner']==owner else None
    def expire(self):
        now=time.monotonic()
        for key in list(self.jobs):
            if key!=self.running and (now-self.jobs[key]['created']>600 or len(self.jobs)>30 and self.jobs[key]['status'] not in ('queued','running')):del self.jobs[key]
    def cancel(self,ident,owner):
        with self.lock:
            row=self.jobs.get(ident)
            if not row or row['owner']!=owner:return False
            row.update(status='cancelled',pcm=b'',text='')
            worker=self.worker if self.running==ident else None
        if worker:worker.stop()
        return True
    def pump(self,config,is_active,prepare):
        with self.lock:
            if self.closed or self.running:return
            for row in self.jobs.values():
                if row['status']!='queued':continue
                if not is_active(row['owner']):row.update(status='cancelled',pcm=b'');continue
                self.running=row['id'];row['status']='running';break
            else:return
        def work():
            worker=None
            try:
                if not is_active(row['owner']):raise ValueError('device_revoked')
                from live_voice import LiveVoiceService
                from speech_asr import ASR_PYTHON
                from feature_bridge import resource
                worker=LiveVoiceService([str(ASR_PYTHON),'-u','-B',str(resource('remote_speech_worker.py'))])
                with self.lock:
                    if self.closed or row['status']=='cancelled':return
                    self.worker=worker
                worker.start(None,None,initial_message={**config,'pcm':base64.b64encode(row['pcm']).decode('ascii')})
                row['pcm']=b'';until=time.monotonic()+120
                while time.monotonic()<until:
                    if self.closed or row['status']=='cancelled' or not is_active(row['owner']):raise ValueError('recording_cancelled_or_revoked')
                    try:event=worker.events.get_nowait()
                    except __import__('queue').Empty:time.sleep(.08);continue
                    if event.get('kind')=='draft':
                        with self.lock:row.update(status='completed',text=event['text'][:3000],metrics=event.get('metrics',{}))
                        return
                    if event.get('kind')=='error':raise ValueError(event.get('code','asr_worker_failed'))
                raise ValueError('asr_timeout')
            except Exception as error:
                with self.lock:
                    if row['status']!='cancelled':row.update(status='failed',error=str(error)[:120] if isinstance(error,ValueError) else type(error).__name__)
            finally:
                if worker:worker.stop()
                with self.lock:row['pcm']=b'';self.running=None;self.worker=None
        try:prepare()
        except Exception:
            with self.lock:row.update(status='failed',error='audio_resource_release_failed',pcm=b'');self.running=None
            return
        threading.Thread(target=work,daemon=True).start()
    def pending(self):
        with self.lock:return bool(self.running) or any(j['status'] in ('queued','running') for j in self.jobs.values())
    def stop(self):
        with self.lock:
            self.closed=True;worker=self.worker
            for row in self.jobs.values():
                if row['status'] in ('queued','running'):row.update(status='cancelled',pcm=b'')
        if worker:worker.stop()
