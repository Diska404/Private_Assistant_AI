import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]
from assistant_tools import AssistantTools,AppCatalog,PersonalMemory,SKILLS,validate_call,safe_url
from agent_runtime import run_agent
from desktop_service import DesktopService
from test_desktop import INVENTORY
from reply_voice import speech_chunks
from voice_pack_service import VoicePackService
from test_warm_sessions import Worker


class SkillTests(unittest.TestCase):
    def desktop(self):
        with patch('desktop_service.inspect_profiles',return_value=INVENTORY):return DesktopService(browser=Mock())

    def test_clock_uses_host_timestamp_instead_of_model_memory(self):
        from datetime import datetime
        from command_resolution import WIB
        result=self.desktop().handle('jam berapa sekarang',datetime(2026,10,19,14,23,tzinfo=WIB))
        self.assertIn('14.23',result['reply']);self.assertEqual(result['evidence']['source'],'system_clock')

    def test_chatgpt_destination_survives_profile_question(self):
        desktop=self.desktop();desktop.browser.launch.return_value={'new_window_observed':True,'dispatched':True}
        first=desktop.handle('buka kan chrome saya untuk membuka chatgpt')
        self.assertIn('profil',first['reply']);desktop.browser.launch.assert_not_called()
        result=desktop.handle('Diska')
        desktop.browser.launch.assert_called_once_with(INVENTORY['profiles'][0],url='https://chatgpt.com/')
        self.assertIn('chatgpt.com',result['reply']);self.assertIsNone(desktop.pending_browser)

    def test_new_request_cannot_inherit_stale_browser_destination(self):
        desktop=self.desktop();desktop.handle('buka ChatGPT');desktop.handle('jam berapa sekarang');desktop.handle('Diska')
        desktop.browser.launch.assert_not_called()

    def test_natural_profile_answer_retains_requested_page(self):
        desktop=self.desktop();desktop.browser.launch.return_value={'new_window_observed':True}
        desktop.handle('buka ChatGPT');desktop.handle('pakai profil Diska')
        desktop.browser.launch.assert_called_once_with(INVENTORY['profiles'][0],url='https://chatgpt.com/')

    def test_negated_or_quoted_browser_instructions_do_not_execute(self):
        desktop=self.desktop()
        for text in ('jangan buka ChatGPT di Diska','terjemahkan buka ChatGPT di Diska','contoh buka Chrome Diska'):
            desktop.handle(text)
        desktop.browser.launch.assert_not_called()

    def test_tools_are_described_and_strictly_validated(self):
        self.assertTrue(all(s.declaration()['function']['name']==s.name for s in SKILLS))
        for name,args in [('shell',{'command':'anything'}),('open_app',{'path':'C:/a.exe'}),('get_time',{'extra':'x'})]:
            with self.assertRaises(ValueError):validate_call(name,args)

    def test_unrequested_url_is_not_dispatched(self):
        desktop=self.desktop();tools=AssistantTools(desktop)
        result=tools.execute('open_browser',{'profile':'Diska','url':'https://example.com/'},'buka ChatGPT')
        self.assertEqual(result['status'],'needs_input');desktop.browser.launch.assert_not_called()
        for url in ('javascript:alert(1)','file:///C:/a','https://user:pass@example.com','https://example.com/\n'):
            with self.assertRaises(ValueError):safe_url(url)

    def test_model_cannot_open_app_from_a_greeting_or_after_cancellation(self):
        tools=AssistantTools(self.desktop())
        with patch.object(tools.apps,'launch') as launch:
            self.assertEqual(tools.execute('open_app',{'app':'Discord'},'hai')['status'],'needs_input')
            self.assertEqual(tools.execute('open_app',{'app':'Discord'},'buka Discord',lambda:False)['status'],'cancelled')
            launch.assert_not_called()

    def test_running_application_is_raised_without_duplicate_launch(self):
        catalog=AppCatalog();catalog.apps={};catalog.add('Discord',Path('C:/fixture/Discord.exe'),('discord',),'Discord.exe')
        with patch('windows_runtime.application_windows',return_value=[7]),patch('windows_runtime.raise_window',return_value=True),patch('assistant_tools.subprocess.Popen') as popen:
            result=catalog.launch('discord')
        self.assertTrue(result['already_running']);self.assertEqual(result['status'],'done');popen.assert_not_called()

    def test_unknown_app_does_not_become_an_executable_command(self):
        catalog=AppCatalog()
        with patch('assistant_tools.subprocess.Popen') as popen:
            self.assertEqual(catalog.launch('notepad.exe & whoami')['status'],'needs_input')
            popen.assert_not_called()

    def test_explicit_notes_survive_restart_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'memory.sqlite3';store=PersonalMemory(path)
            store.remember('Saya menggunakan laptop Acer.');store.remember('Saya menggunakan laptop Acer.')
            rows=PersonalMemory(path).recall('Acer');self.assertEqual(len(rows),1)
            store.forget(rows[0]['id']);self.assertEqual(store.recall(),[])
            with self.assertRaises(ValueError):store.remember('API key: secret')

    def test_memory_requires_user_request_and_literal_search_does_not_widen(self):
        tools=AssistantTools(self.desktop());tools.memory=Mock()
        self.assertEqual(tools.execute('remember',{'note':'X'},'halo')['status'],'needs_input');tools.memory.remember.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            store=PersonalMemory(Path(folder)/'m.sqlite3');store.remember('ordinary note')
            self.assertEqual(store.recall('%'),[])

    def test_agent_uses_host_receipt_and_does_not_repeat_an_action(self):
        local=Mock();local.propose_tool.side_effect=[{'action':'open_app','args':{'app':'Discord'}},
            {'action':'open_app','args':{'app':'Discord'}},{'action':'respond','args':{'text':'Discord sudah terbuka.','speech_text':'Discord sudah terbuka.'}}]
        commands=queue.Queue();events=[]
        def emit(event):
            events.append(event);commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'Jendela Discord terdeteksi.'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'tolong siapkan Discord'}]},local,commands,emit)
        self.assertEqual(len(events),1);self.assertEqual(len(result['tool_receipts']),1)
        self.assertIn('terbuka',result['response'])

    def test_agent_never_promotes_unverified_receipt_to_success(self):
        local=Mock();local.propose_tool.side_effect=[{'action':'open_app','args':{'app':'Discord'}},
            {'action':'respond','args':{'text':'Sukses dibuka!','speech_text':'Sukses dibuka!'}}]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'unverified','reply':'Permintaan terkirim; jendela belum terkonfirmasi.'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'buka Discord'}]},local,commands,emit)
        self.assertIn('belum terkonfirmasi',result['response']);self.assertNotIn('Sukses',result['response'])

    def test_japanese_chunks_keep_all_text_and_do_not_read_thinking(self):
        text='こんにちは。いつでもお手伝いします。'*20
        parts=speech_chunks(text,'ja');self.assertTrue(all(len(p)<=100 for p in parts))
        self.assertEqual(''.join(parts),text)
        self.assertNotIn('private',' '.join(speech_chunks('<think>private</think>こんにちは。','ja')))

    def test_search_snippet_cannot_complete_requested_article_reading(self):
        local=Mock();final={'action':'respond','args':{'text':'Sudah membaca artikel.','speech_text':'Sudah membaca artikel.'}}
        local.propose_tool.side_effect=[{'action':'web_search','args':{'query':'egpu'}},final,final,final]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','sources':[{'url':'https://example.com/one'}]}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Cari dan baca artikel egpu'}]},local,commands,emit)
        self.assertTrue(result['incomplete']);self.assertNotIn('Sudah membaca',result['response'])

    def test_dispatched_typing_cannot_complete_without_reinspection(self):
        local=Mock();final={'action':'respond','args':{'text':'Selesai terverifikasi.','speech_text':'Selesai terverifikasi.'}}
        local.propose_tool.side_effect=[{'action':'computer_action','args':{'action':'type','window':'7','element':'token:1','text':'uji'}},final,final,final]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'dispatched'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Ketik uji di Notepad'}]},local,commands,emit)
        self.assertTrue(result['incomplete']);self.assertNotIn('Selesai terverifikasi',result['response'])

    def test_google_transport_failure_continues_with_local_model(self):
        from hybrid_engine import EngineError
        local=Mock();local.propose_tool.return_value={'action':'respond','args':{'text':'Halo.','speech_text':'Halo.'}}
        with patch('agent_runtime.online_propose_tool',side_effect=EngineError('online_transport_failure')):
            result=run_agent({'id':1,'mode':'hybrid','messages':[{'role':'user','content':'Halo'}]},local,queue.Queue(),Mock())
        self.assertEqual(result['provider'],'local');self.assertEqual(result['fallback_reason'],'online_transport_failure')

    def test_large_inspection_keeps_active_goal_and_editable_element(self):
        commands=queue.Queue();goal='Ketik UJI di editor aktif lalu verifikasi.'
        def choose(messages,declarations):
            if commands.empty() and not any('Hasil host' in m['content'] for m in messages):
                return {'action':'computer_action','args':{'action':'inspect','window':'7','element':'','text':''}}
            self.assertTrue(any(goal in m['content'] for m in messages))
            data=messages[-1]['content'];self.assertIn('EDITABLE_TARGET',data)
            self.assertLess(len(data),16000)
            return {'action':'ask_user','args':{'text':'Hasil diamati.','speech_text':'Hasil diamati.'}}
        local=Mock();local.propose_tool.side_effect=choose
        def emit(event):
            rows=[{'element':str(i),'name':'x'*200,'type':'Text'} for i in range(199)]+[{'element':'EDITABLE_TARGET','name':'Editor','type':'Document'}]
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','elements':rows}})
        run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':goal}]},local,commands,emit)

    def test_reinspection_of_wrong_text_cannot_claim_exact_typing(self):
        args={'window':'7','element':'fixture:1','text':'UJI LEVA 012'}
        local=Mock();local.propose_tool.side_effect=[{'action':'computer_action','args':{**args,'action':'type'}},{'action':'computer_action','args':{**args,'action':'inspect'}},{'action':'respond','args':{'text':'Persis dan selesai.','speech_text':'Persis dan selesai.'}}]
        commands=queue.Queue()
        def emit(event):
            result={'status':'dispatched'} if event['args']['action']=='type' else {'status':'done','elements':[{'type':'Document','name':'Editor','observed_text':'UJI EEVA 012'}]}
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Ketik persis UJI LEVA 012 lalu periksa'}]},local,commands,emit)
        self.assertTrue(result['incomplete']);self.assertNotIn('Persis dan selesai',result['response'])

    def test_switching_voice_language_restarts_correct_runtime(self):
        service=VoicePackService(persistent=True);worker=Worker();service.worker=worker;service.events=worker.events
        with tempfile.TemporaryDirectory() as directory,patch('voice_pack_service.PREVIEWS',Path(directory)),patch('voice_pack_service.resolve_pack',return_value={'actual':'neutral_id','available':True}),patch('voice_pack_service.validate_preview',side_effect=lambda p:(Path(p),.2)):
            try:
                service.generate('neutral_id','Halo.');first=worker.started[0]
                service.accept_generated({'actual_pack':'neutral_id','path':first['output'],'request_id':first['request_id']})
                service.finish();service.generate('neutral_id','こんにちは。',language='ja')
                self.assertEqual(len(worker.started),2);self.assertEqual(worker.started[-1]['language'],'ja')
                self.assertIn('voice-leva-bilingual',worker.worker_command[0])
            finally:service.stop()

    def test_real_tool_ipc_roundtrip_executes_once_and_keeps_history_in_parent(self):
        from chat_service import ChatService
        code="import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if r['kind']=='ask':\n  print(json.dumps({'kind':'tool_call','id':r['id'],'call_id':1,'name':'get_time','args':{}}),flush=True)\n else:\n  print(json.dumps({'kind':'result','id':r['id'],'provider':'local','response':r['result']['reply']}),flush=True)"
        service=ChatService([sys.executable,'-u','-c',code],persistent=True)
        executor=Mock(return_value={'status':'done','reply':'Clock from host.'})
        try:
            result=service.ask('What time?','local',tool_executor=executor)
            self.assertEqual(result['response'],'Clock from host.');self.assertEqual(executor.call_count,1)
            self.assertEqual(len(service.history),2)
        finally:service.cancel()

if __name__=='__main__':unittest.main()
