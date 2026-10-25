"""One cancellable output stream for incremental speech; no inference model here."""
import queue
import threading
import time
import wave

class StreamPlayback:
    def __init__(self,owner,output_factory=None):
        self.owner=owner;self.output_factory=output_factory;self.queue=queue.Queue(maxsize=128)
        self.stop_event=threading.Event();self.complete=threading.Event();self.finished=False;self.audible=False
        self.thread=None;self.sequence=0;self.bytes=0;self.underruns=0;self.started_at=None
    @property
    def active(self):return not self.finished
    def offer(self,path,sequence):
        if sequence!=self.sequence+1:raise ValueError('voice_stream_sequence_mismatch')
        self.sequence=sequence
        try:self.queue.put_nowait(path)
        except queue.Full:raise ValueError('voice_stream_queue_full') from None
        if self.thread is None:
            self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def end(self):self.complete.set()
    def cancel(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=1)
        self.owner.output_level=0;self.owner.output_telemetry.reset();self.owner.playing=False;self.finished=True
    def output(self,rate):
        if self.output_factory:return self.output_factory(rate)
        import sounddevice as sd
        owner=self.owner;device=None;name=getattr(owner,'output_device_name','');host=getattr(owner,'output_hostapi','')
        if name:
            matches=[i for i,row in enumerate(sd.query_devices()) if row['max_output_channels']>0 and row['name']==name and (not host or sd.query_hostapis(row['hostapi'])['name']==host)]
            if not matches:raise ValueError('output_device_not_found')
            device=matches[0]
        return sd.RawOutputStream(samplerate=rate,channels=1,dtype='int16',device=device)
    def run(self):
        owner=self.owner;stream=None;local_failed=False;began=False;next_deadline=time.monotonic()
        try:
            while not self.stop_event.is_set():
                try:path=self.queue.get(timeout=.05)
                except queue.Empty:
                    if self.complete.is_set():break
                    if began:self.underruns+=1
                    continue
                if self.stop_event.is_set():break
                # Publish at playback time, not when inference races ahead; the
                # bounded web clip cache then cannot evict future unheard audio.
                callback=getattr(owner,'audio_ready_callback',None)
                if callback:
                    callback(path,{'pack':owner.actual_pack,'language':owner.language,'streaming':True})
                    owner.web_audio_published=True
                with wave.open(str(path),'rb') as clip:
                    rate=clip.getframerate()
                    if not began:
                        began=True;self.audible=True;owner.playing=True
                        owner.events.put_nowait({'kind':'playback_started'})
                        try:
                            stream=self.output(rate);stream.start();self.started_at=time.monotonic()
                        except Exception as error:
                            local_failed=True;stream=None
                            owner.events.put_nowait({'kind':'error','code':'preview_output_unavailable'})
                            owner.audio_status('stream_remote_only',error_type=type(error).__name__)
                    while not self.stop_event.is_set():
                        raw=clip.readframes(rate//50)
                        if not raw:break
                        from voice_core import pcm_level
                        owner.output_level=pcm_level(raw);owner.output_telemetry.offer(raw)
                        reference=getattr(owner,'reference_callback',None)
                        if reference and not local_failed:reference(raw,rate)
                        if stream:
                            try:stream.write(raw)
                            except Exception as error:
                                local_failed=True
                                try:stream.abort();stream.close()
                                except Exception:pass
                                stream=None;owner.events.put_nowait({'kind':'error','code':'preview_output_unavailable'})
                        if not stream:
                            # Pace remote-only delivery too, preserving the bounded
                            # clip cache and cancellation instead of flooding it.
                            next_deadline=max(next_deadline,time.monotonic())+len(raw)/(rate*2)
                            self.stop_event.wait(max(0,next_deadline-time.monotonic()))
                        self.bytes+=len(raw)
            if not self.stop_event.is_set():
                owner.audio_status('stream_finished',pcm_bytes_sent=self.bytes,stream_chunks=self.sequence,underruns=self.underruns,local_output_failed=local_failed)
        except Exception as error:
            if not self.stop_event.is_set():owner.events.put_nowait({'kind':'error','code':'voice_stream_playback_failed'})
        finally:
            if stream:
                try:
                    if self.stop_event.is_set():stream.abort()
                    else:stream.stop()
                    stream.close()
                except Exception:pass
            owner.output_level=0;owner.output_telemetry.reset();owner.playing=False;self.finished=True
            if not self.stop_event.is_set():owner.events.put_nowait({'kind':'playback_finished'})
