import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from local_audio_core import WakePolicy,Segmenter
from speech_turns import TurnWindow,TurnAssembler,unfinished_utterance
from conversation_frontend import conversation_request,parse_frontend
from pipeline_routing import route_spec


class VoiceSessionTests(unittest.TestCase):
    def test_long_followup_is_authorized_at_start_not_end(self):
        w=WakePolicy(followup_seconds=120);w.accept('hai Leva',now=1)
        self.assertFalse(w.active(now=150))
        self.assertTrue(w.accept('buatkan program web',now=100)['accepted'])

    def test_explicit_arm_45_and_reply_extension_are_distinct(self):
        w=WakePolicy(followup_seconds=120);w.arm(45,now=0)
        self.assertFalse(w.active(now=46));w.arm(now=100)
        self.assertTrue(w.active(now=219));self.assertFalse(w.active(now=221))

    def test_no_commit_until_all_recognition_is_complete(self):
        t=TurnWindow('x');t.voiced(0);t.submitted()
        self.assertIsNone(t.finish(20))
        t.recognized('x','buka Chrome Diska.');self.assertEqual(t.finish(20),'complete')

    def test_connector_waits_for_continuation_and_full_text_stays_together(self):
        t=TurnWindow('x');a=TurnAssembler();t.voiced(0);t.submitted()
        first=a.append('x','Buatkan web bumi 3d, boleh menggunakan',False)
        t.recognized('x',first['text']);self.assertIsNone(t.finish(10))
        t.voiced(13);t.submitted()
        second=a.append('x','model AI apapun dari Hermes agent.',False)
        t.recognized('x',second['text'])
        self.assertIsNone(t.finish(14));self.assertEqual(t.finish(15.1),'complete')
        self.assertEqual(a.append('x','',True)['text'],first['text']+' model AI apapun dari Hermes agent.')

    def test_incomplete_tail_is_never_executed_after_timeout(self):
        t=TurnWindow('x');t.voiced(0);t.submitted();t.recognized('x','buatkan dengan')
        self.assertEqual(t.finish(15),'incomplete')
        self.assertTrue(unfinished_utterance('boleh menggunakan.'))

    def test_manual_dictation_waits_despite_long_silence(self):
        t=TurnWindow('x');t.voiced(0);t.submitted();t.recognized('x','buatkan web')
        self.assertIsNone(t.finish(60,manual=True))
        self.assertEqual(t.finish(60,manual=False),'complete')

    def test_stale_partial_cannot_modify_new_turn(self):
        t=TurnWindow('new');t.submitted();t.recognized('old','old words')
        self.assertEqual(t.pending,1);self.assertEqual(t.text,'')

    def test_manual_flush_includes_pending_short_audio(self):
        s=Segmenter();s.push(b'word',.1)
        self.assertEqual(s.flush(),b'word');self.assertEqual(s.flush(),b'')

    def test_noisy_greeting_keeps_leva_identity_without_loading_model(self):
        model=Mock()
        r=conversation_request(model,'hai apa kabar Arimo',route_spec('Dual GPU'),None,'ja',True)
        model.ask.assert_not_called();self.assertTrue(r['text']);self.assertNotIn('Arimo',r['text']);self.assertEqual(r['kind'],'respond')
        self.assertTrue(r['speech_text'])

    def test_identity_guard_changes_both_text_and_speech(self):
        r=parse_frontend({'response':'{"kind":"respond","text":"Halo! Saya adalah AI, Arimo.","speech_text":"アリモです"}'},'apa kabar Arimo')
        self.assertIn('Leva',r['text']);self.assertNotIn('アリモ',r['speech_text'])

    def test_greeting_with_a_real_task_still_delegates_original_goal(self):
        model=Mock();text='Hai, buatkan web bumi 3d'
        r=conversation_request(model,text,route_spec('Dual GPU'),None,'ja',True)
        self.assertEqual(r['kind'],'delegate');self.assertEqual(r['original_goal'],text)


if __name__=='__main__':unittest.main()
