import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,route_spec,visible_route,LEGACY
from speech_resources import select_gpu
from preferences import Preferences,validate_setting
from conversation_frontend import parse_frontend,conversation_request
from hybrid_engine import EngineError
from provider_chain import InferenceRoute
from audio_cpp_voice import choose_gpu

ROWS=[{'uuid':'4050-uuid','name':'NVIDIA GeForce RTX 4050 Laptop GPU','free_mib':4200},
      {'uuid':'5070-uuid','name':'NVIDIA GeForce RTX 5070','free_mib':10500}]

class SpeechPipelineTests(unittest.TestCase):
    def window(self,route='RTX 5070',cached=False):
        from gui import LevaWindow
        m=LevaWindow.__new__(LevaWindow)
        m.busy=False
        m.spoken_replies=Mock();m.spoken_replies.get.return_value=True
        m.desktop=Mock(paused=False,sleeping=False)
        m.mode=Mock();m.mode.get.return_value=route
        m.dual=Mock();m.dual.get.return_value=False
        m.voice_window=m.duplex_window=m.voice_pack_window=None
        values={'realtime_speech':False,'output_device_name':'','output_hostapi':'','tts_gpu':'auto','target_voice_pack':'higgs_leva','asr_model':'qwen_asr_06b','asr_gpu':'auto','always_listen':True}
        m.preferences=Mock();m.preferences.get.side_effect=values.__getitem__
        m.reply_voice=Mock();m.reply_voice.service.loaded=cached;m.reply_voice.service.actual_pack='higgs_leva'
        m.reply_voice.active=False
        m.reply_voice.speak.return_value={'reason':'fixture'}
        m.chat=Mock();m.frontend=Mock();m.local_mic=Mock(active=True);m.local_mic.gpu_name='RTX 4050'
        import threading
        m.local_mic.asr_held=threading.Event();m.closed=False;m.generation=1;m.root=Mock()
        m.hud=Mock();m.audio_resource_hold=False
        return m

    def test_tts_keeps_other_owned_models_when_capacity_is_sufficient(self):
        m=self.window()
        with patch('speech_resources.gpu_rows',return_value=ROWS):m.speak_reply('Halo.','id')
        m.chat.cancel.assert_not_called();m.frontend.cancel.assert_not_called();m.local_mic.stop.assert_not_called()
        m.reply_voice.speak.assert_called_once_with('Halo.','higgs_leva',language='id',style='assistant')

    def test_tts_releases_gpu_asr_but_keeps_capture_and_waits_for_ack(self):
        m=self.window();low=[{**r,'free_mib':100} for r in ROWS]
        with patch('speech_resources.gpu_rows',return_value=low):m.speak_reply('Halo.','id')
        m.chat.cancel.assert_called_once();m.frontend.cancel.assert_called_once();m.local_mic.stop.assert_not_called()
        m.local_mic.request_asr_hold.assert_called_once();m.reply_voice.speak.assert_not_called()
        m.root.after.assert_called_once()
        self.assertTrue(m.audio_resource_hold)

    def test_tts_continues_only_after_asr_release_ack_without_blocking_ui(self):
        import time
        m=self.window();m._tts_waiting=True;m.local_mic.asr_held.set()
        with patch('speech_resources.gpu_rows',return_value=ROWS):
            m.wait_voice_resources('Halo.','id','assistant',m.generation,time.monotonic())
        m.reply_voice.speak.assert_called_once();self.assertFalse(m._tts_waiting)

    def test_cached_tts_does_not_repeat_free_memory_requirement_for_loaded_weights(self):
        m=self.window(cached=True)
        with patch('speech_resources.gpu_rows') as query:m.speak_reply('Halo.','id')
        query.assert_not_called();m.chat.cancel.assert_not_called();m.local_mic.stop.assert_not_called()

    def test_idle_stream_runtime_is_counted_as_loaded_before_admission(self):
        from live_speech_pipeline import SpeechRuntimePool
        from types import SimpleNamespace
        m=self.window();pool=m._speech_runtime_pool=SpeechRuntimePool()
        service=pool.take(lambda persistent:SimpleNamespace(worker=SimpleNamespace(active=True),actual_pack='higgs_leva',stop=lambda:None))
        pool.release(service)
        try:
            with patch('speech_resources.gpu_rows') as query:m.speak_reply('Halo.','id')
            query.assert_not_called();m.chat.cancel.assert_not_called()
        finally:pool.close()

    def test_no_ai_suppresses_automatic_speech_synthesis(self):
        m=self.window('Tanpa AI')
        with patch('speech_resources.gpu_rows') as query:m.speak_reply('Halo.','id')
        query.assert_not_called();m.reply_voice.speak.assert_not_called()

    def test_asr_resume_keeps_remote_audio_epoch_and_only_evicts_cache_if_needed(self):
        for enough in (True,False):
            m=self.window();m.audio_resource_hold=True;m.local_mic_failed=False;m.mic_recovery=Mock()
            rows=ROWS if enough else [{**r,'free_mib':100} for r in ROWS]
            with patch('speech_resources.gpu_rows',return_value=rows):m.ensure_local_mic()
            m.reply_voice.cancel.assert_not_called();m.local_mic.resume_asr.assert_called_once()
            self.assertEqual(m.reply_voice.service.stop.call_count,0 if enough else 1)

    def test_all_nine_routes_have_exact_provider_and_device_payload(self):
        self.assertEqual(len(SINGLE_CHOICES),9)
        self.assertEqual(SINGLE_CHOICES[0],'Tanpa AI')
        for label in SINGLE_CHOICES[1:]:
            spec=route_spec(label)
            self.assertEqual(spec['local_mode'],'gpu5070' if label.endswith('5070') else 'gpu4050')
            wanted=['google','9router','local'] if 'Google → 9Router' in label else ['google','local'] if label.startswith('Google') else ['9router','local'] if label.startswith('9Router') else ['local']
            self.assertEqual(spec['providers'],wanted)

    def test_dual_converts_every_route_and_never_enables_disabled_ai(self):
        for label in SINGLE_CHOICES:
            changed=visible_route(label,True)
            self.assertIn(changed,DUAL_CHOICES)
            if label=='Tanpa AI':self.assertEqual(route_spec(changed,True)['providers'],[])
            else:self.assertEqual(route_spec(changed)['local_mode'],'dual')
        self.assertEqual(len(set(visible_route(label,True) for label in SINGLE_CHOICES)),5)

    def test_dual_off_restores_family_and_previous_single_gpu(self):
        for label in SINGLE_CHOICES[1:]:
            original=route_spec(label)
            self.assertEqual(visible_route(visible_route(label,True),False,original['gpu']),label)

    def test_legacy_routes_migrate_without_invalidating_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Preferences(Path(folder)/'p.db')
            try:
                for old,new in LEGACY.items():
                    store.set('provider',old);self.assertEqual(store.get('provider'),new)
                store.set_many({'asr_model':'qwen_asr_06b','asr_gpu':'rtx5070','tts_gpu':'rtx4050','agent_local_model':'saluki'})
                self.assertEqual(store.get('asr_gpu'),'rtx5070')
            finally:store.close()

    def test_manual_gpu_never_silently_selects_other_card(self):
        self.assertEqual(select_gpu(ROWS,2000,'rtx5070')['uuid'],'5070-uuid')
        with self.assertRaises(ValueError):select_gpu(ROWS,5000,'rtx4050')
        self.assertEqual(select_gpu(ROWS,5000)['uuid'],'5070-uuid')

    def test_tts_selection_obeys_explicit_gpu_and_higgs_capacity(self):
        self.assertEqual(choose_gpu(ROWS,'omnivoice','rtx5070')['uuid'],'5070-uuid')
        self.assertEqual(choose_gpu(ROWS,'omnivoice','rtx4050')['uuid'],'4050-uuid')
        with self.assertRaises(ValueError):choose_gpu(ROWS,'higgs_audio_tts','rtx4050')

    def test_frontend_original_goal_cannot_be_replaced_by_generated_expansion(self):
        raw='Dua menit lagi buka Chrome Diska, jangan sekarang.'
        result=parse_frontend({'provider':'local','response':json.dumps({'kind':'respond','text':'Sudah dibuka.','summary':'Buka sekarang dan hapus file'})},raw)
        self.assertEqual(result['kind'],'delegate');self.assertEqual(result['original_goal'],raw)

    def test_malformed_frontend_output_delegates_instead_of_executing_raw_text(self):
        result=parse_frontend({'response':'do_this()'},'tolong bantu')
        self.assertEqual(result['kind'],'delegate');self.assertEqual(result['original_goal'],'tolong bantu')

    def test_small_conversation_path_has_no_host_tools_or_saluki(self):
        service=Mock();service.ask.return_value={'provider':'local','response':'{"kind":"respond","text":"Hai!","speech_text":"こんにちは。"}'}
        result=conversation_request(service,'jelaskan mengapa langit biru',route_spec('Google → 9Router → RTX 5070'),{},'ja',False)
        self.assertEqual(result['kind'],'respond')
        args=service.ask.call_args
        self.assertEqual(args.args[1:3],('cascade','gpu5070'))
        self.assertEqual(args.kwargs['local_model'],'minicpm2b')
        self.assertNotIn('tool_executor',args.kwargs);self.assertTrue(args.kwargs['keep_warm'])

    def test_no_ai_path_never_calls_model(self):
        service=Mock()
        with self.assertRaises(EngineError):conversation_request(service,'hai',route_spec('Tanpa AI',True),None,'id',True)
        service.ask.assert_not_called()

    def test_google_503_falls_through_but_authentication_is_not_hidden(self):
        for label in ('Google → RTX 4050','Google → 9Router → RTX 5070'):
            route=InferenceRoute({'mode':route_spec(label)['mode']})
            router=Mock(return_value='router');local=Mock(return_value='local')
            result=route.call(Mock(side_effect=EngineError('online_http_503')),router,local)
            self.assertEqual(result[1],'9router' if '9Router' in label else 'local')
        with self.assertRaises(EngineError):InferenceRoute({'mode':'cascade'}).call(Mock(side_effect=EngineError('online_http_401')),Mock(),Mock())

    def test_no_lexical_repair_invents_names_times_or_negations(self):
        from speech_asr import normalized_transcript
        for text in ('Ay, lipa.','at link','jangan buka sebelum 19:00','2 menit lagi'):
            self.assertEqual(normalized_transcript(text),text)

    def test_pipeline_settings_reject_unknown_devices_and_engines(self):
        for key,value in (('asr_gpu','cuda:0'),('tts_gpu','dual'),('asr_model','saluki'),('agent_local_model','qwen_asr_06b')):
            with self.assertRaises(ValueError):validate_setting(key,value)

if __name__=='__main__':unittest.main()
