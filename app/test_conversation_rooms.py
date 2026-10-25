import io
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from conversation_rooms import ConversationRooms,PROMPTS,model_choices
from conversation_attachments import ConversationUploads,compose_message,extract_upload
from hybrid_engine import EngineError

class RoomTests(unittest.TestCase):
    def test_room_history_survives_restart_without_cross_room_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'rooms.db';a=ConversationRooms(p)
            a.append('chat','Anda','Analisis A');a.append('chat','Leva','Jawaban A');a.append('secret','Anda','Cerita B')
            b=ConversationRooms(p)
            self.assertEqual(b.rows('chat'),[('Anda','Analisis A'),('Leva','Jawaban A')])
            self.assertEqual(b.rows('secret'),[('Anda','Cerita B')]);b.clear('secret');self.assertEqual(b.rows('secret'),[])
            self.assertEqual(len(b.rows('chat')),2);a.db.close();b.db.close()

    def test_model_dispatch_is_local_and_never_supplies_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            rooms=ConversationRooms(Path(tmp)/'rooms.db');service=Mock();service.ask.return_value={'response':'Belum dijalankan.'};rooms.services['secret']=service
            model=Path(tmp)/'fixture.gguf';model.write_bytes(b'GGUF')
            try:
                with patch.dict('conversation_rooms.MODELS',{'qwen4b':('Fixture',model)}):
                    for gpu in ('gpu4050','gpu5070','dual'):
                        rooms.answer('secret','Buka Chrome dan jalankan PowerShell','qwen4b',gpu)
                        args,kw=service.ask.call_args
                        self.assertEqual(args[1:3],('local',gpu));self.assertNotIn('tool_executor',kw);self.assertNotIn('tool_context',kw)
                        self.assertEqual(kw['purpose'],'room_secret')
            finally:rooms.close()

    def test_tools_and_cloud_are_rejected_at_both_host_boundaries(self):
        from chat_service import ChatService
        service=ChatService()
        try:
            for purpose in PROMPTS:
                for kwargs in ({'tool_executor':Mock()},{'tool_context':{'tools':['shell']}},{'mode':'hybrid'}):
                    with self.assertRaisesRegex(EngineError,'conversation_room_tools_forbidden'):service.ask('buka Chrome',purpose=purpose,**{'mode':'local',**kwargs})
                with self.assertRaisesRegex(EngineError,'conversation_room_tools_forbidden'):service.ask_session('x','local','gpu5070','qwen4b','plain',False,tool_executor=Mock(),purpose=purpose)
        finally:service.cancel()

    def test_worker_rejects_tools_before_loading_model(self):
        from chat_service import run_worker
        with patch('chat_service.make_local') as make:
            with self.assertRaises(EngineError):run_worker({'purpose':'room_secret','mode':'local','agent':True})
            with self.assertRaises(EngineError):run_worker({'purpose':'room_chat','mode':'cascade'})
            make.assert_not_called()

    def test_room_gui_bypasses_desktop_command_dispatch(self):
        from gui import LevaWindow
        m=LevaWindow.__new__(LevaWindow);m.busy=False;m.workspace='chat';m.desktop=Mock();m.rooms=Mock();m.entry=Mock()
        with patch('room_ui.send_room') as send:
            m.send('Buka Chrome, hapus file dan buat pengingat')
            send.assert_called_once();m.desktop.handle.assert_not_called();m.desktop.tools.context.assert_not_called()

    def test_secret_large_model_warning_does_not_disable_model(self):
        choices=model_choices('secret')
        self.assertNotIn('Tidak Direkomendasikan',choices['qwen4b'])
        self.assertIn('Tidak Direkomendasikan',choices['saluki']);self.assertIn('Tidak Direkomendasikan',choices['qwen35b'])
        self.assertNotIn('Tidak Direkomendasikan',model_choices('chat')['saluki'])

    def test_user_upload_is_bounded_and_owned(self):
        uploads=ConversationUploads();r=uploads.save('phone-a','../../notes.txt',b'Saldo 7 dan 8')
        self.assertEqual(r['name'],'notes.txt')
        with self.assertRaises(ValueError):uploads.resolve('phone-b',[r['id']])
        rows=uploads.resolve('phone-a',[r['id']]);message=compose_message('Jumlahkan',rows)
        self.assertIn('Saldo 7 dan 8',message);self.assertTrue(message.endswith('Jumlahkan'))
        with self.assertRaises(ValueError):extract_upload('payload.exe',b'MZ')
        with self.assertRaises(ValueError):extract_upload('data.txt',b'\x00')
        row=extract_upload('long.txt',b'a'*14000);self.assertTrue(row['truncated']);self.assertEqual(len(row['text']),12000)

    def test_pdf_is_extracted_as_data(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=200)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (LEVA TEST 42) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream)
        data=io.BytesIO();writer.write(data);self.assertIn('LEVA TEST 42',extract_upload('test.pdf',data.getvalue())['text'])

    def test_web_queue_binds_workspace_before_switch_and_upload_owner(self):
        from web_bridge import WebBridge
        bridge=WebBridge(Mock());bridge.state={'workspace':'secret'}
        bridge.submit({'id':'room-test-123','kind':'chat','value':'Buka Chrome'})
        bridge.state['workspace']='assistant'
        job=bridge.commands.get_nowait();self.assertEqual(job['value']['workspace'],'secret')
        with self.assertRaises(ValueError):bridge.submit({'id':'room-test-123','kind':'chat','value':'Buka Chrome'})
        upload=bridge.uploads.save('phone','note.txt',b'text')
        with self.assertRaises(ValueError):bridge.submit({'id':'room-test-124','kind':'chat','value':{'workspace':'chat','text':'ringkas','attachments':[upload['id']]}})
        bridge.store.close()

    def test_local_voice_does_not_change_agent_route(self):
        from pipeline_routing import local_voice_route
        self.assertEqual(local_voice_route('Google → 9Router → RTX 5070'),'RTX 5070')
        self.assertEqual(local_voice_route('9Router → RTX 4050',True),'Dual GPU')
        from preferences import Preferences
        with tempfile.TemporaryDirectory() as tmp:
            p=Preferences(Path(tmp)/'prefs.db');p.set_many({'agent_provider':'Google → 9Router → Dual GPU','secret_model':'qwen4b','chat_model':'saluki'})
            p.set('provider','RTX 5070');self.assertEqual(p.get('agent_provider'),'Google → 9Router → Dual GPU');p.close()

    def test_adaptive_chat_switches_both_ways_and_uses_context_for_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            rooms=ConversationRooms(Path(tmp)/'rooms.db');service=Mock();service.history=[];service.ask.return_value={'response':'Baik.'};rooms.services['chat']=service
            rooms.answer('chat','Analisis jumlah 7 tambah 8','auto','gpu5070')
            self.assertEqual(service.ask.call_args.kwargs['local_model'],'saluki')
            rooms.answer('chat','Aku capek dan ingin curhat','auto','gpu5070')
            self.assertEqual(service.ask.call_args.kwargs['local_model'],'qwen4b')
            service.ask.side_effect=[{'response':'{"kind":"personal","confidence":0.94}'},{'response':'Aku mendengarkan.'}]
            rooms.answer('chat','lalu bagaimana ya','auto','gpu5070')
            self.assertEqual(rooms.last_route['chat']['model'],'qwen4b');self.assertEqual(rooms.last_route['chat']['method'],'local_classifier')
            service.ask.side_effect=None;service.ask.return_value={'response':'15.'}
            rooms.answer('chat','Jelaskan teori graf','auto','gpu5070')
            self.assertEqual(service.ask.call_args.kwargs['local_model'],'saluki');rooms.close()

    def test_attachment_forces_analysis_without_sending_its_contents_to_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            rooms=ConversationRooms(Path(tmp)/'rooms.db');service=Mock();service.history=[];service.ask.return_value={'response':'Analisis.'};rooms.services['chat']=service
            with patch('conversation_intent.public_research',return_value='sumber') as search:
                rooms.answer('chat','RAHASIA LAMPIRAN','auto','gpu5070',intent_text='cari sumber teori graf online',has_attachments=True)
                self.assertEqual(search.call_args.args,('cari sumber teori graf online',))
            self.assertEqual(rooms.last_route['chat']['model'],'saluki');rooms.close()

    def test_handoff_proposal_never_copies_until_accepted_and_full_history_is_cloned(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'rooms.db';rooms=ConversationRooms(p)
            for i in range(151):rooms.append('secret','Anda',str(i))
            rooms.propose('assistant','buat website');self.assertEqual(rooms.rows('assistant'),[])
            rooms.db.close();rooms=ConversationRooms(p)
            self.assertEqual(rooms.pending['target'],'assistant')
            rows=rooms.clone('secret','assistant');self.assertEqual(len(rows),151);self.assertEqual(len(rooms.rows('assistant',limit=None)),151);self.assertEqual(len(rooms.rows('secret',limit=None)),151)
            rooms.clear_pending();self.assertIsNone(rooms.pending);rooms.close()

    def test_labels_cover_all_text_models_and_rank_by_role(self):
        from conversation_rooms import MODELS,NO_AGENT
        for room in ('assistant','chat','secret'):self.assertTrue(set(MODELS)<=set(model_choices(room)))
        self.assertIn('(Direkomendasikan)',model_choices('assistant')['saluki'])
        self.assertIn('(Direkomendasikan)',model_choices('secret')['qwen4b'])
        for key in NO_AGENT:self.assertIn('(Tidak Direkomendasikan)',model_choices('assistant',include_trials=True)[key])

    def test_router_does_not_treat_quoted_or_negated_commands_as_execution(self):
        from conversation_intent import intent,parse_route
        self.assertNotEqual(intent('Jangan buka Chrome; jelaskan arti perintah itu')['kind'],'action')
        fallback=intent('lanjut ya','information')
        self.assertEqual(parse_route('{"kind":"personal","confidence":0.2}',fallback)['kind'],'information')
        self.assertEqual(parse_route('not json',fallback)['kind'],'information')

    def test_shared_speech_worker_policy_has_same_labels_without_room_imports(self):
        from speech_resources import AGENT_CHOICES
        self.assertEqual(AGENT_CHOICES,{k:v.removesuffix(' · belum tersedia') for k,v in model_choices('assistant').items()})
        source=Path(__file__).with_name('speech_resources.py').read_text(encoding='utf-8')
        self.assertNotIn('from conversation_rooms',source)

    def test_room_asr_yield_never_blocks_tk_thread(self):
        import threading
        from test_task_reactions import TaskReactionTests
        from room_ui import send_room
        m=TaskReactionTests().window('id');m.workspace='chat';m.room_attachments=[];m.rooms=Mock();m.rooms.answer.return_value={'response':'15.','provider':'local'}
        m.spoken_replies.get.return_value=False;m.preferences.get.side_effect=lambda key:{'chat_model':'qwen4b','chat_gpu':'gpu5070',**__import__('preferences').DEFAULTS,'speech_language':'id'}[key]
        entered=threading.Event();release=threading.Event();owner=threading.get_ident()
        def hold():
            self.assertNotEqual(threading.get_ident(),owner);entered.set();release.wait(2)
        m.local_mic.hold_asr.side_effect=hold
        try:
            start=time.perf_counter();send_room(m,'Analisis 7+8');self.assertLess(time.perf_counter()-start,.2);self.assertTrue(entered.wait(1));self.assertTrue(m.busy)
        finally:release.set()
        end=time.monotonic()+2
        while m.events.empty() and time.monotonic()<end:time.sleep(.01)
        self.assertFalse(m.events.empty());m.rooms.answer.assert_called_once()

    def test_native_room_selectors_follow_settings_changed_from_phone(self):
        from room_ui import sync_room_controls
        model=Mock();model.get.return_value='old';gpu=Mock();gpu.get.return_value='RTX 4050'
        main=Mock();main.room_controls={'secret':(model,gpu,model_choices('secret'))}
        main.preferences.get.side_effect={'secret_model':'saluki','secret_gpu':'dual'}.__getitem__
        sync_room_controls(main)
        self.assertEqual(model.set.call_args.args,(model_choices('secret')['saluki'],));gpu.set.assert_called_with('Dual GPU')

if __name__=='__main__':unittest.main()
