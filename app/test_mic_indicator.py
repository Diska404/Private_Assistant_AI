import math
import struct
import unittest
from unittest.mock import Mock
from mic_indicator import MicTelemetry,OutputTelemetry,dbfs,pcm_measurements
from local_audio_core import Segmenter
from local_mic_service import LocalMicService
from voice_core import VoiceEvents

class MicIndicatorTests(unittest.TestCase):
    def test_pcm_level_peak_and_clipping_use_real_amplitude(self):
        values=pcm_measurements(struct.pack('<hhhh',32767,-32768,0,16384))
        self.assertTrue(values['clipped']);self.assertEqual(values['peak'],1)
        self.assertAlmostEqual(values['rms'],math.sqrt((32767**2+32768**2+16384**2)/4)/32768)
        self.assertEqual(dbfs(0),-80);self.assertEqual(dbfs(1),0);self.assertAlmostEqual(dbfs(.01),-40)

    def test_threshold_shown_is_the_segmenter_threshold(self):
        s=Segmenter();self.assertEqual(s.threshold,.009)
        s.noise=.008;self.assertEqual(s.threshold,.024)

    def test_live_quiet_voice_clipping_and_stale_are_distinct(self):
        m=MicTelemetry();m.apply({'kind':'local_status','microphone_open':True,'state':'listening','device_name':'Headset'})
        m.apply({'kind':'local_meter','rms':.02,'peak':.07,'voiced':True,'threshold':.009},now=10)
        self.assertEqual(m.snapshot(now=10)['state'],'voice')
        self.assertAlmostEqual(m.snapshot(now=10)['threshold_db'],dbfs(.009))
        m.apply({'kind':'local_meter','rms':.1,'peak':1,'clipped':True},now=10.2)
        self.assertEqual(m.snapshot(now=10.3)['state'],'clipping')
        self.assertEqual(m.snapshot(now=12)['state'],'stale')
        self.assertEqual(m.snapshot(now=12)['rms_db'],-80)
        self.assertEqual(m.snapshot(active=False,now=10.3)['state'],'off')

    def test_unaccepted_transcript_remains_verbatim_and_is_never_an_action(self):
        service=LocalMicService();service.worker=Mock();service.worker.events=VoiceEvents()
        raw='Ay, lipa. Jangan buka Chrome sebelum jam 19:00.'
        service.worker.events.put({'kind':'local_heard','text':raw,'reason':'awaiting_wake','asr_ms':1350})
        result=service.poll()
        self.assertEqual(service.telemetry.text,raw);self.assertEqual(service.telemetry.reason,'awaiting_wake')
        self.assertFalse(any(e['kind']=='local_transcript' for e in result))
        service.worker.send.assert_not_called()

    def test_text_survives_meter_updates_and_capture_stop_but_can_be_cleared(self):
        m=MicTelemetry();m.apply({'kind':'local_heard','text':'Leva, buka Chrome.','reason':'wake'})
        m.apply({'kind':'local_meter','rms':.01,'peak':.03},now=20)
        m.reset_capture();self.assertEqual(m.text,'Leva, buka Chrome.')
        self.assertFalse(m.open);self.assertEqual(m.rms,0)
        m.clear_text();self.assertEqual(m.text,'')

    def test_transcribing_phase_keeps_new_meter_frames(self):
        m=MicTelemetry();m.apply({'kind':'local_status','microphone_open':True,'state':'listening'})
        m.apply({'kind':'local_meter','rms':.01,'peak':.02,'phase':'transcribing'},now=30)
        self.assertEqual(m.snapshot(now=30)['state'],'transcribing')
        m.apply({'kind':'local_meter','rms':.08,'peak':.2,'phase':'transcribing'},now=30.1)
        self.assertEqual(m.rms,.08)

    def test_local_meters_coalesce_without_displacing_transcript(self):
        q=VoiceEvents(capacity=3)
        q.put({'kind':'local_heard','text':'Ay, lipa.'})
        for i in range(100):q.put({'kind':'local_meter','input':i/100})
        self.assertEqual(q.get_nowait()['text'],'Ay, lipa.')
        self.assertEqual(q.get_nowait()['input'],.99)

    def test_output_level_requires_recent_pcm_and_active_playback(self):
        output=OutputTelemetry();pcm=struct.pack('<hh',16384,-16384)*200
        output.offer(pcm,now=10)
        self.assertAlmostEqual(output.snapshot(playing=True,now=10)['rms_db'],-6.0206,places=3)
        self.assertEqual(output.snapshot(playing=False,now=10)['state'],'off')
        self.assertEqual(output.snapshot(playing=True,now=11)['state'],'off')
        output.reset();self.assertEqual(output.snapshot(playing=True,now=10)['state'],'off')

    def test_output_stream_uses_wav_pcm_and_resets_meter_after_completion(self):
        import tempfile,time,types,wave
        from pathlib import Path
        from unittest.mock import patch
        from voice_pack_service import VoicePackService
        snapshots=[]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.wav'
            with wave.open(str(path),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(22050)
                audio.writeframes(struct.pack('<hh',8192,-8192)*2205)
            service=VoicePackService(persistent=True);service.generated=path
            class Stream:
                def __init__(self,**kwargs):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def write(self,pcm):snapshots.append(service.output_telemetry.snapshot(playing=service.playing))
                def abort(self):pass
            fake=types.SimpleNamespace(RawOutputStream=Stream,query_devices=lambda *a,**kw:{'name':'Synthetic output'})
            with patch.dict('sys.modules',{'sounddevice':fake}),patch('voice_pack_service.validate_preview',return_value=(path,.2)):
                self.assertTrue(service.play());service.play_thread.join(timeout=2)
                self.assertFalse(service.play_thread.is_alive())
            self.assertTrue(snapshots)
            self.assertTrue(all(abs(s['rms_db']+12.0412)<.01 for s in snapshots))
            self.assertFalse(service.playing);self.assertEqual(service.output_level,0)
            self.assertEqual(service.output_telemetry.snapshot(playing=True)['state'],'off')

if __name__=='__main__':unittest.main()
