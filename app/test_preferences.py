import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/"experiments")]
from preferences import Preferences, MODES
from desktop_service import DesktopService
from test_desktop import INVENTORY
from voice_core import VoiceEvents, preferred_device
from voice_window import VoiceWindow
from live_voice import LiveVoiceService, voice_worker


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"prefs.sqlite3"
        self.store=Preferences(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_settings_and_alias_survive_restart_without_conversation_data(self):
        self.store.set_many({"provider":MODES[1],"voice":"Leda","dual_gpu":True})
        self.store.set_alias("Frontline Raver","id1")
        self.store.record("youtube","id1")
        self.store.close()
        self.store=Preferences(self.path)
        self.assertEqual(self.store.get("provider"),MODES[1])
        self.assertEqual(self.store.get("voice"),"Leda")
        self.assertEqual(self.store.aliases(),{"frontline raver":"id1"})
        self.assertEqual(self.store.habits()[0]["uses"],1)
        columns={row[1] for row in self.store.db.execute("PRAGMA table_info(habits)")}
        self.assertEqual(columns,{"action","profile_id","uses","last_used"})

    def test_invalid_batch_does_not_partially_save_or_accept_unknown_fields(self):
        with self.assertRaises(ValueError):
            self.store.set_many({"provider":MODES[1],"dual_gpu":"yes"})
        self.assertEqual(self.store.get("provider"),MODES[0])
        for key,value in [("api_key","secret"),("microphone_on",True),("animation",{}),("voice","unknown")]:
            with self.assertRaises(ValueError):
                self.store.set(key,value)

    def test_corrupt_value_uses_default_and_corrupt_file_is_preserved(self):
        self.store.db.execute("INSERT INTO settings VALUES ('dual_gpu','not json')")
        self.assertFalse(self.store.get("dual_gpu"))
        damaged=Path(self.temp.name)/"damaged.sqlite3"
        damaged.write_bytes(b"not-a-database")
        fallback=Preferences(damaged)
        try:
            self.assertFalse(fallback.persistent)
            fallback.set("voice","Puck")
            self.assertEqual(fallback.get("voice"),"Puck")
            self.assertEqual(damaged.read_bytes(),b"not-a-database")
        finally:
            fallback.close()

    def test_habits_need_three_uses_unique_leader_and_current_inventory(self):
        for _ in range(2): self.store.record("youtube","a")
        self.assertEqual(self.store.suggestions({"a","b"}),{})
        self.store.record("youtube","a")
        self.assertEqual(self.store.suggestions({"a","b"}),{"youtube":"a"})
        for _ in range(3): self.store.record("youtube","b")
        self.assertEqual(self.store.suggestions({"a","b"}),{})
        self.store.record("youtube","b")
        self.assertEqual(self.store.suggestions({"a","b"}),{"youtube":"b"})
        self.assertEqual(self.store.suggestions(set()),{})

    def test_disabled_learning_does_not_count_or_suggest_and_clear_removes_it(self):
        for _ in range(3): self.store.record("youtube","a")
        self.store.set("learn_habits",False)
        self.store.record("youtube","a")
        self.assertEqual(self.store.habits()[0]["uses"],3)
        self.assertEqual(self.store.suggestions({"a"}),{})
        self.store.clear_habits()
        self.assertEqual(self.store.habits(),[])

    def test_alias_cannot_steal_an_existing_alias_or_contain_command(self):
        self.store.set_alias("raver","a")
        for alias,pid in [("raver","b"),("buka youtube","a"),("x; exit","a")]:
            with self.assertRaises(ValueError): self.store.set_alias(alias,pid)
        self.assertEqual(self.store.aliases(),{"raver":"a"})

    def test_parallel_settings_and_counts_use_one_consistent_database(self):
        errors=[]
        def record():
            try:
                for _ in range(30): self.store.record("chrome","a")
            except Exception as e: errors.append(str(e))
        threads=[threading.Thread(target=record) for _ in range(3)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[])
        self.assertEqual(self.store.habits()[0]["uses"],90)

    def make_desktop(self):
        browser=Mock()
        browser.launch.return_value={"dispatched":True,"new_window_observed":True,"profile_verified_in_window":False}
        with patch("desktop_service.inspect_profiles",return_value=INVENTORY):
            return DesktopService(browser,preferences=self.store),browser

    def test_learned_profile_is_a_question_and_requires_confirmation(self):
        desktop,browser=self.make_desktop()
        for _ in range(3): desktop.handle("buka YouTube di profil Diska")
        self.assertEqual(browser.launch.call_count,3)
        result=desktop.handle("buka YouTube di Chrome")
        self.assertIn("seperti biasanya",result["reply"])
        self.assertEqual(browser.launch.call_count,3)
        desktop.handle("iya")
        self.assertEqual(browser.launch.call_count,4)
        desktop.handle("buka YouTube")
        desktop.handle("tidak")
        self.assertEqual(browser.launch.call_count,4)

    def test_failed_or_unobserved_launch_does_not_train_a_habit(self):
        desktop,browser=self.make_desktop()
        browser.launch.return_value={"dispatched":True,"new_window_observed":False}
        desktop.handle("buka Chrome Diska")
        browser.launch.side_effect=OSError("failed")
        desktop.handle("buka Chrome Diska")
        self.assertEqual(self.store.habits(),[])

    def test_alias_works_and_conflicting_alias_does_not_change_profile(self):
        desktop,browser=self.make_desktop()
        pid=INVENTORY["profiles"][0]["id"]
        desktop.add_alias("Frontline Raver",pid)
        desktop.handle("buka Chrome profil Frontline Raver")
        browser.launch.assert_called_once_with(INVENTORY["profiles"][0],False)
        with self.assertRaises(ValueError):desktop.add_alias("Hiburan",pid)

    def test_long_session_keeps_host_turn_cache_bounded(self):
        desktop,browser=self.make_desktop()
        for _ in range(300):desktop.handle("halo")
        self.assertLessEqual(len(desktop.controller.results),128)
        browser.launch.assert_not_called()


class VoiceRecoveryTests(unittest.TestCase):
    def test_meter_flood_is_coalesced_and_terminal_error_survives(self):
        events=VoiceEvents()
        for i in range(1000): events.put_nowait({"kind":"meter","input":i})
        events.put_nowait({"kind":"error","code":"synthetic"})
        events.put_nowait({"kind":"stopped"})
        self.assertEqual(events.get_nowait()["kind"],"error")
        self.assertEqual(events.get_nowait()["kind"],"stopped")
        self.assertTrue(events.empty())

    def test_saved_device_follows_name_not_changed_id_and_missing_is_not_replaced(self):
        devices=[{"id":5,"name":"Headset"},{"id":1,"name":"Laptop"}]
        self.assertEqual(preferred_device(devices,"Headset",1),5)
        self.assertIsNone(preferred_device(devices,"Missing",1))
        self.assertIsNone(preferred_device(devices+[{"id":7,"name":"Headset"}],"Headset",1))
        self.assertEqual(preferred_device(devices,"",1),1)

    def test_stop_clears_command_authority_before_a_new_voice_session(self):
        window=object.__new__(VoiceWindow)
        for name in ("service","orb","meter","notice","start","inputs","outputs","voices","demo","run_button","heading","direct"):
            setattr(window,name,Mock())
        window.final_text="Leva buka Chrome"
        window.last_text=window.final_text
        window.stop()
        self.assertEqual(window.final_text,"")
        self.assertFalse(window.mic_open)
        window.direct.set.assert_called_once_with(False)
        window.main=Mock(busy=False)
        window.run_command()
        window.main.send.assert_not_called()

    def test_a_final_transcript_is_consumed_once_even_on_repeated_button_presses(self):
        window=object.__new__(VoiceWindow)
        window.main=Mock(busy=False)
        window.run_button=Mock()
        window.final_text="Leva buka Chrome Diska"
        window.run_command()
        window.run_command()
        window.main.send.assert_called_once_with("Leva buka Chrome Diska",commands_only=True)

    def test_input_stream_is_closed_if_output_construction_fails(self):
        microphone=Mock()
        ws=Mock()
        ws.recv.return_value=json.dumps({"setupComplete":{}})
        fake_audio=Mock()
        fake_audio.RawInputStream.return_value=microphone
        fake_audio.RawOutputStream.side_effect=RuntimeError("synthetic output failure")
        events=[]
        with patch.dict(sys.modules,{"sounddevice":fake_audio}),patch("live_voice.connect_live",return_value=ws),patch("sys.stdin",io.StringIO("")):
            voice_worker({"input_device":1,"output_device":2},events.append)
        microphone.close.assert_called_once()
        self.assertTrue(any(e.get("kind")=="stopped" for e in events))

    def test_unexpected_worker_exit_reports_error_without_microphone_or_network(self):
        script="import sys,json; sys.stdin.readline(); print(json.dumps({'kind':'state','state':'connecting'}),flush=True)"
        service=LiveVoiceService([sys.executable,"-u","-c",script])
        try:
            service.start(1,2)
            deadline=time.monotonic()+4
            events=[]
            while time.monotonic()<deadline:
                try:events.append(service.events.get_nowait())
                except queue.Empty:time.sleep(0.01)
                if any(e.get("kind")=="stopped" for e in events):break
            self.assertIn("voice_worker_unexpected_exit",[e.get("code") for e in events])
            self.assertFalse(service.active)
        finally:service.stop()


if __name__=="__main__":unittest.main()
