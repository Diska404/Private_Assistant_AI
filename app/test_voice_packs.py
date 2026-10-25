import array
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import wave

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "experiments")]
from preferences import Preferences
from voice_packs import catalog, resolve_pack, validate_preview, validate_text, verify_piper
from voice_pack_service import VoicePackService
from gui import LevaWindow
from voice_pack_window import VoicePackWindow


class VoicePackTests(unittest.TestCase):
    def test_manager_layout_constructs_with_real_label_and_button_signatures(self):
        class Variable:
            def __init__(self, value=None): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
            def trace_add(self, mode, callback): return 'fixture-trace'
        main = Mock()
        main.preferences.get.return_value = "leva_gfl2"
        main.label = LevaWindow.label.__get__(main)
        main.button = LevaWindow.button.__get__(main)
        with ExitStack() as stack:
            for widget in ("Toplevel", "Frame", "Radiobutton", "Text", "Label", "Button"):
                stack.enter_context(patch("voice_pack_window.tk." + widget))
            stack.enter_context(patch("voice_pack_window.tk.StringVar", Variable))
            stack.enter_context(patch('voice_pack_window.resolve_pack',return_value=resolve_pack('leva_gfl2',runtime_available=True,candidate_ready=True)))
            window = VoicePackWindow(main)
            self.assertIn("Kandidat Leva A", window.summary.get())
            self.assertFalse(window.service.active)
            window.close()

    def test_pending_target_and_historical_rvc_never_acquire_leva_identity(self):
        for target in ("leva_gfl2", "shiroko_rvc"):
            result = resolve_pack(target, runtime_available=True, candidate_ready=False)
            self.assertEqual(result["requested"], target)
            self.assertEqual(result["actual"], "neutral_id")
            self.assertTrue(result["fallback"])
        self.assertIsNone(resolve_pack("leva_gfl2", runtime_available=False)["actual"])
        with self.assertRaises(ValueError):
            resolve_pack("renamed-shiroko")

    def test_candidate_requires_implemented_engine_assets_and_piper(self):
        self.assertEqual(resolve_pack('leva_gfl2',runtime_available=True,candidate_ready=True)['actual'],'leva_gfl2')
        self.assertIsNone(resolve_pack('leva_gfl2',runtime_available=False,candidate_ready=True)['actual'])
        packs=catalog(); packs['leva_gfl2']['engine']='unassigned'
        self.assertEqual(resolve_pack('leva_gfl2',packs,True,True)['actual'],'neutral_id')

    def test_catalog_cannot_promote_unimplemented_engine_by_a_ready_flag(self):
        packs = catalog()
        packs["leva_gfl2"].update(engine="rvc", status="file_proven")
        self.assertEqual(resolve_pack("leva_gfl2", packs, True)["actual"], "neutral_id")
        packs["neutral_id"]["engine"] = "unassigned"
        self.assertIsNone(resolve_pack("leva_gfl2", packs, True)["actual"])

    def test_target_survives_restart_separately_from_google_live_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.db"
            store = Preferences(path)
            self.assertEqual(store.get("target_voice_pack"), "leva_gfl2")
            store.set_many({"target_voice_pack": "shiroko_rvc", "voice": "Leda"})
            store.close()
            store = Preferences(path)
            try:
                self.assertEqual(store.get("target_voice_pack"), "shiroko_rvc")
                self.assertEqual(store.get("voice"), "Leda")
                with self.assertRaises(ValueError):
                    store.set("target_voice_pack", "arbitrary-model.pth")
            finally:
                store.close()

    def test_model_tampering_is_detected_before_loading_the_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "id_ID-news_tts-medium.onnx"
            model.write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(ValueError, "hash_mismatch"):
                verify_piper(model)

    def test_preview_rejects_escape_silence_and_wrong_audio_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            path = parent / "sample.wav"
            def make(rate, value):
                with wave.open(str(path), "wb") as out:
                    out.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                    out.writeframes(array.array("h", [value] * 5000).tobytes())
            make(22050, 100)
            self.assertEqual(validate_preview(path, parent)[0], path.resolve())
            with self.assertRaisesRegex(ValueError, "path"):
                validate_preview(path, parent / "different")
            make(22050, 0)
            with self.assertRaisesRegex(ValueError, "silent"):
                validate_preview(path, parent)
            make(16000, 100)
            with self.assertRaisesRegex(ValueError, "audio"):
                validate_preview(path, parent)

    def test_invalid_text_never_starts_a_worker(self):
        service = VoicePackService()
        with patch.object(service.worker, "start") as start:
            for value in ("", " " * 10, "a" * 601, "a\x00b", None):
                with self.assertRaises(ValueError):
                    service.generate("leva_gfl2", value)
            start.assert_not_called()

    def test_stop_kills_owned_synthesis_and_discards_late_results(self):
        service = VoicePackService()
        with tempfile.TemporaryDirectory() as directory, patch("voice_pack_service.PREVIEWS", Path(directory)), \
                patch('voice_pack_service.resolve_pack',return_value=resolve_pack('leva_gfl2',runtime_available=True,candidate_ready=True)), \
                patch('voice_pack_service.CANDIDATE_PYTHON',Path(sys.executable)):
            service.script=Path(directory)/'fixture_worker.py'
            service.script.write_text('import sys,time\nsys.stdin.readline()\ntime.sleep(30)\n',encoding='utf8')
            try:
                service.generate("leva_gfl2", "Ini teks uji.")
                process = service.worker.process
                folder = Path(service.folder.name)
                self.assertTrue(service.active)
                service.stop()
                self.assertIsNotNone(process.poll())
                self.assertFalse(service.active)
                self.assertFalse(folder.exists())
                with self.assertRaisesRegex(ValueError, "stale"):
                    service.accept_generated({"actual_pack": "neutral_id", "path": str(folder / "speech.wav")})
            finally:
                service.stop()

    def test_foreign_file_and_stale_worker_cannot_replace_the_current_preview(self):
        service = VoicePackService()
        service.folder = Mock(name="folder")
        service.folder.name = str(Path(tempfile.gettempdir()) / "synthetic-current")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            service.accept_generated({"actual_pack": "neutral_id", "path": str(Path(tempfile.gettempdir()) / "other.wav")})
        self.assertIsNone(service.generated)

    def test_pause_release_and_close_stop_the_pack_owned_resources(self):
        for action in ("toggle_pause", "release", "close"):
            main = object.__new__(LevaWindow)
            main.chat = Mock()
            main.voice_pack_window = Mock()
            main.voice_window = main.duplex_window = None
            main.activity = Mock()
            main.add = Mock()
            main.desktop = Mock(paused=False)
            main.desktop.controller.sleep.mode = "off"
            main.root = Mock()
            main.local_mic=Mock();main.hardware=Mock();main.generation=0;main.set_busy=Mock()
            getattr(main, action)()
            main.local_mic.stop.assert_called_once()
            getattr(main.voice_pack_window, "close" if action == "close" else "stop").assert_called_once()

    def test_startup_and_unready_playback_never_open_audio(self):
        with patch.dict(sys.modules, {"sounddevice": Mock()}) as modules:
            service = VoicePackService()
            self.assertFalse(service.active)
            self.assertFalse(service.play())
            service.stop()
            modules["sounddevice"].RawOutputStream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
