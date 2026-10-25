"""Exercise persistent settings, actual mic/phone dispatch and strict overrides."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
from contextlib import ExitStack
import unittest
from unittest.mock import Mock,patch
from preferences import Preferences,DEFAULTS
from pipeline_routing import route_spec
from speech_resources import pipeline_gpu,agent_mode,select_asr_devices
from speech_configuration import apply_pipeline_settings,configuration_snapshot,validate_pipeline_settings

class IndependentDeviceTests(unittest.TestCase):
    def main(self,folder):
        prefs=Preferences(Path(folder)/'preferences.sqlite3');self.addCleanup(prefs.close)
        return SimpleNamespace(preferences=prefs,busy=False,local_mic=Mock(),local_mic_failed=True,cancel_inference=Mock(),stop_reply_voice=Mock())

    def test_default_input_is_qwen_on_5070_but_engine_targets_are_independent(self):
        self.assertEqual((DEFAULTS['asr_model'],DEFAULTS['asr_gpu']),('qwen_asr_06b','rtx5070'))
        route=route_spec('Dual GPU')
        self.assertEqual(pipeline_gpu(route,'asr','rtx5070'),'rtx5070')
        self.assertEqual(agent_mode(route,'rtx4050'),'gpu4050')
        self.assertEqual(agent_mode(route,'auto'),'dual')
        self.assertEqual(pipeline_gpu(route,'asr','auto'),'dual')
        self.assertIsNone(agent_mode(route_spec('Tanpa AI'),'rtx5070'))
        with self.assertRaises(ValueError):pipeline_gpu(route_spec('Tanpa AI'),'asr','rtx5070')

    def test_save_reopens_preferences_and_does_not_reset_tts_or_route(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            main=self.main(folder);cleanup.callback(main.preferences.close);main.preferences.set_many({'tts_gpu':'rtx4050','provider':'Dual GPU','agent_gpu':'dual'})
            main.audio_resource_hold=True;main.root=Mock();main.ensure_local_mic=Mock()
            with patch('speech_asr.ready',return_value=True):apply_pipeline_settings(main,{'asr_gpu':'rtx5070','agent_gpu':'rtx4050'})
            main.local_mic.stop.assert_called_once();main.cancel_inference.assert_called_once()
            self.assertFalse(main.audio_resource_hold);main.root.after.assert_called_once_with(0,main.ensure_local_mic)
            other=Preferences(main.preferences.path)
            try:
                self.assertEqual(other.get('asr_gpu'),'rtx5070');self.assertEqual(other.get('agent_gpu'),'rtx4050')
                self.assertEqual(other.get('tts_gpu'),'rtx4050');self.assertEqual(other.get('provider'),'Dual GPU')
            finally:other.close()

    def test_busy_missing_model_and_phone_transcription_reject_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            main=self.main(folder);cleanup.callback(main.preferences.close);main.preferences.set('asr_gpu','rtx4050')
            for reason in ('busy','missing','phone'):
                main.busy=reason=='busy';main._web_host=Mock() if reason=='phone' else None
                with patch('speech_asr.ready',return_value=reason!='missing'):
                    with self.assertRaises(ValueError):apply_pipeline_settings(main,{'asr_gpu':'rtx5070'})
                self.assertEqual(main.preferences.get('asr_gpu'),'rtx4050');main.local_mic.stop.assert_not_called()

    def test_snapshot_matches_effective_override_and_can_never_enable_disabled_ai(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            main=self.main(folder);cleanup.callback(main.preferences.close);main.preferences.set('agent_gpu','rtx4050')
            value=configuration_snapshot(main.preferences,route_spec('Dual GPU'))
            self.assertEqual(value['effective'],{'asr_gpu':'rtx5070','agent_mode':'gpu4050'})
            self.assertIn('RTX 5070',value['summary']);self.assertIn('RTX 4050',value['summary'])
            off=configuration_snapshot(main.preferences,route_spec('Tanpa AI'))
            self.assertEqual(off['effective'],{'asr_gpu':'none','agent_mode':'gpu4050'})
            main.preferences.set('agent_provider','Tanpa AI')
            only_voice=configuration_snapshot(main.preferences,route_spec('RTX 5070'))
            self.assertEqual(only_voice['effective'],{'asr_gpu':'rtx5070','agent_mode':None})

    def test_explicit_input_does_not_fall_back_when_selected_card_has_no_room(self):
        rows=[{'name':'RTX 4050','uuid':'other','free_mib':5000},{'name':'RTX 5070','uuid':'target','free_mib':100}]
        with self.assertRaises(ValueError):select_asr_devices(rows,'qwen_asr_06b','rtx5070')

    def test_web_command_uses_same_transaction_and_rejects_unknown_keys(self):
        from web_bridge import WebBridge
        from web_store import WebStore
        from web_host import DesktopWebHost
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            main=self.main(folder);cleanup.callback(main.preferences.close);store=WebStore(Path(folder)/'web.sqlite3');cleanup.callback(store.close)
            bridge=WebBridge(None,port=0,store=store)
            for value in ({'workspace_root':folder},{'asr_gpu':'cuda:0'},[],{}):
                with self.assertRaises(ValueError):bridge.submit({'id':'invalid-config','kind':'pipeline_settings','value':value})
            bridge.submit({'id':'pipeline-change','kind':'pipeline_settings','value':{'asr_gpu':'rtx4050','agent_gpu':'rtx5070'}})
            host=DesktopWebHost.__new__(DesktopWebHost);host.main=main
            with patch('speech_asr.ready',return_value=True):host.control(bridge.controls.get_nowait())
            self.assertEqual((main.preferences.get('asr_gpu'),main.preferences.get('agent_gpu')),('rtx4050','rtx5070'))

    def test_agent_provider_and_voice_route_change_independently_in_gui_dispatch(self):
        import time
        from test_task_reactions import TaskReactionTests
        from preferences import DEFAULTS
        for voice,agent,expected in [('RTX 4050','Google → 9Router → RTX 5070',('cascade','gpu5070')),
                                     ('Tanpa AI','RTX 5070',('local','gpu5070'))]:
            fixture=TaskReactionTests();main=fixture.window('id')
            values={**DEFAULTS,'provider':voice,'agent_provider':agent,'agent_local_model':'saluki','speech_language':'id','asr_model':'qwen_asr_06b','router_model':'fixture-model'}
            main.router_gateway=Mock()
            main.preferences.get.side_effect=values.__getitem__;main.mode.get.return_value=voice
            main.desktop.handle.return_value={'kind':'chat'};main.chat.ask.return_value={'response':'Selesai fixture.','provider':'local'}
            with patch('conversation_frontend.conversation_request',return_value={'kind':'delegate','summary':'fixture'}),patch('task_reactions.cached_reaction',return_value=None):
                main.send('Buat proyek web contoh.')
                until=time.monotonic()+3
                while not main.chat.ask.called and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(main.chat.ask.call_args.args[1:3],expected)
                if expected[0]=='cascade':main.router_gateway.start.assert_called_once_with(DEFAULTS['router_url'])
                else:main.router_gateway.start.assert_not_called()
                fixture.wait(lambda:not main.events.empty())

if __name__=='__main__':unittest.main()
