"""Global device rules, missing-card failures and real GUI dispatch payloads."""
import unittest
from unittest.mock import Mock,patch
from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,route_spec
from speech_resources import agent_mode,pipeline_gpu,select_asr_devices
from hybrid_engine import gpu_visibility,verify_gpu_model_buffers,EngineError
import test_speech_pipeline as fixtures
ROWS=fixtures.ROWS

class GPUContractTests(unittest.TestCase):
    def test_explicit_engine_devices_are_independent_and_auto_follows_route(self):
        for label in SINGLE_CHOICES+DUAL_CHOICES:
            spec=route_spec(label)
            if spec['gpu']=='none':
                for engine in ('asr','tts'):
                    with self.assertRaises(ValueError):pipeline_gpu(spec,engine)
                continue
            for preference in ('auto','rtx4050','rtx5070','dual'):
                expected=spec['local_mode'] if preference=='auto' else {'rtx4050':'gpu4050','rtx5070':'gpu5070','dual':'dual'}[preference]
                self.assertEqual(agent_mode(spec,preference),expected)
                self.assertEqual(pipeline_gpu(spec,'asr',preference),spec['gpu'] if preference=='auto' else preference)
            self.assertEqual(pipeline_gpu(spec,'asr'),spec['gpu'])
            self.assertEqual(pipeline_gpu(spec,'tts'),'rtx5070' if spec['gpu']=='dual' else spec['gpu'])

    def test_dual_asr_requires_two_distinct_cards_and_headroom_on_each(self):
        self.assertEqual([r['uuid'] for r in select_asr_devices(ROWS[::-1],'qwen_asr_06b','dual')],['4050-uuid','5070-uuid'])
        for rows in (ROWS[:1],ROWS[1:],[{**r,'free_mib':900} for r in ROWS]):
            with self.assertRaises(ValueError):select_asr_devices(rows,'qwen_asr_06b','dual')
        with self.assertRaises(ValueError):select_asr_devices(ROWS,'qwen_asr_17b','rtx4050')

    def test_cuda_visibility_hides_unselected_card_before_llama_initializes(self):
        rows=[{**r,'uuid':'GPU-'+r['uuid']} for r in ROWS]
        self.assertEqual(gpu_visibility(rows,'gpu4050'),'GPU-4050-uuid')
        self.assertEqual(gpu_visibility(rows,'gpu5070'),'GPU-5070-uuid')
        self.assertEqual(gpu_visibility(rows,'dual'),'GPU-4050-uuid,GPU-5070-uuid')
        with self.assertRaises(EngineError):gpu_visibility(rows[:1],'dual')
        with self.assertRaises(EngineError):gpu_visibility(rows,'typo')

    def test_llm_requires_real_weight_buffers_on_every_selected_card(self):
        log='CUDA0 model buffer size = 621.77 MiB\nCUDA1 model buffer size = 1657.96 MiB'
        self.assertEqual(len(verify_gpu_model_buffers(log,['CUDA0','CUDA1'])),2)
        for bad in ('','CUDA0 model buffer size = 621.77 MiB',log.replace('1657.96','0.00')):
            with self.assertRaises(EngineError):verify_gpu_model_buffers(bad,['CUDA0','CUDA1'])
        with self.assertRaises(EngineError):verify_gpu_model_buffers(log,['CUDA0'])

    def test_mic_receives_explicit_asr_gpu_even_if_toolbar_is_dual(self):
        for label in ('RTX 4050','RTX 5070','Dual GPU'):
            m=fixtures.SpeechPipelineTests().window(label)
            m.closed=False;m.local_mic=Mock(active=False);m.local_mic_failed=False
            prefs={'asr_model':'qwen_asr_06b','always_listen':True,'asr_gpu':'rtx5070',
                   'input_device_name':'Headset','input_hostapi':'MME','asr_language':'id'}
            m.preferences.get.side_effect=prefs.__getitem__
            m.ensure_local_mic()
            self.assertEqual(m.local_mic.start.call_args.args[3],'rtx5070')

    def test_higgs_on_4050_reports_capacity_instead_of_starting_5070(self):
        m=fixtures.SpeechPipelineTests().window('RTX 4050');m.add=Mock()
        with patch('speech_resources.gpu_rows') as query:m.speak_reply('Halo.')
        query.assert_not_called();m.reply_voice.speak.assert_not_called();m.local_mic.stop.assert_not_called()
        self.assertIn('GPU tidak dialihkan',m.add.call_args.args[1])

    def test_tts_5070_payload_ignores_old_auto_preference(self):
        m=fixtures.SpeechPipelineTests().window('RTX 5070')
        with patch('speech_resources.gpu_rows',return_value=ROWS):m.speak_reply('Halo.')
        self.assertEqual(m.reply_voice.service.gpu_preference,'rtx5070')

    def test_route_change_also_releases_voice_preview_and_duplex_models(self):
        m=fixtures.SpeechPipelineTests().window('RTX 5070');m.busy=False
        m.voice_pack_window=Mock();m.duplex_window=Mock();m.save_preference=Mock()
        m.route_changed()
        m.voice_pack_window.stop.assert_called_once();m.duplex_window.stop.assert_called_once()
        m.local_mic.stop.assert_called_once();m.chat.cancel.assert_called_once()

if __name__=='__main__':unittest.main()
