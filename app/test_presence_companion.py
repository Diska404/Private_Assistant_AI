import queue
import random
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import urllib.error
import test_web_integration as fixtures
from leva_persona import PersonaDelivery,GREETINGS,simple_greeting
from companion_lines import GREETINGS_BY_ROOM,IDLE_BY_ROOM
from preferences import Preferences,DEFAULTS
from presence_companion import CompanionPolicy,observed_apps,available,tick,deliver,validate_settings

class CompanionTests(unittest.TestCase):
    def test_mode_banks_and_bilingual_variety(self):
        d=PersonaDelivery(random.Random(15))
        for room in ('assistant','chat','secret'):
            self.assertEqual(len(GREETINGS)+len(GREETINGS_BY_ROOM[room]),26)
            rows=[d.greeting(room=room) for _ in range(80)]
            self.assertTrue(all(r['room']==room and r['text'] and r['speech_text'] for r in rows))
            self.assertGreater(len({r['text'] for r in rows}),40)
            self.assertTrue(all(a['text']!=b['text'] for a,b in zip(rows,rows[1:])))
    def test_calm_greetings_and_idle_exclude_playful_markers(self):
        d=PersonaDelivery(random.Random(5))
        for room in GREETINGS_BY_ROOM:
            for _ in range(60):
                for r in (d.greeting(room=room,playful=False),d.standby(room=room,playful=False)):
                    self.assertNotIn('💗',r['text']);self.assertNotIn('desu',r['text']);self.assertNotIn('berduaan',r['text'])
    def test_only_actual_executable_identity_marks_app_observed(self):
        result={'status':'done','windows':[{'pid':11,'title':'Discord tutorial — Google Chrome'},{'pid':12,'title':'Notes'}]}
        apps=observed_apps(result,lambda pid:{11:'chrome.exe',12:'notepad.exe'}[pid])
        self.assertEqual(apps,{'chrome':True})
        self.assertEqual(observed_apps({'status':'failed','windows':result['windows']}),{})
        self.assertEqual(observed_apps(result,lambda pid:(_ for _ in ()).throw(OSError())),{})
    def test_app_claim_requires_evidence_and_stays_out_of_chat_secret(self):
        d=PersonaDelivery(random.Random(2))
        for _ in range(30):
            r=d.standby('assistant',{'discord':True});self.assertTrue(r['evidence']['discord_window_observed']);self.assertIn('Discord',r['text'])
            self.assertEqual(d.standby('assistant',{})['evidence'],{})
            for room in ('chat','secret'):
                row=d.standby(room,{'discord':True});self.assertEqual(row['evidence'],{});self.assertNotIn('Discord',row['text'])
    def test_idle_limits_cancellation_suspend_and_hour_budget(self):
        now=[0.];p=CompanionPolicy(clock=lambda:now[0],rng=random.Random(1));p.touch()
        self.assertIsNone(p.reserve(True));now[0]=200
        token=p.reserve(True);self.assertIsNotNone(token);self.assertIsNone(p.reserve(True))
        p.touch();self.assertFalse(p.commit(token));now[0]+=200
        for episode in range(2):
            for _ in range(2):
                token=p.reserve(True);self.assertIsNotNone(token);self.assertTrue(p.commit(token));now[0]+=601
                # Deterministic clock advances beyond randomized follow-up delay.
                p.next_at=min(p.next_at,now[0])
            self.assertIsNone(p.reserve(True));p.touch();now[0]+=200
        self.assertIsNone(p.reserve(True))
        now[0]+=3601;self.assertIsNotNone(p.reserve(True));p.suspend();self.assertIsNone(p.reserve(True))
    def main(self):
        return SimpleNamespace(preferences=SimpleNamespace(get=lambda k:DEFAULTS[k]),closed=False,busy=False,
          desktop=SimpleNamespace(paused=False,sleeping=False),reply_voice=Mock(active=False),
          entry=SimpleNamespace(get=lambda:''),root=SimpleNamespace(state=lambda:'normal',focus_displayof=lambda:object()),
          local_mic=SimpleNamespace(active=False,telemetry=SimpleNamespace(snapshot=lambda active:{'rms_db':-80,'text':''})),
          spoken_replies=SimpleNamespace(get=lambda:False),workspace='secret',generation=0,events=queue.Queue(),add=Mock())
    def test_busy_draft_voice_sleep_and_background_suppress_idle(self):
        m=self.main();self.assertTrue(available(m))
        for key in ('busy','_translation_pending','dictation_active','_image_gpu_active'):
            setattr(m,key,True);self.assertFalse(available(m));setattr(m,key,False)
        m.entry.get=lambda:'draft';self.assertFalse(available(m));m.entry.get=lambda:''
        m.desktop.paused=True;self.assertFalse(available(m));m.desktop.paused=False
        m.root.state=lambda:'iconic';self.assertFalse(available(m))
        from presence_companion import policy,touch
        policy(m).suspend();touch(m);self.assertTrue(policy(m).suspended)
        touch(m,'hai leva');self.assertFalse(policy(m).suspended)
    def test_secret_idle_is_text_only_without_tools_or_models(self):
        m=self.main();now=[0.];m.companion_policy=CompanionPolicy(clock=lambda:now[0]);now[0]=200
        with patch('feature_bridge.FeatureBridge') as bridge,patch('chat_service.ChatService') as model:
            tick(m);generation,event=m.events.get(timeout=2);self.assertEqual(generation,0)
            self.assertTrue(deliver(m,event['_companion']));bridge.assert_not_called();model.assert_not_called()
            self.assertEqual(m.add.call_args.args[0],'Leva · Sapaan');m.reply_voice.speak.assert_not_called()
    def test_settings_persist_and_validation_rejects_expanded_scope(self):
        v={'companion_idle':False,'companion_playful':False,'companion_idle_delay':'300'}
        with tempfile.TemporaryDirectory() as temp:
            p=Preferences(Path(temp)/'p.db');p.set_many(v);p.close();p=Preferences(Path(temp)/'p.db')
            self.assertEqual({k:p.get(k) for k in v},v);p.close()
        for bad in ({**v,'execute':True},{**v,'companion_idle':'true'},{**v,'companion_idle_delay':'1'}):
            with self.assertRaises(ValueError):validate_settings(bad)
    def test_greeting_does_not_capture_a_command_or_attachment(self):
        self.assertTrue(simple_greeting('Haiii Leva~'))
        self.assertFalse(simple_greeting('Hai Leva, buka Discord'))
        from conversation_rooms import ConversationRooms
        with tempfile.TemporaryDirectory() as temp:
            r=ConversationRooms(Path(temp)/'rooms.db');s=Mock(history=[]);r.services['chat']=s
            result=r.answer('chat','Hai Leva','auto','gpu5070');s.ask.assert_not_called()
            self.assertEqual(result['routing']['method'],'host_greeting');self.assertEqual(s.history[-1]['content'],result['response']);r.close()

class CompanionHTTPTests(unittest.TestCase):
    setUp=fixtures.BridgeTests.setUp
    request=fixtures.BridgeTests.request
    def test_settings_require_auth_and_cannot_inject_tools(self):
        value={'companion_idle':False,'companion_playful':True,'companion_idle_delay':'120'}
        body={'id':'persona-test-123','kind':'persona_settings','value':value}
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/commands','POST',body,authenticated=False)
        with self.request('/api/commands','POST',body) as response:self.assertEqual(response.status,202)
        self.assertEqual(self.bridge.controls.get_nowait()['value'],value)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/commands','POST',{**body,'id':'persona-test-456','value':{**value,'terminal':'x'}})
    def test_draft_presence_has_no_text_and_is_ephemeral(self):
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/interaction','POST',{'draft':True},authenticated=False)
        with self.request('/api/interaction','POST',{'draft':True}) as response:self.assertEqual(response.status,200)
        self.assertGreater(self.bridge.ui_draft_until,self.bridge.ui_interaction_seen)
        self.assertEqual(self.bridge.commands.qsize(),0);self.assertEqual(self.bridge.store.recent(),[])
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/interaction','POST',{'draft':True,'text':'private draft'})

if __name__=='__main__':unittest.main()
