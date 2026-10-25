import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import sys
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]

from speech_style import SpeechStylePolicy,explicit_style,higgs_text
from task_journal import TaskJournal
from preferences import Preferences
from audio_cpp_voice import choose_gpu
from assistant_tools import validate_call,AssistantTools

class AdaptiveVoiceTaskTests(unittest.TestCase):
    def test_style_is_contextual_not_a_reply_length_threshold(self):
        policy=SpeechStylePolicy()
        self.assertEqual(policy.choose('Buka Chrome')['style'],'assistant')
        self.assertEqual(policy.choose('Aku sedang sedih dan ingin curhat. '*80)['style'],'personal')
        self.assertEqual(policy.choose('Iya, lanjut')['style'],'personal')
        self.assertEqual(policy.choose('Sekarang cari artikel GPU',hint='personal')['style'],'assistant')
        self.assertEqual(policy.choose('Boleh bantu?',hint='personal',receipts=[{'name':'computer_action'}])['style'],'assistant')

    def test_user_controls_style_and_model_cannot_inject_tags(self):
        policy=SpeechStylePolicy()
        self.assertEqual(policy.choose('jangan pakai gaya personal',hint='personal')['style'],'assistant')
        self.assertEqual(policy.choose('Buka Chrome',mode='personal')['style'],'personal')
        self.assertEqual(explicit_style('ubah gaya suara ke otomatis'),'auto')
        self.assertIsNone(explicit_style('jangan ubah gaya personal'))
        self.assertIsNone(explicit_style('Apakah gaya personal cocok?'))
        self.assertIsNone(explicit_style('Terjemahkan: gunakan gaya personal'))
        self.assertEqual(higgs_text('<|style:shouting|>Halo','assistant'),'<|emotion:contentment|>Halo')
        validate_call('respond',{'text':'Hai','speech_text':'Hai','voice_style':'personal'})
        with self.assertRaises(ValueError):validate_call('respond',{'text':'Hai','speech_text':'Hai','voice_style':'arbitrary'})

    def test_style_and_engine_selection_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.db'
            prefs=Preferences(path);prefs.set_many({'speech_style':'personal','target_voice_pack':'higgs_native'});prefs.close()
            prefs=Preferences(path)
            self.assertEqual(prefs.get('speech_style'),'personal');self.assertEqual(prefs.get('target_voice_pack'),'higgs_native');prefs.close()

    def test_window_verifier_uses_uia_states_and_waits_for_transition(self):
        import feature_worker
        window=Mock();rect=window.rectangle.return_value
        rect.left=50;rect.top=60;rect.width.return_value=800;rect.height.return_value=600
        window.get_show_state.side_effect=[0,1]
        with patch('feature_worker.target',return_value=window),patch('feature_worker.time.sleep'):
            result=feature_worker.manage_window({'action':'maximize','window':'123','bounds':''})
        self.assertEqual(result['status'],'done');self.assertEqual(window.get_show_state.call_count,2)
        window.get_show_state.side_effect=None;window.get_show_state.return_value=0
        with patch('feature_worker.target',return_value=window):
            self.assertTrue(feature_worker.manage_window({'action':'restore','window':'123','bounds':''})['task_verified'])
        window.get_show_state.return_value=1
        with patch('feature_worker.target',return_value=window),patch('feature_worker.time.monotonic',side_effect=[0,2]):
            self.assertFalse(feature_worker.manage_window({'action':'restore','window':'123','bounds':''})['task_verified'])

    def test_gpu_scheduler_preserves_headroom_and_does_not_pool_vram(self):
        rows=[{'name':'RTX 4050','free_mib':5900,'uuid':'a'},{'name':'RTX 5070','free_mib':9500,'uuid':'b'}]
        self.assertEqual(choose_gpu(rows,'higgs_audio_tts')['uuid'],'b')
        self.assertEqual(choose_gpu(rows,'omnivoice')['uuid'],'a')
        rows[1]['free_mib']=2500
        with self.assertRaisesRegex(ValueError,'headroom'):choose_gpu(rows,'higgs_audio_tts')

    def test_interrupted_dispatch_survives_restart_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tasks.db';journal=TaskJournal(path)
            task=journal.begin('Buka editor dan ketik UJI')
            journal.intent(task,1,'computer_action',{'action':'type','window':'123','text':'UJI'})
            reopened=TaskJournal(path);state=reopened.get(task)
            self.assertEqual(state['steps'][0]['status'],'dispatching')
            self.assertTrue(state['requires_fresh_observation']);self.assertFalse(state['automatic_replay'])
            reopened.receipt(task,1,{'status':'dispatched','reply':'Input dikirim','content':'DO NOT STORE FULL DOCUMENT'})
            self.assertNotIn('DO NOT STORE FULL DOCUMENT',json.dumps(reopened.get(task)))
            reopened.finish(task,'incomplete');self.assertEqual(reopened.recent()[0]['status'],'incomplete')

    def test_resume_is_explicit_and_following_request_clears_resumed_goal(self):
        desktop=Mock();desktop.preferences=None;desktop.controller.active_profile_id=None
        with tempfile.TemporaryDirectory() as folder:
            journal=TaskJournal(Path(folder)/'tasks.db');ident=journal.begin('Ketik UJI')
            tools=AssistantTools(desktop)
            with patch('task_journal.TaskJournal',return_value=journal):
                self.assertEqual(tools.execute('resume_task',{'task_id':ident},'hai')['status'],'needs_input')
                self.assertEqual(tools.execute('resume_task',{'task_id':ident},'lanjut tugas '+ident)['status'],'done')
                self.assertEqual(tools._resume_goal,'Ketik UJI')
            tools.context('permintaan baru');self.assertEqual(tools._resume_goal,'')

if __name__=='__main__':unittest.main()
