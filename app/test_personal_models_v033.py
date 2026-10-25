import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

class PersonalModelTests(unittest.TestCase):
    def test_new_profiles_share_choices_across_interfaces(self):
        from personal_models import PROFILES
        from conversation_rooms import MODELS,model_choices
        from speech_resources import AGENT_CHOICES
        self.assertEqual(AGENT_CHOICES,{k:v.removesuffix(' · belum tersedia') for k,v in model_choices('assistant').items()})
        for room in ('assistant','chat','secret'):
            self.assertTrue(set(PROFILES)<=set(model_choices(room)))
            self.assertTrue(set(PROFILES)<=set(MODELS))

    def test_preferences_roundtrip_for_all_new_models_without_changing_voice(self):
        from preferences import Preferences
        from personal_models import PROFILES
        with tempfile.TemporaryDirectory() as tmp:
            p=Preferences(Path(tmp)/'prefs.sqlite3');voice=p.get('speech_language');asr=p.get('asr_gpu')
            for key in PROFILES:
                for role in ('agent_local_model','chat_model','secret_model'):
                    p.set(role,key);self.assertEqual(p.get(role),key)
            self.assertEqual(p.get('speech_language'),voice);self.assertEqual(p.get('asr_gpu'),asr);p.close()
            p=Preferences(Path(tmp)/'prefs.sqlite3');self.assertEqual(p.get('secret_model'),next(reversed(PROFILES)));p.close()

    def test_y_location_is_used_when_d_file_is_absent(self):
        import personal_models as m
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'D';y=Path(tmp)/'Y';profile=m.PROFILES['stheno8b'];target=y/profile['folder']/profile['file'];target.parent.mkdir(parents=True);target.write_bytes(b'GGUF')
            with patch.object(m,'MODEL_ROOT',d),patch.object(m,'ALTERNATE',y):
                self.assertEqual(m.model_path('stheno8b'),target)
                primary=d/profile['folder']/profile['file'];primary.parent.mkdir(parents=True);primary.write_bytes(b'GGUF')
                self.assertEqual(m.model_path('stheno8b'),primary)

    def test_worker_uses_real_selected_profile_and_gpu_with_non_thinking(self):
        from personal_models import PROFILES,model_path
        from chat_service import make_local
        for key in PROFILES:
            for gpu in ('gpu4050','gpu5070','dual'):
                with patch('chat_service.LocalEngine') as engine:
                    make_local({'local_model':key,'local_mode':gpu,'agent':True})
                    args,kw=engine.call_args
                    self.assertEqual(args[1],model_path(key));self.assertEqual(kw['mode'],gpu)
                    self.assertEqual(kw['thinking_budget'],0);self.assertEqual(kw['context_size'],8192)

    def test_room_speech_models_do_not_receive_agent_context(self):
        from chat_service import run_worker
        from hybrid_engine import EngineError
        from personal_models import PROFILES
        for key in PROFILES:
            with patch('chat_service.make_local') as make:
                with self.assertRaisesRegex(EngineError,'conversation_room_tools_forbidden'):
                    run_worker({'local_model':key,'purpose':'room_secret','mode':'local','tool_context':{'apps':['x']}})
                make.assert_not_called()

    def test_qwen_non_thinking_sampling_is_not_overwritten_by_generic_room_policy(self):
        from chat_service import run_worker
        from personal_models import sampling_for
        engine=Mock();engine.generate.return_value='Aku mendengarkan.'
        request={'local_model':'qwen3_8b','purpose':'room_secret','mode':'local','messages':[{'role':'user','content':'Aku lelah'}]}
        result=run_worker(request,engine,False)
        self.assertEqual(engine.sampling,sampling_for('qwen3_8b','room_secret'))
        self.assertEqual(result['response'],'Aku mendengarkan.')
        engine.close.assert_not_called()

    def test_external_speech_worker_bundle_includes_shared_profile_module(self):
        text=Path(__file__).with_name('build.ps1').read_text('utf8')
        self.assertIn('$taskRoot/app/personal_models.py;assistant_runtime',text)
        import personal_models
        self.assertNotIn('conversation_rooms',Path(personal_models.__file__).read_text('utf8'))

    def test_invalid_model_settings_fail_as_validation_errors(self):
        from preferences import validate_setting
        for field in ('agent_local_model','chat_model','secret_model'):
            for value in (None,[],{},'remote-unregistered-model'):
                with self.assertRaises(ValueError):validate_setting(field,value)

    def test_text_only_model_in_assistant_keeps_correct_mode_and_does_not_receive_tools(self):
        from conversation_rooms import ConversationRooms
        with tempfile.TemporaryDirectory() as tmp:
            rooms=ConversationRooms(Path(tmp)/'rooms.db');service=Mock();service.history=[];service.ask.return_value={'response':'Pilih model agent yang mendukung alat.'};rooms.services['assistant']=service
            rooms.answer('assistant','Buka Chrome','stheno8b','gpu5070')
            self.assertEqual(service.ask.call_args.kwargs['purpose'],'room_assistant_text')
            self.assertNotIn('tool_executor',service.ask.call_args.kwargs);rooms.close()

    def test_worker_rejects_unproven_agent_models_before_inference(self):
        import io,json
        from chat_service import session_worker
        from personal_models import NO_AGENT_MODELS
        for key in NO_AGENT_MODELS:
            events=[];local=Mock()
            payload={'id':1,'messages':[{'role':'user','content':'buka Chrome'}],'mode':'local','agent':True,'local_model':key,'keep_warm':False}
            with patch('sys.stdin',io.StringIO(json.dumps(payload)+'\n')),patch('chat_service.make_local',return_value=local),patch('agent_runtime.run_agent') as run:
                session_worker(events.append,idle_seconds=1)
            self.assertTrue(any(row.get('code')=='conversation_model_has_no_agent_tools' for row in events));run.assert_not_called();local.start.assert_not_called()

if __name__=='__main__':unittest.main()
