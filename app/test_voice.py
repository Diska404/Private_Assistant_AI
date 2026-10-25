from array import array
import json
import math
from pathlib import Path
import sys
import unittest
import queue
from unittest.mock import Mock

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/"experiments")]
from voice_core import PlaybackBuffer, pcm_level, voice_setup, STATES, direct_command
from neural_orb import particle
from live_voice import classify_voice_error
from gui import LevaWindow


class AudioBufferTests(unittest.TestCase):
    def test_interruption_discards_queued_speech_and_new_turn_remains(self):
        buffer=PlaybackBuffer()
        buffer.push(b"old speech")
        buffer.clear()
        buffer.push(b"new")
        actual,padded=buffer.pop(8)
        self.assertEqual(actual,b"new")
        self.assertEqual(padded,b"new"+bytes(5))
        self.assertEqual(len(buffer),0)

    def test_backlog_is_bounded_instead_of_speaking_stale_audio(self):
        buffer=PlaybackBuffer(max_bytes=4)
        buffer.push(b"1234")
        with self.assertRaises(BufferError):
            buffer.push(b"5")
        self.assertEqual(len(buffer),4)

    def test_audio_meters_measure_real_samples_and_silence(self):
        self.assertEqual(pcm_level(bytes(100)),0)
        self.assertEqual(pcm_level(b""),0)
        self.assertGreater(pcm_level(array("h",[3500,-3500]*100).tobytes()),0.4)
        self.assertLessEqual(pcm_level(array("h",[32767]*100).tobytes()),1)

    def test_setup_uses_duplex_audio_and_interruptions_without_action_tools(self):
        setup=voice_setup()["setup"]
        self.assertEqual(setup["realtimeInputConfig"]["activityHandling"],"START_OF_ACTIVITY_INTERRUPTS")
        self.assertFalse(setup["realtimeInputConfig"]["automaticActivityDetection"]["disabled"])
        self.assertNotIn("tools",setup)
        self.assertEqual(setup["generationConfig"]["responseModalities"],["AUDIO"])

    def test_error_classification_never_exposes_server_reason_or_credentials(self):
        class Closed(Exception):
            rcvd=type("Frame",(),{"code":1011,"reason":"quota exhausted SECRET_SENTINEL"})()
        code=classify_voice_error(Closed())
        self.assertEqual(code,"live_quota_or_capacity")
        self.assertNotIn("SECRET",code)

    def test_direct_actions_require_wake_prefix_and_supported_intent(self):
        for text in ["Leva, buka Chrome", "Leva buka YouTube di profil Diska", "Leva, jedakan sistemmu"]:
            self.assertTrue(direct_command(text))
        for text in ["buka Chrome", "Leva, hapus semua file", "Leva, buka Discord", "Leva, jangan buka Chrome",
                     "contoh Leva buka Chrome", "Leva, kirim pesan ke teman"]:
            self.assertFalse(direct_command(text))


class NeuralGeometryTests(unittest.TestCase):
    def test_all_states_have_finite_bounded_geometry(self):
        for state in STATES:
            for index in range(220):
                point=particle(index,220,15.3,state,0.9)
                self.assertTrue(all(math.isfinite(v) and abs(v)<1.5 for v in point))

    def test_audio_changes_speaking_shape_and_sleep_flattens_it(self):
        silent=particle(34,220,1.2,"speaking",0)
        speaking=particle(34,220,1.2,"speaking",0.8)
        self.assertNotEqual(silent,speaking)
        awake_extent=max(abs(particle(i,220,0,"idle")[1]) for i in range(220))
        sleep_extent=max(abs(particle(i,220,0,"sleeping")[1]) for i in range(220))
        self.assertLess(sleep_extent,awake_extent*0.6)


class VoicePrivacyLifecycleTests(unittest.TestCase):
    def test_completed_pause_command_closes_voice_even_if_timer_was_already_paused(self):
        window=object.__new__(LevaWindow)
        window.closed=False
        window.generation=4
        window.events=queue.Queue()
        window.events.put((4,{"kind":"command","cancel_ai":True,"reply":"Dijeda"}))
        window.desktop=Mock(paused=True,sleeping=True)
        window.voice_window=Mock()
        window.root=Mock()
        window.set_busy=Mock()
        window.add=Mock()
        window.activity=Mock()
        window.hud=Mock()
        window.local_mic=Mock();window.hardware=Mock();window.poll_local_mic=Mock()
        window.poll()
        window.voice_window.stop.assert_called_once_with(sleeping=True)


if __name__=="__main__":
    unittest.main()
