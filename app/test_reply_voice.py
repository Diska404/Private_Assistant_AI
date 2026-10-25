from pathlib import Path
import queue
import json
import tempfile
import sys
import unittest
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]
from reply_voice import ReplyVoice,speech_chunks
from saluki_backend import SalukiEngine,chosen_acceleration
from hybrid_engine import EngineError
from voice_core import VoiceEvents

class ReplyTests(unittest.TestCase):
    def service(self):
        service=Mock(); service.events=VoiceEvents(); service.active=False; service.worker.active=True;service.can_play=False
        service.check_timeout.return_value=False
        service.generate.return_value={'actual':'leva_gfl2'}
        return service

    def test_long_reply_keeps_all_prose_in_bounded_chunks(self):
        text='Aku akan membantu. '*200
        parts=speech_chunks(text)
        self.assertTrue(all(0<len(p)<=480 for p in parts))
        self.assertEqual(' '.join(parts),' '.join(text.split()))
        self.assertNotIn('```',' '.join(speech_chunks('Ini penjelasan. ```python\nprint(1)\n``` Selesai.')))
        with self.assertRaises(ValueError):speech_chunks('a'*8001)

    def test_generated_audio_waits_for_worker_exit_before_playback(self):
        service=self.service(); voice=ReplyVoice(service)
        voice.speak('Halo, aku siap.','leva_gfl2')
        service.events.put({'kind':'generated'})
        voice.poll(); service.play.assert_not_called()
        service.worker.active=False
        service.can_play=True
        voice.poll(); service.play.assert_called_once()
        self.assertEqual(voice.state,'connecting')

    def test_stop_discards_remaining_chunks_and_no_new_synthesis(self):
        service=self.service(); voice=ReplyVoice(service)
        voice.speak('Kalimat pertama. '*100,'leva_gfl2')
        self.assertTrue(voice.pending)
        voice.stop()
        self.assertFalse(voice.active)
        service.generate.assert_called_once()

    def test_worker_error_stops_queue_without_switching_identity(self):
        service=self.service(); voice=ReplyVoice(service)
        voice.speak('Coba dengarkan. '*100,'leva_gfl2')
        service.events.put({'kind':'error','code':'candidate_asset_mismatch'})
        self.assertIn('candidate_asset_mismatch',voice.poll()[0])
        self.assertFalse(voice.active)
        service.generate.assert_called_once()

    def test_speculative_methods_are_alternatives_and_never_load_microturn_lora(self):
        for method in ('plain','mtp','dflash'):
            engine=SalukiEngine(Path('unused'),acceleration=method)
            flags=engine.extra_server_args
            self.assertNotIn('--lora',flags)
            if method=='plain':self.assertNotIn('--spec-type',flags)
            else:self.assertIn('draft-mtp' if method=='mtp' else 'draft-dflash',flags)
        with self.assertRaises(EngineError):chosen_acceleration('mtp,dflash')

    def test_auto_refuses_a_failed_probe_but_manual_experiments_remain_explicit(self):
        with tempfile.TemporaryDirectory() as folder,patch('saluki_backend.MODEL_ROOT',Path(folder)):
            profile=Path(folder)/'runtime-profile.json'
            profile.write_text(json.dumps({'blocked_auto':True,'measured':False}),encoding='utf-8')
            with self.assertRaisesRegex(EngineError,'benchmark_pending'):chosen_acceleration('auto')
            self.assertEqual(chosen_acceleration('mtp'),'mtp')
            profile.write_text(json.dumps({'recommended_acceleration':'mtp','measured':True}),encoding='utf-8')
            self.assertEqual(chosen_acceleration('auto'),'mtp')

if __name__=='__main__':unittest.main()
