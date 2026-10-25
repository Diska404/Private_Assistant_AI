from datetime import datetime,timezone
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch

from conversation_memory import ConversationMemory,redact
from local_audio_core import WakePolicy,Segmenter,self_transcript
from autonomy_services import PluginManager,ProactiveService
from assistant_tools import selected_skills,AssistantTools
from web_tools import public_url
from feature_bridge import FeatureBridge
import feature_worker

class AutonomyTests(unittest.TestCase):
    def test_automatic_memory_survives_restart_and_keeps_user_assistant_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'memory.sqlite3';store=ConversationMemory(path)
            store.record('Saya memakai laptop Acer.','Kamu memakai laptop Acer.',[{'name':'get_time','result':{'status':'done'}}])
            reopened=ConversationMemory(path)
            self.assertEqual(reopened.recent()[0]['role'],'user')
            self.assertEqual(reopened.recall('Acer')[0]['user'],'Saya memakai laptop Acer.')
            self.assertIn('Pengguna:',reopened.overview()[0]['summary']);self.assertIn('Leva:',reopened.overview()[0]['summary'])
            reopened.clear();self.assertEqual(reopened.recent(),[]);self.assertEqual(reopened.recall('Acer'),[])

    def test_memory_search_escapes_fts_operators_and_redacts_common_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationMemory(Path(folder)/'db')
            store.record('API key: should_not_be_stored','Saya catat.')
            self.assertNotIn('should_not_be_stored',str(store.recent()))
            self.assertEqual(store.recall('" OR * NEAR()'),[])
        self.assertNotIn('AIza'+'a'*35,redact('Token '+ 'AIza'+'a'*35))

    def test_agenda_requires_timezone_and_watch_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationMemory(Path(folder)/'db')
            with self.assertRaises(ValueError):store.add_agenda('Meeting','2026-10-20T09:00:00')
            row=store.add_agenda('Meeting','2026-10-20T09:00:00+07:00');self.assertEqual(store.agenda()[0]['id'],row['id'])
            store.watch('Acer eGPU');store.watch('Acer eGPU');self.assertEqual(len(store.watches()),1)

    def test_wake_word_followups_and_timeout(self):
        wake=WakePolicy()
        self.assertFalse(wake.accept('buka Chrome',0)['accepted'])
        self.assertEqual(wake.accept('Leva, buka Chrome',1)['command'],'buka Chrome')
        self.assertTrue(wake.accept('profil Diska',10)['accepted'])
        self.assertFalse(wake.accept('obrolan lain',60)['accepted'])
        self.assertFalse(wake.accept('lewat jalan',70)['accepted'])

    def test_endpoint_requires_speech_and_barge_in_rejects_echo(self):
        segmenter=Segmenter();frames=[];interrupted=False
        for index in range(15):
            complete,barge,_=segmenter.push(b'voice',.05,speaking=True,awake=True);interrupted|=barge
        for index in range(28):
            complete,_,_=segmenter.push(b'quiet',.001)
            if complete:frames.append(complete)
        self.assertTrue(interrupted);self.assertEqual(len(frames),1)
        for index in range(20):self.assertFalse(segmenter.push(b'echo',.1,echo=True,speaking=True,awake=True)[1])

    def test_own_speech_is_not_a_new_user_command(self):
        self.assertTrue(self_transcript('Steam sudah terbuka','Steam sudah terbuka. Mau lanjut?',1))
        self.assertFalse(self_transcript('Leva jeda sistemmu','Steam sudah terbuka.',1))
        self.assertFalse(self_transcript('Steam sudah terbuka','Steam sudah terbuka',5))

    def test_declarative_plugin_rejects_executable_or_unknown_skill(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'good.json').write_text(json.dumps({'name':'cari-artikel','description':'Cari artikel','skill':'web_search','args':{'query':'{input}'}}))
            (root/'bad.json').write_text(json.dumps({'name':'bad','skill':'shell','args':{'command':'anything'}}))
            manager=PluginManager(root)
            self.assertEqual(manager.resolve('cari-artikel','Acer eGPU'),('web_search',{'query':'Acer eGPU'}))
            self.assertEqual(len(manager.errors),1)
            with self.assertRaises(ValueError):manager.resolve('bad','x')

    def test_tools_are_loaded_on_demand_without_a_large_greeting_schema(self):
        greeting={s.name for s in selected_skills('hai')};self.assertNotIn('computer_action',greeting)
        self.assertIn('web_search',{s.name for s in selected_skills('cari artikel Acer eGPU')})
        self.assertIn('computer_action',{s.name for s in selected_skills('klik tombol pada layar')})
        self.assertIn('web_search',{s.name for s in selected_skills('hai',{'web'})})

    def test_private_urls_cannot_be_read_as_public_internet(self):
        for url in ('file:///C:/data','http://localhost/','http://127.0.0.1/','http://10.0.0.1/','https://user:pass@example.com','https://example.com:4433/'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):public_url(url)

    def test_public_url_resolution_is_checked_before_read(self):
        with patch('web_tools.socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]):self.assertEqual(public_url('https://example.com/'),'https://example.com/')
        with patch('web_tools.socket.getaddrinfo',return_value=[(2,1,6,'',('192.168.1.1',443))]):
            with self.assertRaises(ValueError):public_url('https://example.com/')

    def test_unrequested_camera_or_unobserved_url_does_not_reach_runtime(self):
        desktop=Mock();desktop.preferences=None;desktop.controller.active_profile_id=None
        tools=AssistantTools(desktop);tools._bridge=Mock()
        self.assertEqual(tools.execute('webcam_snapshot',{'device':'0'},'hai')['status'],'needs_input')
        self.assertEqual(tools.execute('read_webpage',{'url':'https://example.com/'},'cari Acer')['status'],'needs_input');tools._bridge.run.assert_not_called()

    def test_cancellation_stops_feature_runtime_before_waiting_for_result(self):
        bridge=FeatureBridge();bridge.worker=Mock();bridge.worker.active=True;bridge.worker.events=queue.Queue()
        result=bridge.run('web_search',{'query':'fixture'},authorized=Mock(side_effect=[True,False]))
        self.assertEqual(result['status'],'cancelled');bridge.worker.stop.assert_called_once()

    def test_trailing_constraint_does_not_cancel_requested_typing(self):
        desktop=Mock();desktop.preferences=None;desktop.controller.active_profile_id=None
        tools=AssistantTools(desktop);tools.observed_windows={'7'};tools._bridge=Mock();tools._bridge.run.return_value={'status':'dispatched'}
        args={'action':'type','window':'7','element':'fixture:1','text':'UJI'}
        self.assertEqual(tools.execute('computer_action',args,'Ketik UJI di tab kosong. Jangan pindah tab lain.')['status'],'dispatched')
        tools._bridge.run.reset_mock()
        for prompt in ('Jangan ketik UJI','Terjemahkan: ketik UJI','Lihat saja jendelanya'):
            self.assertEqual(tools.execute('computer_action',args,prompt)['status'],'needs_input')
        tools._bridge.run.assert_not_called()

    def test_unobserved_window_and_changed_literal_are_not_dispatched(self):
        desktop=Mock();desktop.preferences=None;desktop.controller.active_profile_id=None
        tools=AssistantTools(desktop);tools._bridge=Mock()
        args={'action':'type','window':'7','element':'fixture:1','text':'UJI EEVA 012'}
        result=tools.execute('computer_action',args,'Ketik persis UJI LEVA 012 lalu periksa')
        self.assertEqual(result['code'],'window_not_observed')
        tools.observed_windows={'7'}
        self.assertEqual(tools.execute('computer_action',args,'Ketik persis UJI LEVA 012 lalu periksa')['code'],'literal_text_mismatch')
        tools._bridge.run.assert_not_called()

    def test_replacement_requires_explicit_replace_request(self):
        desktop=Mock();desktop.preferences=None;desktop.controller.active_profile_id=None
        tools=AssistantTools(desktop);tools.observed_windows={'7'};tools._bridge=Mock();tools._bridge.run.return_value={'status':'dispatched'}
        args={'action':'replace_text','window':'7','element':'fixture:1','text':'baru'}
        self.assertEqual(tools.execute('computer_action',args,'Ketik baru')['status'],'needs_input')
        tools._bridge.run.assert_not_called()
        self.assertEqual(tools.execute('computer_action',args,'Pilih semua lalu ketik baru')['status'],'dispatched')

    def test_literal_typing_distinguishes_instruction_comma_from_quoted_content(self):
        from assistant_tools import exact_requested_text
        self.assertEqual(exact_requested_text('Ketik persis UJI LEVA 012, lalu periksa.'),'UJI LEVA 012')
        self.assertEqual(exact_requested_text('Ketik persis "Halo, lalu pergi.", kemudian periksa.'),'Halo, lalu pergi.')

    def test_stale_or_password_control_cannot_receive_input(self):
        window=Mock();window.process_id.return_value=12
        args={'action':'type','window':'7','element':'missing:1','text':'hello'}
        with patch('feature_worker.target',return_value=window):
            with self.assertRaisesRegex(ValueError,'stale'):feature_worker.computer(args)
            element=Mock();element.element_info.element.CurrentIsPassword=True
            feature_worker.snapshots['fixture']={'time':__import__('time').monotonic(),'window':'7','pid':12,'controls':{'1':element}}
            with self.assertRaisesRegex(ValueError,'password'):feature_worker.computer({**args,'element':'fixture:1'})
            element.type_keys.assert_not_called()
        feature_worker.snapshots.clear()

    def test_watch_notifies_only_changed_results_and_stops_when_not_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationMemory(Path(folder)/'db');store.watch('Acer eGPU');bridge=Mock()
            bridge.run.return_value={'status':'done','sources':[{'title':'Fixture','url':'https://fixture.invalid/one'}]}
            service=ProactiveService(store,bridge);emit=Mock()
            with patch('autonomy_services.threading.Thread') as thread,patch('autonomy_services.time.time',return_value=10000):
                service.tick(emit,lambda:True);thread.call_args.kwargs['target']()
            emit.assert_called_once()
            service.last_tick=0
            with patch('autonomy_services.threading.Thread') as thread,patch('autonomy_services.time.time',return_value=20000):
                service.tick(emit,lambda:True);thread.call_args.kwargs['target']()
            emit.assert_called_once();bridge.run.reset_mock();service.last_tick=0
            service.tick(emit,lambda:False);bridge.run.assert_not_called()

if __name__=='__main__':unittest.main()
