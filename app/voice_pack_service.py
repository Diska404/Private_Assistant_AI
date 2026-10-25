"""Owned one-shot synthesis and cancellable local playback, both opt-in."""
import tempfile
import threading
import time
import wave

from live_voice import LiveVoiceService
from voice_packs import PREVIEWS, PYTHON, CANDIDATE_PYTHON, resource, resolve_pack, validate_preview, validate_text
from mic_indicator import OutputTelemetry


class VoicePackService:
    def __init__(self,persistent=False):
        self.persistent=persistent
        import sys
        from paths import ROOT
        script = (resource("local_voice_runtime/voice_pack_worker.py") if getattr(sys, "frozen", False)
                  else ROOT / "app/voice_pack_worker.py")
        self.script = script
        self.worker = LiveVoiceService([str(PYTHON), "-B", "-u", str(script)])
        self.events = self.worker.events
        self.folder = None
        self.generated = None
        self.playing = False
        self.state = "idle"
        self.epoch = 0
        self.play_thread = None
        self.play_stop = threading.Event()
        self.deadline = 0
        self.actual_pack = None
        self.synthesizing=False
        self.sequence=0
        self.request_id=None
        self.last_result=None
        self.language='id'
        self.output_level=0
        self.output_telemetry=OutputTelemetry()
        self.gpu_preference='auto'
        # Native v0.9.2 SSE can assert inside ggml on repeated long requests.
        # Keep the stable sentence queue as default until the streaming soak
        # test passes. The isolated verifier explicitly opts into real SSE.
        self.stream_audio=False
        self.early_audio=False

    @property
    def active(self):
        return (self.synthesizing if self.persistent else self.worker.active) or self.playing

    def audio_status(self,state,**details):
        """Delivery evidence, not a claim that a person heard the sound."""
        import json,os
        from paths import DATA
        if os.environ.get('LEVA_AUDIO_DIAGNOSTICS')=='0':return
        try:
            folder=DATA/'status';folder.mkdir(parents=True,exist_ok=True)
            value={'state':state,'updated_at':time.time(),'pid':os.getpid(),'pack':self.actual_pack,
                   'selected_device':getattr(self,'output_device_name',''),'selected_hostapi':getattr(self,'output_hostapi',''),**details}
            temporary=folder/('reply-audio-'+str(os.getpid())+'.tmp')
            temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8');temporary.replace(folder/'reply-audio.json')
        except OSError:pass

    @property
    def loaded(self):return self.worker.active

    @property
    def can_play(self):
        return bool(self.generated and not self.synthesizing and (self.persistent or not self.worker.active))

    def generate(self, requested, text,language='id',style='assistant'):
        if language not in ('id','ja'):raise ValueError('unsupported_voice_language')
        if style not in ('assistant','personal'):raise ValueError('invalid_speech_style')
        resolved = resolve_pack(requested)
        if not resolved["available"]:
            raise ValueError("local_voice_runtime_missing")
        text = validate_text(text)
        modern=resolved['actual'].startswith(('higgs_','omnivoice_'))
        if not modern and self.gpu_preference not in ('auto','rtx4050'):
            # Historical Kokoro/Seed-VC adapters are hard-bound to 4050.
            # Never run them on 4050 when the global route restricts us to 5070.
            if resolved['actual']!='neutral_id' or language!='id':raise ValueError('voice_gpu_unsupported_for_engine')
        reuse=self.persistent and self.worker.active and not self.synthesizing and self.actual_pack==resolved['actual'] and (modern or self.language==language)
        self.reset(keep_warm=reuse)
        self.actual_pack = resolved['actual']
        self.language=language
        self.worker.worker_command=[str(CANDIDATE_PYTHON if modern or resolved['actual']=='leva_gfl2' or language=='ja' else PYTHON),'-B','-u',str(self.script)]
        if self.persistent:self.worker.worker_command.append('--session')
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=PREVIEWS, prefix="preview-")
        from pathlib import Path
        output = Path(self.folder.name) / "speech.wav"
        self.state = "thinking"
        self.synthesizing=True
        self.audio_status('synthesizing',language=language)
        self.last_result=None
        self.sequence+=1;self.request_id=self.sequence
        self.deadline = time.monotonic() + 180
        try:
            payload={'actual_pack':resolved['actual'],'text':text,'output':str(output),'request_id':self.request_id,'language':language,'voice_style':style,'tts_gpu':self.gpu_preference,'stream_audio':self.stream_audio and resolved['actual'].startswith('higgs_'),'early_audio':self.early_audio is True}
            if reuse:self.worker.send(payload)
            else:self.worker.start(None,None,initial_message=payload)
        except Exception:
            self.stop()
            raise
        return {**resolved,'voice_style':style,'reason':resolved['reason']+' · '+style if modern else ('Jepang · Kokoro → Seed-VC kandidat A · RTX 4050' if resolved['actual']=='leva_gfl2' else 'Jepang netral · Kokoro · RTX 4050') if language=='ja' else resolved.get('reason','Suara lokal')}

    def accept_generated(self, event):
        """A worker result must belong to this request, not a historical or arbitrary WAV."""
        from pathlib import Path
        if not self.folder or event.get("actual_pack") != (self.actual_pack or 'neutral_id'):
            raise ValueError("stale_voice_result")
        if self.persistent and event.get('request_id')!=self.request_id:raise ValueError('stale_voice_result')
        expected = Path(self.folder.name) / "speech.wav"
        if Path(event.get("path", "")).resolve() != expected.resolve():
            raise ValueError("unexpected_voice_result")
        validate_preview(expected)
        self.generated = expected
        self.last_result=dict(event)
        self.synthesizing=False
        self.state = "idle"
        self.audio_status('generated',language=self.language)

    def accept_delta(self,event):
        from pathlib import Path
        sequence=event.get('sequence')
        if not self.folder or event.get('request_id')!=self.request_id or event.get('actual_pack')!=self.actual_pack or type(sequence) is not int or not 1<=sequence<=128:raise ValueError('stale_voice_result')
        expected=Path(self.folder.name)/('stream-'+str(sequence).zfill(4)+'.wav')
        if Path(event.get('path','')).resolve()!=expected.resolve():raise ValueError('unexpected_voice_result')
        if not expected.is_file() or expected.stat().st_size>256000:raise ValueError('invalid_voice_stream_clip')
        with wave.open(str(expected),'rb') as clip:
            if clip.getframerate()!=24000 or clip.getnchannels()!=1 or clip.getsampwidth()!=2 or not .1<=clip.getnframes()/24000<=5:raise ValueError('invalid_voice_stream_clip')
            if len(clip.readframes(clip.getnframes()))!=clip.getnframes()*2:raise ValueError('invalid_voice_stream_clip')
        # Pauses inside a valid stream are legitimate; only the complete final
        # utterance is subject to the all-silent preview rejection.
        return expected

    def use_cached(self, source, actual_pack):
        """Copy a verified local clip into an owned playback folder; no inference."""
        import shutil
        from pathlib import Path
        validate_preview(source)
        self.reset(keep_warm=True)
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=PREVIEWS,prefix='reaction-')
        output=Path(self.folder.name)/'speech.wav'
        shutil.copyfile(source,output)
        validate_preview(output)
        self.generated=output;self.actual_pack=actual_pack
        self.state='idle';self.synthesizing=False
        return {'actual':actual_pack,'reason':'Balasan awal tersimpan · pemutaran lokal tanpa inferensi GPU'}

    def check_timeout(self):
        if self.synthesizing and time.monotonic() > self.deadline:
            self.stop()
            return True
        return False

    def play(self):
        if not self.can_play or self.playing:
            return False
        path, _ = validate_preview(self.generated)
        self.web_audio_published=False
        callback=getattr(self,'audio_ready_callback',None)
        if callback:
            try:callback(path,{'pack':self.actual_pack,'language':self.language});self.web_audio_published=True
            except (OSError,ValueError,RuntimeError):self.audio_status('web_audio_unavailable')
        self.play_stop.clear()
        epoch = self.epoch
        self.playing = True
        self.state = "connecting"
        def run():
            sent=0;resolved='';host_name='';peak=0;failed=False
            try:
                import sounddevice as sd
                device=None
                name=getattr(self,'output_device_name','');host=getattr(self,'output_hostapi','')
                if name:
                    candidates=[i for i,row in enumerate(sd.query_devices()) if row['max_output_channels']>0 and row['name']==name and (not host or sd.query_hostapis(row['hostapi'])['name']==host)]
                    if not candidates:raise ValueError('output_device_not_found')
                    device=candidates[0]
                row=sd.query_devices(device,kind='output');resolved=row['name']
                host_name=sd.query_hostapis(row['hostapi'])['name'] if 'hostapi' in row else host
                with wave.open(str(path), "rb") as audio:
                    with sd.RawOutputStream(samplerate=audio.getframerate(), channels=1, dtype="int16",device=device) as stream:
                        self.audio_status('playing',resolved_device=resolved,resolved_hostapi=host_name,sample_rate=audio.getframerate())
                        if not self.play_stop.is_set() and epoch == self.epoch:
                            self.events.put_nowait({"kind": "playback_started"})
                        while not self.play_stop.is_set() and epoch == self.epoch:
                            chunk = audio.readframes(882)  # 40 ms; stop never waits through a whole sentence.
                            if not chunk:
                                break
                            from voice_core import pcm_level
                            self.output_level=pcm_level(chunk)
                            self.output_telemetry.offer(chunk)
                            from mic_indicator import pcm_measurements
                            peak=max(peak,pcm_measurements(chunk)['peak'])
                            reference=getattr(self,'reference_callback',None)
                            if reference:reference(chunk,audio.getframerate())
                            stream.write(chunk)
                            sent+=len(chunk)
                        if self.play_stop.is_set() or epoch != self.epoch:
                            stream.abort()
            except Exception as error:
                failed=True
                if epoch == self.epoch:
                    self.output_level=0
                    self.events.put_nowait({"kind": "error", "code": "preview_output_unavailable"})
                    self.audio_status('error',error_type=type(error).__name__,message=str(error)[:300],resolved_device=resolved)
            finally:
                if epoch == self.epoch:
                    self.output_level=0;self.output_telemetry.reset()
                    self.playing = False
                    self.state = "idle"
                    if not failed:self.audio_status('finished',resolved_device=resolved,resolved_hostapi=host_name,pcm_bytes_sent=sent,pcm_peak=peak)
                    self.events.put_nowait({"kind": "playback_finished"})
        self.play_thread = threading.Thread(target=run, daemon=True)
        self.play_thread.start()
        return True

    def finish(self):
        self.reset(keep_warm=self.persistent)

    def stop(self):self.reset(keep_warm=False)

    def reset(self,keep_warm=False):
        keep_warm=keep_warm and self.persistent and not self.synthesizing
        self.epoch += 1
        self.play_stop.set()
        if self.play_thread:
            self.play_thread.join(timeout=1)
        self.play_thread = None
        self.playing = False
        self.output_level=0
        self.output_telemetry.reset()
        if not keep_warm:self.worker.stop()
        else:
            while not self.events.empty():self.events.get_nowait()
        self.generated = None
        self.web_audio_published=False
        if not keep_warm:self.actual_pack = None
        if not keep_warm:self.last_result=None
        self.synthesizing=False
        self.request_id=None
        self.state = "idle"
        if self.folder:
            try:
                self.folder.cleanup()
            except OSError:
                pass  # Windows may still be releasing a failed audio handle; never delete elsewhere.
            self.folder = None
