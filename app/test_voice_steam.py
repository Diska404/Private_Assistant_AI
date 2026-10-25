import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch

from assistant_tools import AssistantTools,AppCatalog,requested_voice_language,effective_speech_language,validate_call
from desktop_service import DesktopService
from preferences import Preferences
from steam_catalog import SteamCatalog
from agent_runtime import run_agent
from test_desktop import INVENTORY


class VoiceSteamTests(unittest.TestCase):
    def desktop(self,preferences):
        if isinstance(preferences,Mock):preferences.aliases.return_value={};preferences.suggestions.return_value={}
        with patch('desktop_service.inspect_profiles',return_value=INVENTORY):return DesktopService(browser=Mock(),preferences=preferences)

    def test_exact_user_language_sequence_changes_setting_and_reply_language(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.sqlite3';prefs=Preferences(path);desktop=self.desktop(prefs)
            first=desktop.handle('ubah modul suara mu ke bahasa jepang')
            self.assertEqual(prefs.get('speech_language'),'ja');self.assertEqual(effective_speech_language(first,'id'),'ja')
            second=desktop.handle('ubah modul suara saja, untuk balasan bentuk teks tetap dengan bahasa indonesia')
            self.assertNotIn('voice_language',second);self.assertEqual(prefs.get('speech_language'),'ja')
            third=desktop.handle('gunakan kembali modul suara indonesia')
            self.assertEqual(prefs.get('speech_language'),'id');self.assertEqual(effective_speech_language(third,'ja'),'id')
            reopened=Preferences(path)
            self.assertEqual(reopened.get('speech_language'),'id');reopened.close();prefs.close()
            self.assertIn('Balasan teks tetap bahasa Indonesia',third['reply'])

    def test_setting_write_failure_does_not_confirm_success(self):
        prefs=Mock();prefs.set.side_effect=OSError('unavailable');prefs.get.return_value='id'
        result=self.desktop(prefs).handle('ubah suara ke Jepang')
        self.assertEqual(result['status'],'failed');self.assertNotIn('voice_language',result)

    def test_voice_claim_does_not_change_effective_language(self):
        self.assertEqual(effective_speech_language({'response':'Suara sudah kembali Indonesia'},'ja'),'ja')
        self.assertEqual(effective_speech_language({'tool_receipts':[{'name':'set_voice_language','result':{'status':'done','voice_language':'id'}}]},'ja'),'id')

    def test_language_commands_do_not_execute_from_quotes_negation_or_text_only(self):
        for phrase in ('jangan ubah suara ke Jepang','contoh gunakan suara Jepang','ubah teks ke bahasa Jepang','bagaimana cara ubah suara ke Jepang','ubah suara saja, balasan teks tetap Indonesia'):
            self.assertIsNone(requested_voice_language(phrase),phrase)
        with self.assertRaises(ValueError):validate_call('set_voice_language',{'language':'en'})

    def test_language_skill_cannot_change_unrequested_language(self):
        tools=AssistantTools(self.desktop(Mock()))
        result=tools.execute('set_voice_language',{'language':'ja'},'hai')
        self.assertEqual(result['status'],'needs_input');tools.desktop.preferences.set.assert_not_called()

    def test_app_context_retains_requested_app_outside_first_twenty(self):
        catalog=AppCatalog();catalog.apps={}
        for n in range(85):catalog.add('Fixture'+str(n),Path('C:/fixture')/(str(n)+'.exe'))
        catalog.add('Steam',Path('C:/fixture/steam.exe'),('steam',),'steam.exe')
        self.assertEqual(len(catalog.public()),86)
        self.assertEqual(catalog.relevant('coba buka steam dulu')[0]['name'],'Steam')

    def fixture_steam(self,folder):
        root=Path(folder);exe=root/'steam.exe';exe.touch();apps=root/'steamapps';apps.mkdir()
        game=apps/'common/GFL2';game.mkdir(parents=True)
        (apps/'appmanifest_3347400.acf').write_text('"AppState" { "appid" "3347400" "name" "GIRLS FRONTLINE 2 EXILIUM" "installdir" "GFL2" "StateFlags" "4" }')
        return SteamCatalog(exe)

    def test_game_id_and_aliases_come_from_installed_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=self.fixture_steam(folder)
            self.assertEqual(catalog.resolve('gfl2 exilium')['id'],'3347400')
            self.assertIsNone(catalog.resolve('not-installed'))
            with patch('steam_catalog.subprocess.Popen') as popen:
                self.assertEqual(catalog.launch('not-installed')['status'],'needs_input');popen.assert_not_called()

    def test_unready_or_traversing_manifest_is_not_launchable(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=self.fixture_steam(folder);manifest=Path(folder)/'steamapps/appmanifest_3347400.acf'
            original=manifest.read_text()
            for changed in (original.replace('"4"','"2"'),original.replace('"GFL2"','"../GFL2"')):
                manifest.write_text(changed);self.assertEqual(SteamCatalog(catalog.executable).public(),[])

    def test_game_launch_uses_verified_id_and_does_not_claim_lobby(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=self.fixture_steam(folder)
            with patch('windows_runtime.application_windows',side_effect=[[],[42]]),patch('steam_catalog.subprocess.Popen') as popen:
                result=catalog.launch('gfl2')
            self.assertEqual(popen.call_args.args[0],[str(catalog.executable),'-applaunch','3347400'])
            self.assertTrue(result['window_observed']);self.assertFalse(result['lobby_verified'])

    def test_game_not_visible_is_unverified_and_cancellation_never_spawns(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=self.fixture_steam(folder)
            with patch('windows_runtime.application_windows',return_value=[]),patch('steam_catalog.subprocess.Popen') as popen,patch('steam_catalog.time.monotonic',side_effect=[0,41]):
                result=catalog.launch('gfl2')
            self.assertEqual(result['status'],'unverified');self.assertFalse(result['window_observed'])
            with patch('steam_catalog.subprocess.Popen') as popen:
                self.assertEqual(catalog.launch('gfl2',lambda:False)['status'],'cancelled');popen.assert_not_called()

    def test_game_skill_requires_game_in_user_request(self):
        tools=AssistantTools(self.desktop(Mock()))
        with tempfile.TemporaryDirectory() as folder:
            tools.steam=self.fixture_steam(folder)
            with patch.object(tools.steam,'launch') as launch:
                self.assertEqual(tools.execute('launch_game',{'game':'3347400'},'buka steam')['status'],'needs_input');launch.assert_not_called()
                tools.execute('launch_game',{'game':'3347400'},'bukakan steam dan jalankan gfl2 exilium')
                launch.assert_called_once()

    def test_steam_tracked_handoff_accepts_live_pid_and_rejects_recycled_pid(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as folder:
            catalog=self.fixture_steam(folder);logs=Path(folder)/'logs';logs.mkdir()
            (logs/'gameprocess_log.txt').write_text('[2026-10-19 14:05:18] AppID 3347400 adding PID 10 as a tracked process\n[2026-10-19 14:05:38] AppID 3347400 no longer tracking PID 10, exit code 0\n[2026-10-19 14:05:49] AppID 3347400 adding PID 11 as a tracked process\n[2026-10-19 14:05:49] AppID 999 adding PID 12 as a tracked process\n')
            stamp=datetime(2026,10,19,14,5,49).timestamp()
            with patch('psutil.Process') as process:
                process.return_value.create_time.return_value=stamp-1
                self.assertEqual(catalog.tracked_processes('3347400'),[11])
                process.assert_called_once_with(11)
                process.return_value.create_time.return_value=stamp+1000
                self.assertEqual(catalog.tracked_processes('3347400'),[])

    def test_agent_game_launch_releases_model_before_host_and_does_not_reload(self):
        local=Mock();local.propose_tool.return_value={'action':'launch_game','args':{'game':'3347400'}}
        commands=queue.Queue()
        def emit(event):
            local.close.assert_called_once()
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'unverified','reply':'Permintaan terkirim, belum terkonfirmasi.'}})
        result=run_agent({'id':1,'mode':'local','speech_language':'ja','messages':[{'role':'user','content':'jalankan gfl2'}]},local,commands,emit)
        self.assertTrue(result['game_launch']);self.assertIn('未',result['speech_text'].replace('まだ','未'))
        local.propose_tool.assert_called_once()

if __name__=='__main__':unittest.main()
