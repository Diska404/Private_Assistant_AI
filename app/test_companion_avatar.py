"""Four-mode privacy and avatar contracts; no audio, GPU, model or desktop action."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from companion_avatar import AvatarDirector,configure,interrupt,presentation
from conversation_rooms import ConversationRooms,validate_room_settings,NO_AGENT,PROMPTS
from preferences import Preferences
import model_registry

class AvatarTests(unittest.TestCase):
    def test_generation_cancel_rejects_late_event_and_closes_mouth(self):
        director=AvatarDirector();director.apply({'state':'speaking','mouth':.8})
        self.assertEqual(director.snapshot()['mouth'],.8);director.cancel()
        self.assertFalse(director.apply({'generation':0,'state':'speaking','mouth':1}))
        self.assertEqual(director.snapshot()['mouth'],0)
    def test_expression_decays_and_rate_limit_applies(self):
        clock=Mock(return_value=10.);d=AvatarDirector(clock)
        d.apply({'expression':'happy','duration_ms':500});d.apply({'expression':'sad'})
        self.assertEqual(d.snapshot()['expression'],'happy');clock.return_value=10.6
        self.assertEqual(d.snapshot()['expression'],'neutral')
    def test_bad_levels_and_untrusted_properties_are_rejected(self):
        d=AvatarDirector()
        for value in ({'mouth':float('nan')},{'expression':'execute_shell'},{'state':'admin'},{'command':'calc.exe'},{'duration_ms':90000}):
            with self.assertRaises(ValueError):d.apply(value)
    def test_non_speaking_states_never_have_open_mouth(self):
        d=AvatarDirector()
        for state in ('idle','thinking','listening','sleeping','error','interrupted'):
            d.apply({'state':state,'mouth':1});self.assertEqual(d.snapshot()['mouth'],0)

class CompanionTests(unittest.TestCase):
    def test_feature_default_off_and_configuration_does_not_change_main_models(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Preferences(Path(folder)/'prefs.db');main=Mock();main.preferences=p;main.busy=False;main._translation_pending=False;main.room_frames={};main.room_controls={}
            try:
                self.assertFalse(p.get('companion_enabled'));before=p.get('agent_local_model')
                configure(main,{'enabled':True,'label':'Leva Studio','experimental_models':True})
                self.assertTrue(p.get('companion_enabled'));self.assertEqual(p.get('agent_local_model'),before)
                self.assertEqual(p.get('companion_label'),'Leva Studio');main.local_mic.start.assert_not_called()
            finally:p.close()
    def test_companion_session_is_not_written_to_shared_database(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'rooms.db';rooms=ConversationRooms(p)
            rooms.append('secret','Anda','Private secret fixture');rooms.append('companion_avatar','Anda','Private avatar fixture')
            self.assertEqual(rooms.rows('companion_avatar'),[('Anda','Private avatar fixture')])
            self.assertEqual(rooms.db.execute("SELECT count(*) FROM room_log WHERE room='companion_avatar'").fetchone()[0],0)
            rooms.clear('companion_avatar');self.assertTrue(rooms.rows('secret'));rooms.close()
            rooms=ConversationRooms(p);self.assertEqual(rooms.rows('companion_avatar'),[]);rooms.close()
    def test_companion_prompt_is_local_and_has_no_tool_executor(self):
        from chat_service import run_worker,ChatService
        from hybrid_engine import EngineError
        self.assertIn('room_companion_avatar',PROMPTS)
        for extra in ({'agent':True},{'mode':'hybrid'},{'tool_context':{'shell':'all'}}):
            with patch('chat_service.make_local') as make:
                with self.assertRaises(EngineError):run_worker({'mode':'local','purpose':'room_companion_avatar',**extra})
                make.assert_not_called()
        service=ChatService()
        try:
            with self.assertRaises(EngineError):service.ask('x',purpose='room_companion_avatar',mode='hybrid')
        finally:service.cancel()
    def test_companion_never_auto_starts_microphone(self):
        from gui import LevaWindow
        main=Mock();main.closed=False;main.workspace='companion_avatar';main.companion_mic_consent=False;main.local_mic.active=True
        LevaWindow.ensure_local_mic(main);main.local_mic.stop.assert_called_once();main.local_mic.start.assert_not_called()
    def test_companion_keeps_context_in_its_session_service(self):
        import queue
        from types import SimpleNamespace
        from chat_service import ChatService
        service=ChatService();events=queue.Queue();sent=[]
        def send(payload):sent.append(payload);events.put({'kind':'result','id':payload['id'],'response':'Fixture jawaban.'})
        old=service.session;service.session=SimpleNamespace(active=True,process=None,events=events,send=send,stop=lambda:None)
        try:
            service.ask('Ingat proyek Langit.','local',purpose='room_companion_avatar',keep_warm=True)
            service.ask('Apa proyekku?','local',purpose='room_companion_avatar',keep_warm=True)
            self.assertEqual(len(sent[-1]['messages']),3);self.assertIn('Langit',sent[-1]['messages'][0]['content'])
            for i in range(38):service.ask('Lanjut fixture '+str(i),'local',purpose='room_companion_avatar',keep_warm=True)
            self.assertEqual(len(service.history),80);self.assertIn('Langit',sent[-1]['messages'][0]['content'])
        finally:service.cancel();old.stop()
    def test_stop_is_scoped_to_companion_and_cancels_owned_work(self):
        main=Mock();main.workspace='assistant'
        with self.assertRaises(ValueError):interrupt(main)
        main.cancel_inference.assert_not_called();main.workspace='companion_avatar';main.generation=5;main.avatar_director=AvatarDirector()
        interrupt(main);self.assertEqual(main.generation,6);main.cancel_inference.assert_called_once();main.local_mic.stop.assert_called_once()
        self.assertEqual(presentation(main,'idle',0)['state'],'interrupted')

class RegistryTests(unittest.TestCase):
    def test_application_constructs_trial_adapter_from_registry_resolution(self):
        from chat_service import make_local
        decision={'status':'ready','selected_model':'hauhau_qwen35_4b','provider':'local','tool_policy':'none','experimental':True,'context_tested':8192,'path':'C:/Fixture/model.gguf'}
        with patch('model_registry.resolve',return_value=decision):
            engine=make_local({'local_model':'hauhau_qwen35_4b','purpose':'room_companion_avatar','local_mode':'gpu5070'})
            self.assertEqual(engine.model,Path(decision['path']));self.assertEqual(engine.registry_route['tool_policy'],'none')
            self.assertIsNone(engine.process)
    def test_reused_worker_cannot_upgrade_trial_model_to_agent(self):
        from chat_service import run_worker
        from hybrid_engine import EngineError
        local=Mock()
        with self.assertRaisesRegex(EngineError,'experimental_model_agent_not_approved'):
            run_worker({'local_model':'hauhau_qwen35_4b','mode':'local','agent':True},local=local)
        local.generate.assert_not_called()
    def test_disabling_trials_keeps_saved_selection_visible_but_not_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs=Preferences(Path(folder)/'prefs.db');rooms=ConversationRooms(Path(folder)/'rooms.db')
            try:
                prefs.set_many({'secret_model':'hauhau_qwen35_4b','experimental_models_enabled':False})
                view=rooms.snapshot(prefs)['secret'];self.assertIn(view['model'],view['models'])
                self.assertIn('aktifkan',view['models'][view['model']])
            finally:rooms.close();prefs.close()
    def test_missing_registry_is_not_ready_or_auto_fallback(self):
        with patch('model_registry.records',return_value={}):
            row=model_registry.resolve('secret','hauhau_qwen35_4b',opt_in=True,fallback='qwen4b')
            self.assertEqual(row['status'],'unavailable');self.assertTrue(row['fallback_requires_confirmation']);self.assertEqual(row['tool_policy'],'none')
    def test_opt_in_cannot_grant_tools_and_hash_tampering_is_detected(self):
        key='hauhau_qwen35_4b'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/model_registry.TRIALS[key]['file'];path.write_bytes(b'GGUF')
            expected=hashlib.sha256(b'GGUF').hexdigest();profile={**model_registry.TRIALS[key],'sha256':expected}
            record={key:{'path':str(path),'bytes':4,'sha256':expected,'verified':True,'quant':'Q4_K_M'}}
            with patch.dict(model_registry.TRIALS,{key:profile}),patch('model_registry.records',return_value=record):
                with self.assertRaises(ValueError):model_registry.resolve('assistant',key,opt_in=False)
                result=model_registry.resolve('assistant',key,opt_in=True);self.assertEqual(result['tool_policy'],'none')
                path.write_bytes(b'BAD!')
                with self.assertRaisesRegex(ValueError,'hash_changed'):model_registry.model_path(key,verify=True)
        self.assertTrue(set(model_registry.TRIALS)<=NO_AGENT)

if __name__=='__main__':unittest.main()
