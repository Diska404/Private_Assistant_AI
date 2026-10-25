"""One voice identity, bounded phrase/translation/PCM queues, one persistent synth worker.

No microphone or model routing is selected here. The host supplies translation and device
policy. Playback reads owned copies, so synthesis can prepare the next phrase concurrently.
"""
import queue
import shutil
import tempfile
import threading
import time
from pathlib import Path
from llm_stream import AdaptiveSegmenter

class SpeechRuntimePool:
    """At most one idle synth worker, with explicit close and a bounded warm TTL."""
    def __init__(self,idle_seconds=120):self.idle_seconds=idle_seconds;self.lock=threading.Lock();self.cached=None;self.timer=None;self.epoch=0
    def take(self,factory):
        with self.lock:
            if self.timer:self.timer.cancel();self.timer=None
            value=self.cached;self.cached=None;epoch=self.epoch
        value=value or factory(persistent=True);value._leva_pool_epoch=epoch
        return value
    def release(self,service):
        with self.lock:
            stale=getattr(service,'_leva_pool_epoch',-1)!=self.epoch
            old=self.cached
            if self.timer:self.timer.cancel();self.timer=None
            self.cached=None if stale else service
            def expire():
                with self.lock:
                    if self.cached is not service:return
                    self.cached=None
                service.stop()
            if not stale:
                self.timer=threading.Timer(self.idle_seconds,expire);self.timer.daemon=True;self.timer.start()
        if old and old is not service:old.stop()
        if stale:service.stop()
    def close(self):
        with self.lock:
            service=self.cached;self.cached=None;self.epoch+=1
            if self.timer:self.timer.cancel();self.timer=None
        if service:service.stop()

class LiveSpeechPipeline:
    def __init__(self,pack,language='id',style='assistant',gpu='rtx5070',translate=None,
                 authorized=lambda:True,audio_callback=None,reference_callback=None,
                 output_device='',output_hostapi='',service_factory=None,output_factory=None,
                 native_stream=False,clock=time.monotonic,pool=None):
        from voice_pack_service import VoicePackService
        self.clock=clock;self.started=clock();self.pack=pack;self.language=language;self.style=style
        self.translate=translate;self.authorized=authorized;self.stop_event=threading.Event()
        self.translated=queue.Queue(maxsize=4);self.notices=queue.Queue(maxsize=16)
        self.input_done=False;self.segmenter=AdaptiveSegmenter('ja' if language=='ja' and translate is None else 'id',clock);self.input_lock=threading.Lock();self.raw_pending='';self.input_characters=0
        factory=service_factory or VoicePackService
        self.pool=pool;self.synth=pool.take(factory) if pool else factory(persistent=True);self.playback=factory(persistent=False)
        self.synth.gpu_preference=gpu;self.synth.stream_audio=native_stream;self.synth.early_audio=native_stream
        self.playback.audio_ready_callback=audio_callback;self.playback.reference_callback=reference_callback
        self.playback.output_device_name=output_device;self.playback.output_hostapi=output_hostapi
        from paths import DATA
        folder=DATA/'tmp';folder.mkdir(parents=True,exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(prefix='live-speech-',dir=folder)
        from stream_playback import StreamPlayback
        self.player=StreamPlayback(self.playback,output_factory)
        self.metrics={'first_phrase_ms':None,'first_translated_ms':None,'first_pcm_ms':None,
          'first_output_started_ms':None,'phrases':0,'synthesized':0,'failed':False,'cancelled':False,
          'translation_ms':[],'synthesis_ms':[],'native_stream':native_stream}
        self.pcm_sequence=0;self.synthesis_done=False;self.cleanup_done=False;self.closed=False
        self.threads=[threading.Thread(target=self._translate_loop,daemon=True),threading.Thread(target=self._synth_loop,daemon=True)]
        for thread in self.threads:thread.start()
    def valid(self):return not self.stop_event.is_set() and self.authorized()
    def _put(self,target,item):
        while self.valid():
            try:target.put(item,timeout=.05);return True
            except queue.Full:pass
        return False
    def feed(self,text,final=False):
        with self.input_lock:
            if self.input_done or not self.valid():return False
            self.input_characters+=len(text)
            if self.input_characters>24000:self._error(ValueError('speech_input_limit'));return False
            self.raw_pending+=text;self.input_done=final
        return True
    def _error(self,error):
        self.metrics['failed']=True
        try:self.notices.put_nowait('Suara bertahap berhenti; teks tetap tersedia. Kode: '+type(error).__name__)
        except queue.Full:pass
        self.stop_event.set();self.playback.play_stop.set()
    def _translate_loop(self):
        try:
            while self.valid():
                with self.input_lock:raw=self.raw_pending;self.raw_pending='';done=self.input_done
                if not raw and not done:self.stop_event.wait(.02);continue
                for phrase in self.segmenter.feed(raw,final=done):
                    self.metrics['phrases']+=1
                    if self.metrics['first_phrase_ms'] is None:self.metrics['first_phrase_ms']=(self.clock()-self.started)*1000
                    start=self.clock();spoken=self.translate(phrase) if self.language=='ja' and self.translate else phrase
                    if self.language=='ja':
                        import re
                        if not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',spoken):raise ValueError('speech_translation_script_mismatch')
                    if not self.valid():return
                    self.metrics['translation_ms'].append((self.clock()-start)*1000)
                    if self.metrics['first_translated_ms'] is None:self.metrics['first_translated_ms']=(self.clock()-self.started)*1000
                    if not self._put(self.translated,spoken):return
                if done:self._put(self.translated,None);return
        except Exception as error:self._error(error)
    def _offer(self,path):
        if not self.valid():return
        while self.player.queue.qsize()>=96 and self.valid():self.stop_event.wait(.02)
        if not self.valid():return
        self.pcm_sequence+=1;copy=Path(self.folder.name)/(str(self.pcm_sequence)+'.wav');shutil.copyfile(path,copy)
        if self.metrics['first_pcm_ms'] is None:self.metrics['first_pcm_ms']=(self.clock()-self.started)*1000
        self.playback.actual_pack=self.pack;self.playback.language=self.language
        self.player.offer(copy,self.pcm_sequence)
    def _synth_loop(self):
        try:
            while self.valid():
                try:text=self.translated.get(timeout=.05)
                except queue.Empty:continue
                if text is None:break
                start=self.clock();self.synth.generate(self.pack,text,language=self.language,style=self.style);deltas=0
                while self.valid():
                    if self.synth.check_timeout():raise TimeoutError('tts_timeout')
                    try:event=self.synth.events.get_nowait()
                    except queue.Empty:self.stop_event.wait(.01);continue
                    if event.get('kind')=='error':raise RuntimeError(event.get('code','tts_failed'))
                    if event.get('kind')=='audio_delta':self._offer(self.synth.accept_delta(event));deltas+=1
                    if event.get('kind')=='generated':
                        self.synth.accept_generated(event)
                        if not deltas:self._offer(self.synth.generated)
                        self.metrics['synthesized']+=1;self.metrics['synthesis_ms'].append((self.clock()-start)*1000)
                        self.synth.finish();break
                    if event.get('kind')=='stopped' and self.synth.synthesizing:raise RuntimeError('tts_worker_stopped')
            if self.valid():self.player.end()
        except Exception as error:self._error(error)
        finally:
            self.synthesis_done=True
            if self.stop_event.is_set():self.player.cancel();self.synth.stop()
    @property
    def active(self):return not self.closed and (not self.synthesis_done or self.player.thread is not None and self.player.active)
    @property
    def output_level(self):return self.playback.output_level
    def poll(self):
        if self.player.started_at is not None and self.metrics['first_output_started_ms'] is None:self.metrics['first_output_started_ms']=(self.player.started_at-self.started)*1000
        notices=[]
        while not self.notices.empty():notices.append(self.notices.get_nowait())
        while not self.playback.events.empty():
            event=self.playback.events.get_nowait()
            if event.get('kind')=='error' and event.get('code')!='preview_output_unavailable':self._error(RuntimeError(event.get('code')))
        if self.synthesis_done and not self.active and not self.closed:
            self.closed=True;self._cleanup_async()
        return notices
    def progress(self):
        return {'state':'speaking' if self.output_level>0 else 'thinking' if self.active else 'idle',
          'completed':self.metrics['synthesized'],'total':self.metrics['phrases'],'failed':int(self.metrics['failed'])}
    def cancel(self):
        self.metrics['cancelled']=True;self.stop_event.set();self.playback.play_stop.set();self.closed=True
        self._cleanup_async()
    def _cleanup_async(self):
        if getattr(self,'cleaning',False):return
        self.cleaning=True
        def clean():
            self.player.cancel()
            reusable=self.pool and not self.metrics['failed'] and not self.metrics['cancelled'] and self.input_done
            if not reusable:self.synth.stop()
            self.playback.stop()
            for thread in self.threads:
                if thread is not threading.current_thread():thread.join(5)
            try:self.folder.cleanup()
            except OSError:pass
            if reusable:self.pool.release(self.synth)
            self.cleanup_done=True
        threading.Thread(target=clean,daemon=True).start()
