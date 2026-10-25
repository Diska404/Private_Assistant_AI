"""Local web and routing regressions, with isolated vaults/journals and no model."""
import json,queue,socket,tempfile,urllib.request,urllib.error
from pathlib import Path
import unittest
from unittest.mock import Mock
from web_bridge import WebBridge
from web_data import WebData
from web_host import DesktopWebHost
from second_brain import SecondBrain
from preferences import Preferences
from task_journal import TaskJournal
from conversation_memory import ConversationMemory
from assistant_tools import selected_skills,AssistantTools
from scheduled_tasks import deferred_request

QUESTION='Leva menurut catatan obsidian saya apa prioritas pengembangan untuk suara live eh bisakah sebutkan sebenernya'
BRIEF='Buat briefing singkat: jam komputer saat ini, agenda lokal hari ini dan 3 headline berita terbaru dengan tautan sumber.'

class RoutingRegressionTests(unittest.TestCase):
    def test_briefing_is_not_a_scheduled_reminder(self):
        self.assertFalse(deferred_request(BRIEF));self.assertFalse(deferred_request('Briefing harian otomatis'))
        self.assertTrue(deferred_request('buatkan jadwal memo malam ini jam 19:00'))
        self.assertTrue(deferred_request('ingatkan saya besok jam 8 untuk briefing'))
        names={s.name for s in selected_skills(BRIEF)}
        self.assertIn('get_agenda',names);self.assertNotIn('add_agenda',names);self.assertNotIn('terminal',names)
    def test_new_spoken_question_does_not_resume_workspace_task(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=TaskJournal(Path(folder)/'tasks.db');ident=journal.begin('Buat web pesawat 3D');journal.wait_for_input(ident,'Pilih path workspace proyek mana?')
            self.assertIsNone(journal.continuation(QUESTION));self.assertIsNone(journal.continuation('bagaimana kabar hari ini'))
            self.assertEqual(journal.continuation('D:\\Projects')['id'],ident)
            self.assertEqual(journal.continuation('lanjut tugas '+ident)['id'],ident)
    def test_knowledge_scope_excludes_project_even_after_discovery(self):
        for groups in ((),('development',)):
            self.assertEqual({s.name for s in selected_skills(QUESTION,groups)},{'respond','ask_user','obsidian_action'})
        tools=AssistantTools.__new__(AssistantTools)
        result=tools.execute('terminal',{'action':'start','code':'print(1)'},QUESTION)
        self.assertEqual(result['code'],'knowledge_read_only_request')

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge=WebBridge(Mock(),port=0);self.bridge.update({'phase':'idle'});self.bridge.start();self.addCleanup(self.bridge.stop)
    def request(self,path,method='GET',body=None,authenticated=True,origin=None):
        headers={'Origin':origin or self.bridge.origin}
        if authenticated:headers['Cookie']='leva_session='+self.bridge.cookie
        raw=json.dumps(body).encode() if body is not None else None
        return urllib.request.urlopen(urllib.request.Request(self.bridge.origin+path,data=raw,method=method,headers=headers),timeout=3)
    def test_authentication_origin_host_and_no_cors(self):
        for authenticated,origin in ((False,None),(True,'https://example.com')):
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/state',authenticated=authenticated,origin=origin)
            self.assertIn(caught.exception.code,(401,403))
        with self.request('/api/state') as response:
            self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'));self.assertEqual(json.load(response)['state']['phase'],'idle')
    def test_bootstrap_cookie_is_http_only_and_fragment_secret_not_in_html(self):
        req=urllib.request.Request(self.bridge.origin+'/api/session',method='POST',headers={'Origin':self.bridge.origin,'X-Leva-Bootstrap':self.bridge.bootstrap})
        with urllib.request.urlopen(req) as response:
            self.assertIn('HttpOnly',response.headers['Set-Cookie']);self.assertIn('SameSite=Strict',response.headers['Set-Cookie'])
        with self.request('/') as response:self.assertNotIn(self.bridge.bootstrap,response.read().decode())
    def test_commands_deduplicate_and_do_not_execute_on_http_thread(self):
        payload={'id':'same-id-1234','kind':'chat','value':'jam berapa sekarang'}
        for _ in range(2):
            with self.request('/api/commands','POST',payload) as response:self.assertEqual(response.status,202)
        self.assertEqual(self.bridge.commands.qsize(),1);self.bridge.reader.assert_not_called()
    def test_avatar_modules_are_served_by_actual_bridge(self):
        for name in ('messages.js','trace.js','avatar.js','avatar.css','vrm_avatar.js','avatar_dynamics.js','avatar_performance.js','avatar-vendor.js','THIRD_PARTY_NOTICES.txt'):
            with self.request('/'+name) as response:
                self.assertEqual(response.status,200);self.assertGreater(len(response.read()),100)
    def test_avatar_upload_requires_auth_and_origin(self):
        for authenticated,origin in ((False,None),(True,'https://example.com')):
            with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/avatar-model','POST',{},authenticated,origin)
            self.assertIn(caught.exception.code,(401,403))
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/avatar-model','POST',{})
    def test_private_mode_trace_endpoint_is_empty(self):
        self.bridge.update({'workspace':'secret','trace_events':[{'event_type':'tool.started'}]})
        with self.request('/api/trace') as response:
            value=json.load(response);self.assertEqual(value['events'],[]);self.assertEqual(value.get('runs'),[])
    def test_invalid_commands_and_traversal_denied(self):
        for data in ({'id':'a','kind':'chat','value':'x'},{'id':'valid-id-123','kind':'terminal','value':'rm -rf'},{'id':'valid-id-123','kind':'route','value':'invented'}):
            with self.assertRaises(urllib.error.HTTPError):self.request('/api/commands','POST',data)
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/../preferences.sqlite3')
        self.assertEqual(caught.exception.code,404)
    def test_start_reuses_server_and_revision_returns_204(self):
        server=self.bridge.server;url=self.bridge.start();self.assertIs(server,self.bridge.server)
        self.assertTrue(url.startswith(self.bridge.origin+'/#session='))
        with self.request('/api/state?since='+str(self.bridge.revision)+'&instance='+self.bridge.instance) as response:self.assertEqual(response.status,204)
    def test_port_collision_falls_back_to_free_loopback_port(self):
        other=WebBridge(Mock(),port=self.bridge.server.server_port)
        try:
            other.start();self.assertNotEqual(other.server.server_port,self.bridge.server.server_port)
            self.assertEqual(other.server.server_address[0],'127.0.0.1')
        finally:other.stop()
    def test_shutdown_releases_socket(self):
        port=self.bridge.server.server_port;self.bridge.stop()
        with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',port),timeout=.5)
    def test_completed_command_history_is_bounded(self):
        for i in range(650):
            self.bridge.submit({'id':'bounded-id-'+str(i),'kind':'chat','value':'fixture'})
            self.bridge.finish(self.bridge.commands.get_nowait(),'dispatched')
        self.assertLessEqual(len(self.bridge.jobs),401)

class WebDataTests(unittest.TestCase):
    def test_graph_uses_note_and_receipt_provenance_only(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);vault=base/'vault';vault.mkdir()
            (vault/'One.md').write_text('# One\n[[Two]] [[Missing]]\n');(vault/'Two.md').write_text('# Two\n')
            prefs=Preferences(base/'prefs.db');prefs.set('obsidian_vault',str(vault))
            try:
                journal=TaskJournal(base/'tasks.db');ident=journal.begin('Read notes');journal.intent(ident,1,'obsidian_action',{'action':'read','path':'One.md'});journal.receipt(ident,1,{'status':'done'})
                tools=Mock();tools.second_brain=SecondBrain(prefs,base/'index');tools.conversations=ConversationMemory(base/'memory.db')
                data=WebData(tools,lambda:journal).graph();ids={n['id'] for n in data['nodes']}
                self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in data['edges']))
                links=[e for e in data['edges'] if e['relation']=='wikilink'];self.assertEqual(len(links),1)
                self.assertEqual(links[0]['provenance'],{'note':'One.md','link':'Two'})
                self.assertTrue(any(e['relation']=='calls_tool' for e in data['edges']))
            finally:prefs.close()
    def test_host_serializes_web_chat_on_existing_desktop_send(self):
        main=Mock();main.preferences.get.return_value='0';main.busy=True;main.entry.get.return_value='';main.events=queue.Queue();main._web_log=[]
        host=DesktopWebHost(main);host.last_update=__import__('time').monotonic()
        host.bridge.submit({'id':'first-message-001','kind':'chat','value':'hello'})
        host.poll();main.send.assert_not_called()
        main.busy=False;host.poll();main.send.assert_called_once_with('hello',client_context=None,workspace='assistant',attachments=[])
        host.poll();main.send.assert_called_once()
    def test_web_controls_use_existing_desktop_methods_and_busy_guard(self):
        main=Mock();main.preferences.get.return_value='0';main._web_log=[];main.busy=True
        host=DesktopWebHost(main)
        with self.assertRaises(ValueError):host.control({'kind':'route','value':'Dual GPU'})
        main.mode.set.assert_not_called();main.busy=False
        host.control({'kind':'route','value':'Google → 9Router → Dual GPU'})
        main.dual.set.assert_called_with(True);main.mode.set.assert_called_with('Google → 9Router → Dual GPU')
        host.control({'kind':'route','value':'RTX 4050'});main.dual.set.assert_called_with(False)
        host.control({'kind':'language','value':'ja'});main.speech_language.set.assert_called_with('日本語')
        host.control({'kind':'stop_voice'});main.stop_reply_voice.assert_called_once()
        host.bridge.submit({'id':'cancelled-chat-01','kind':'chat','value':'fixture'})
        host.control({'kind':'release'});main.release.assert_called_once()
        self.assertEqual(host.bridge.snapshot()['queue'],0);self.assertEqual(host.bridge.snapshot()['commands'][-1]['status'],'cancelled')

if __name__=='__main__':unittest.main()
