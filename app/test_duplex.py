from pathlib import Path
import sys
import unittest
import queue
from unittest.mock import Mock

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/"experiments")]
from duplex_core import (StableTranscript,TranscriptDelta,DuplexCoordinator,SpeechGate,LISTEN,NO_VOICE,parse_decision,replay_scenarios)
from duplex_service import baseline_messages,DuplexService
from gui import LevaWindow


class TranscriptTests(unittest.TestCase):
    def test_interim_prefix_and_final_do_not_duplicate_words(self):
        source=StableTranscript()
        a=source.update("a",1,"saya ingin")
        b=source.update("a",2,"saya ingin mencari")
        c=source.update("a",3,"saya ingin mencari artikel",True)
        self.assertEqual([a.text,b.text,c.text],["","saya ingin","mencari artikel"])
        self.assertTrue(source.update("a",3,"saya ingin mencari artikel",True).ignored)
        self.assertTrue(source.update("a",2,"saya ingin").ignored)

    def test_revision_of_emitted_text_signals_context_reset(self):
        source=StableTranscript()
        source.update("a",1,"buka chrome diska")
        source.update("a",2,"buka chrome diska sekarang")
        correction=source.update("a",3,"jangan buka chrome",True)
        self.assertTrue(correction.corrected)
        self.assertEqual(correction.text,"jangan buka chrome")

    def test_open_segments_cannot_grow_without_bound(self):
        source=StableTranscript(capacity=1)
        source.update("a",1,"hello")
        with self.assertRaises(BufferError):source.update("b",1,"world")

    def test_completed_segments_can_be_retired(self):
        source=StableTranscript(capacity=1)
        source.update("a",1,"hello",True)
        self.assertEqual(source.update("b",1,"world",True).text,"world")
        self.assertTrue(source.update("a",2,"hello",True).ignored)


class CoordinatorTests(unittest.TestCase):
    def test_no_voice_is_distinct_from_a_decision_to_listen(self):
        core=DuplexCoordinator()
        tick=core.begin(0)
        self.assertEqual(tick.heard,NO_VOICE)
        self.assertEqual(core.finish(tick,LISTEN,.05)["kind"],"listen")
        self.assertEqual(core.history,[(NO_VOICE,LISTEN)])

    def test_history_is_append_only_and_new_fragments_wait_for_next_tick(self):
        core=DuplexCoordinator()
        core.add(TranscriptDelta("saya ingin"))
        first=core.begin(0)
        core.add(TranscriptDelta("mencari artikel"))
        core.finish(first,LISTEN,.05)
        snapshot=tuple(core.history)
        second=core.begin(.6)
        self.assertEqual(second.heard,"mencari artikel")
        self.assertEqual(second.history,snapshot)
        core.finish(second,"Artikel apa?",.7)
        self.assertEqual(tuple(core.history[:1]),snapshot)

    def test_only_one_inference_inflight_and_no_tick_before_due(self):
        core=DuplexCoordinator()
        tick=core.begin(0)
        self.assertIsNone(core.begin(.7))
        core.finish(tick,LISTEN,.2)
        self.assertIsNone(core.begin(.3))
        self.assertIsNotNone(core.begin(.6))

    def test_late_answer_is_discarded_and_input_is_not_lost(self):
        core=DuplexCoordinator()
        core.add(TranscriptDelta("tentang eGPU"))
        tick=core.begin(0)
        result=core.finish(tick,"Baik, mari bahas.",.8)
        self.assertEqual(result["reason"],"deadline_missed")
        self.assertEqual(core.history,[])
        self.assertEqual(core.begin(.8).heard,"tentang eGPU")

    def test_correction_invalidates_old_inference_and_preserves_new_text(self):
        core=DuplexCoordinator()
        core.add(TranscriptDelta("buka chrome"))
        old=core.begin(0)
        core.add(TranscriptDelta("jangan buka chrome",corrected=True))
        self.assertEqual(core.finish(old,"Baik, sudah dibuka.",.1)["reason"],"stale_response")
        self.assertEqual(core.begin(.6).heard,"jangan buka chrome")

    def test_pause_invalidates_late_output_and_resume_does_not_replay_it(self):
        core=DuplexCoordinator()
        tick=core.begin(0)
        core.pause()
        self.assertFalse(core.finish(tick,"Halo",.1)["accepted"])
        self.assertIsNone(core.begin(1))
        core.resume()
        self.assertEqual(core.begin(1).heard,NO_VOICE)

    def test_excess_pending_input_pauses_instead_of_building_a_backlog(self):
        core=DuplexCoordinator(max_pending=1)
        core.add(TranscriptDelta("a"))
        with self.assertRaises(BufferError):core.add(TranscriptDelta("b"))
        self.assertTrue(core.paused)

    def test_input_character_budget_is_bounded_across_fragments(self):
        core=DuplexCoordinator()
        core.add(TranscriptDelta("a"*400))
        with self.assertRaises(BufferError):core.add(TranscriptDelta("b"*400))
        self.assertTrue(core.paused)

    def test_invalid_long_or_tagged_output_is_never_truncated_into_speech(self):
        core=DuplexCoordinator()
        tick=core.begin(0)
        self.assertEqual(core.finish(tick,"Ini jawaban panjang empat kata",.1)["reason"],"invalid_policy_output")
        for text in ("<tool>open chrome</tool>","<listen> hello","",None):
            with self.assertRaises(ValueError):parse_decision(text)

    def test_context_rollover_is_recorded_as_a_new_epoch(self):
        core=DuplexCoordinator(max_history=1)
        core.finish(core.begin(0),LISTEN,.01)
        tick=core.begin(.6)
        self.assertEqual(tick.history,())
        self.assertEqual(core.metrics["context_resets"],1)


class SpeechTests(unittest.TestCase):
    def test_cancel_flushes_and_rejects_late_audio(self):
        gate=SpeechGate()
        old=gate.enqueue("Halo")
        gate.cancel()
        self.assertIsNone(gate.coalesce())
        self.assertFalse(gate.accept_audio(old))
        new=gate.enqueue("Aku mendengarkan")
        self.assertTrue(gate.accept_audio(new))

    def test_tts_fragments_are_coalesced_without_losing_words(self):
        gate=SpeechGate()
        gate.enqueue("Baik kita")
        gate.enqueue("mulai dari koneksi")
        self.assertEqual(gate.coalesce()[1],"Baik kita mulai dari koneksi")

    def test_speech_backpressure_is_bounded(self):
        gate=SpeechGate(max_chunks=1)
        gate.enqueue("halo")
        with self.assertRaises(BufferError):gate.enqueue("lagi")

    def test_replay_is_explicitly_synthetic_and_does_not_load_devices_or_model(self):
        result=replay_scenarios()
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["microphone_opened"])
        self.assertFalse(result["model_loaded"])
        self.assertTrue(result["barge_in_flush"])
        self.assertFalse(result["stale_audio_accepted"])

    def test_baseline_is_a_separate_protocol_and_validates_context(self):
        self.assertEqual(baseline_messages([["hello",LISTEN]],NO_VOICE)[-1],{"role":"user","content":NO_VOICE})
        with self.assertRaises(ValueError):baseline_messages([["a",{},"b"]],"hello")

    def test_worker_start_message_is_explicit_without_voice_device_configuration(self):
        service=DuplexService()
        service.start=Mock()
        service.start_lab()
        service.start.assert_called_once_with(0,0,initial_message={"kind":"start"})

    def test_desktop_pause_command_stops_the_lab_without_a_voice_window(self):
        window=object.__new__(LevaWindow)
        window.closed=False
        window.generation=2
        window.events=queue.Queue()
        window.events.put((2,{"kind":"command","cancel_ai":True,"reply":"Jeda"}))
        window.desktop=Mock(paused=True,sleeping=True,memory_notice="")
        window.voice_window=None
        window.duplex_window=Mock()
        window.root=Mock()
        window.set_busy=Mock()
        window.add=Mock()
        window.activity=Mock()
        window.hud=Mock()
        window.local_mic=Mock();window.hardware=Mock();window.poll_local_mic=Mock()
        window.poll()
        window.duplex_window.stop.assert_called_once()


if __name__=="__main__":unittest.main()
