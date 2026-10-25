from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "experiments")]
from command_resolution import WIB
from desktop_service import DesktopService
from chat_service import ChatService, bounded_history, run_worker
from hybrid_engine import EngineError
from windows_runtime import ProcessJob


INVENTORY = {"profiles": [
    {"id": "chrome-stable:Profile 1", "name": "Diska", "channel": "stable", "profile_directory": "Profile 1",
     "user_data_root": "C:/fixture", "directory_exists": True},
    {"id": "chrome-stable:Profile 2", "name": "Hiburan", "channel": "stable", "profile_directory": "Profile 2",
     "user_data_root": "C:/fixture", "directory_exists": True}]}


class DesktopCommandTests(unittest.TestCase):
    now = datetime(2026, 10, 18, 23, tzinfo=WIB)

    def setUp(self):
        self.browser = Mock()
        self.browser.launch.return_value = {"dispatched": True, "new_window_observed": True,
                                           "profile_verified_in_window": False}
        with patch("desktop_service.inspect_profiles", return_value=INVENTORY):
            self.desktop = DesktopService(self.browser)

    def test_profile_question_does_not_launch_until_named_choice(self):
        self.desktop.handle("buka YouTube", self.now)
        self.browser.launch.assert_not_called()
        result = self.desktop.handle("Diska", self.now)
        self.browser.launch.assert_called_once_with(INVENTORY["profiles"][0], True)
        self.assertNotIn("simulasi", result["reply"])
        self.assertIn("dikirim", result["reply"])
        self.assertFalse(result["evidence"]["profile_verified_in_window"])

    def test_failed_browser_does_not_report_success(self):
        self.browser.launch.side_effect = OSError("unavailable")
        result = self.desktop.handle("buka Chrome Diska", self.now)
        self.assertFalse(result["success"])
        self.assertNotIn("sudah dikirim", result["reply"])

    def test_model_chat_cannot_launch_browser(self):
        self.assertEqual(self.desktop.handle("halo, apa kabar?", self.now)["kind"], "chat")
        self.browser.launch.assert_not_called()

    def test_unknown_actions_route_to_planner_without_executing_them(self):
        with patch('assistant_tools.AppCatalog.launch',return_value={'status':'done','reply':'Discord terdeteksi.'}) as launch:
            self.assertEqual(self.desktop.handle('buka Discord',self.now)['kind'],'command')
            launch.assert_called_once_with('discord')
        for text in ["hapus semua file", "kirim email", "skip iklan"]:
            self.assertTrue(self.desktop.handle(text,self.now)['needs_tools'])
        self.browser.launch.assert_not_called()

    def test_pause_blocks_commands_and_resume_does_not_launch(self):
        self.desktop.handle("jeda sistemmu", self.now)
        self.desktop.handle("buka Chrome Diska", self.now)
        self.browser.launch.assert_not_called()
        self.desktop.handle("aktifkan", self.now)
        self.desktop.handle("buka Chrome Diska", self.now)
        self.browser.launch.assert_called_once()

    def test_real_sleep_timer_state_activity_and_manual_override(self):
        result = self.desktop.handle("aku mau tidur sampai besok setengah lima pagi", self.now)
        self.assertTrue(result["cancel_ai"])
        self.assertTrue(self.desktop.sleeping)
        wake = self.desktop.controller.sleep.next_transition
        with patch("desktop_service.idle_milliseconds", return_value=3600000):
            self.desktop.tick(wake)
            self.assertEqual(self.desktop.controller.sleep.mode, "observing")
            self.desktop.tick(wake + timedelta(minutes=30))
            self.assertEqual(self.desktop.controller.sleep.mode, "paused")
        with patch("desktop_service.idle_milliseconds", return_value=0):
            self.desktop.tick(wake + timedelta(minutes=90))
            self.assertEqual(self.desktop.controller.sleep.mode, "off")
        self.desktop.handle("jeda sampai besok jam empat subuh", self.now)
        self.desktop.pause()
        self.assertIsNone(self.desktop.controller.sleep.next_transition)

    def test_profile_refresh_clears_prior_task_and_timer(self):
        self.desktop.handle("aku mau tidur sampai besok 04:30", self.now)
        with patch("desktop_service.inspect_profiles", return_value=INVENTORY):
            self.desktop.refresh_profiles()
        self.assertIsNone(self.desktop.controller.pending)
        self.assertFalse(self.desktop.sleeping)


class WorkerTests(unittest.TestCase):
    def test_empty_request_rejected_before_loading_model(self):
        with patch("chat_service.LocalEngine") as engine:
            with self.assertRaises(EngineError) as error:
                run_worker({"messages": [{"role": "user", "content": ""}]})
            self.assertEqual(str(error.exception), "invalid_chat_request")
            engine.return_value.generate.assert_not_called()

    def test_history_is_bounded_and_latest_message_kept(self):
        data = [{"role": "user", "content": str(i) * 1000} for i in range(10)]
        history = bounded_history(data)
        self.assertEqual(history[-1], data[-1])
        self.assertLessEqual(sum(len(m["content"]) for m in history), 6500)

    def test_worker_pipe_and_owned_process_cleanup(self):
        service = ChatService()
        with self.assertRaises(EngineError) as error:
            service.ask("", "local")
        self.assertEqual(str(error.exception), "invalid_chat_request")
        self.assertIsNone(service.process)
        self.assertIsNone(service.job)

    def test_job_close_kills_worker_and_descendants(self):
        import psutil
        script = ("import subprocess,sys,time; sys.stdin.readline(); "
                  "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(40)']); "
                  "print(p.pid,flush=True); time.sleep(40)")
        process = subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        job = ProcessJob(process)
        try:
            process.stdin.write("go\n")
            process.stdin.flush()
            child_pid = int(process.stdout.readline())
            child = psutil.Process(child_pid)
            job.close()
            process.wait(timeout=5)
            child.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
        finally:
            job.close()
            process.stdin.close()
            process.stdout.close()

    def test_cancel_returns_without_leaving_the_chat_worker(self):
        script = "import sys,time,json; json.load(sys.stdin); time.sleep(40)"
        service = ChatService([sys.executable, "-u", "-c", script])
        results = []
        errors = []
        def ask():
            try:
                results.append(service.ask("synthetic input", "local"))
            except Exception as error:
                errors.append(str(error))
        thread = threading.Thread(target=ask)
        thread.start()
        deadline = time.monotonic() + 3
        while service.process is None and time.monotonic() < deadline:
            time.sleep(0.01)
        service.cancel()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [{"cancelled": True}])
        self.assertIsNone(service.process)


if __name__ == "__main__":
    unittest.main()
