import base64
import queue
import threading
from feature_bridge import PYTHON,resource
from live_voice import LiveVoiceService
from mic_indicator import MicTelemetry

class LocalMicService:
    def __init__(self):
        self.worker=LiveVoiceService([str(PYTHON),'-u','-B',str(resource('local_mic_worker.py'))])
        self.references=queue.Queue(maxsize=30);self.stop_event=threading.Event();self.thread=None
        self.input_level=0;self.state='off';self.last_asr_ms=0;self.spoken_text='';self.gpu_name=''
        self.telemetry=MicTelemetry()
        self.asr_held=threading.Event()
    @property
    def active(self):return self.worker.active
    def start(self,input_device_name='',input_hostapi='',asr_model='whisper_cpu',asr_gpu='auto',asr_language='id'):
        if self.active:return
        self.telemetry.reset_capture()
        self.asr_held.clear()
        self.stop_event.clear();self.state='loading'
        if asr_model!='whisper_cpu':
            from speech_asr import ASR_PYTHON,ready
            if not ready(asr_model):raise ValueError('speech_asr_assets_missing')
            self.worker.worker_command=[str(ASR_PYTHON),'-u','-B',str(resource('local_mic_worker.py'))]
        else:self.worker.worker_command=[str(PYTHON),'-u','-B',str(resource('local_mic_worker.py'))]
        self.worker.start(None,None,initial_message={'input_device_name':input_device_name,'input_hostapi':input_hostapi,
            'wake_word':'leva','asr_model':asr_model,'asr_gpu':asr_gpu,'asr_language':asr_language})
        def send_references():
            import audioop
            rate_state=None;last_rate=None
            while not self.stop_event.is_set():
                try:pcm,rate=self.references.get(timeout=.1)
                except queue.Empty:continue
                if not pcm:
                    rate_state=None;self.worker.send({'kind':'reference_reset'});continue
                if rate!=last_rate:rate_state=None;last_rate=rate
                converted,rate_state=audioop.ratecv(pcm,2,1,rate,16000,rate_state)
                self.worker.send({'kind':'reference','pcm':base64.b64encode(converted).decode('ascii'),'spoken_text':self.spoken_text[:8000]})
        self.thread=threading.Thread(target=send_references,daemon=True);self.thread.start()
    def reference(self,pcm,rate):
        if not self.active:return
        try:self.references.put_nowait((pcm,rate))
        except queue.Full:
            # A missing render packet invalidates alignment; reset explicitly.
            while not self.references.empty():
                try:self.references.get_nowait()
                except queue.Empty:break
            try:self.references.put_nowait((b'',rate));self.references.put_nowait((pcm,rate))
            except queue.Full:pass
    def poll(self):
        events=[]
        while not self.worker.events.empty():
            event=self.worker.events.get_nowait()
            self.telemetry.apply(event)
            if event.get('kind')=='local_meter':self.input_level=event['input'];self.state=event['state']
            elif event.get('kind')=='local_status':self.state=event['state'];self.gpu_name=event.get('gpu_name',self.gpu_name)
            elif event.get('kind')=='local_transcript':self.last_asr_ms=event.get('asr_ms',0)
            elif event.get('kind')=='local_asr_held':self.asr_held.set()
            elif event.get('kind')=='local_asr_resumed':self.asr_held.clear()
            events.append(event)
        return events
    def request_asr_hold(self):
        if self.asr_held.is_set():return
        self.asr_held.clear();self.worker.send({'kind':'hold_asr'})
    def resume_asr(self):
        self.asr_held.clear();self.worker.send({'kind':'resume_asr'})
    def hold_asr(self,timeout=30):
        # Called from the task thread; the GUI keeps polling the acknowledgement.
        if not self.active:return
        self.request_asr_hold()
        import time
        until=time.monotonic()+timeout
        while self.active and time.monotonic()<until:
            if self.asr_held.wait(.1):return
        if self.active:raise RuntimeError('microphone_asr_hold_timeout')
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=.4)
        self.worker.stop();self.state='off';self.input_level=0
        self.telemetry.reset_capture()
        self.asr_held.clear()
        while not self.references.empty():
            try:self.references.get_nowait()
            except queue.Empty:break
