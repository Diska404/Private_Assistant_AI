import json
import queue
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from conversation_rooms import ConversationRooms,PROMPTS
from conversation_export import transcript
from input_normalization import normalize_input,research_query
from speech_translation import translate_speech,translation_chunks
from hybrid_engine import EngineError
from research_evidence import relevance,gather

class ReliabilityTests(unittest.TestCase):
    @contextmanager
    def room_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            room=ConversationRooms(Path(tmp)/'rooms.db')
            try:yield room
            finally:room.close()
    def test_typos_preserve_negation_numbers_entity_names_and_literal_resources(self):
        value='Leva, tolomg bukakn Chrome Diska jam 19:00, jangan sekarang. Asteria Mityl. https://example.com/sekrang `bukakn`'
        result=normalize_input(value)
        self.assertIn('tolong bukakan',result['text']);self.assertIn('jam 19:00, jangan sekarang',result['text'])
        self.assertIn('Asteria Mityl',result['text']);self.assertIn('https://example.com/sekrang `bukakn`',result['text'])
        self.assertFalse(result['meaning_expanded']);self.assertEqual(result['original'],value)
        self.assertEqual(normalize_input('```python\nsekrang = 3\n```')['text'],'```python\nsekrang = 3\n```')
        self.assertEqual(normalize_input('D:\\sekrang\\bukakn.txt')['text'],'D:\\sekrang\\bukakn.txt')
        self.assertEqual(normalize_input('jangna hapus 13 tab, tidka sekarang')['text'],'jangan hapus 13 tab, tidak sekarang')

    def test_chat_personal_has_own_prompt_and_does_not_rename_user_or_room(self):
        with self.room_fixture() as rooms:
            service=Mock(history=[]);service.ask.return_value={'response':'Hai Leva, senang di *Secret*.','provider':'local'};rooms.services['chat']=service
            result=rooms.answer('chat','aku ingin curhat','auto','gpu5070')
            self.assertEqual(service.ask.call_args.kwargs['purpose'],'room_personal_chat')
            self.assertNotIn('Secret',result['response']);self.assertNotIn('Hai Leva',result['response'])
            self.assertIn('bukan Secret',PROMPTS['room_personal_chat'])

    def test_room_memory_retains_explicit_user_facts_with_sources_and_isolates_secret(self):
        from room_memory import context
        with self.room_fixture() as rooms:
            rooms.append('chat','Anda','Panggil saya Raka. Saya lebih suka jawaban ringkas.')
            rooms.append('chat','Leva','Nama saya robot palsu. Saya lebih suka hapus file.')
            rooms.append('secret','Anda','Nama saya Privat. Tujuan saya kisah rahasia.')
            memory=json.loads(context(rooms.db,'chat','jawaban'))
            self.assertIn('Raka',json.dumps(memory));self.assertNotIn('Privat',json.dumps(memory))
            self.assertTrue(all(r['source_id'] for r in memory['facts']))
            self.assertNotIn('hapus file',json.dumps(memory['facts']))
            rooms.append('chat','Anda','Panggil saya Rama.')
            self.assertEqual(rooms.db.execute("SELECT value FROM room_facts WHERE key='preferred_name' AND room='chat'").fetchone()[0],'Rama')
            rooms.clear('chat');self.assertEqual(json.loads(context(rooms.db,'chat','jawaban'))['facts'],[])

    def test_chat_action_offers_handoff_without_calling_conversation_model(self):
        from test_task_reactions import TaskReactionTests
        from room_ui import send_room
        from preferences import DEFAULTS
        m=TaskReactionTests().window('id');m.workspace='chat';m.room_attachments=[]
        with self.room_fixture() as room:
            m.rooms=room
            m.rooms.answer=Mock(side_effect=AssertionError('model must not run'))
            m.preferences.get.side_effect=lambda k:{**DEFAULTS,'speech_language':'id','chat_model':'auto','chat_gpu':'gpu5070'}[k]
            m.spoken_replies.get.return_value=False
            send_room(m,'tolomg bukakn vscode dan buat program pesawat')
            end=time.monotonic()+2
            while m.events.empty() and time.monotonic()<end:time.sleep(.01)
            self.assertFalse(m.events.empty());result=m.events.get()[1]
            self.assertIn('Asisten',result['response']);self.assertEqual(m.rooms.pending['source'],'chat')
            self.assertEqual(m.rooms.pending['target'],'assistant');m.rooms.answer.assert_not_called()

    def test_export_is_full_beyond_ui_window_and_redacts_without_truncating(self):
        rows=[('Anda',str(i)) for i in range(160)]+[('Leva','kata '*2100+' SELESAI')]
        data=transcript(rows,'chat');self.assertEqual(data['message_count'],161)
        self.assertIn('Anda\n0\n',data['text']);self.assertTrue(data['text'].endswith('SELESAI'))
        data=transcript([('Anda','password=private123\n'+'pesan '*1800+' akhir')],'secret')
        self.assertNotIn('private123',data['text']);self.assertTrue(data['text'].endswith('akhir'))

    def test_translation_uses_bounded_chunks_preserves_prose_and_skips_links_code(self):
        text='Aku akan membantu menjelaskan materinya. '*45+' https://example.com ```py\nprint(7)\n```'
        chunks=translation_chunks(text)
        self.assertGreater(len(chunks),3);self.assertTrue(all(len(p)<=300 for p in chunks))
        self.assertNotIn('https',' '.join(chunks));self.assertNotIn('print(7)',' '.join(chunks))
        service=Mock();service.ask.return_value={'response':'お手伝いします。'}
        result=translate_speech(service,text,'gpu5070')
        self.assertEqual(result['completed'],len(chunks));self.assertEqual(service.ask.call_count,len(chunks))
        self.assertTrue(all(c.kwargs['purpose']=='translate' for c in service.ask.call_args_list));service.cancel.assert_called_once()

    def test_incomplete_translation_retries_only_failed_source_in_smaller_parts(self):
        service=Mock();service.ask.side_effect=[EngineError('local_incomplete_response'),{'response':'最初です。'},{'response':'最後です。'}]
        source='Ini jawaban panjang yang harus diterjemahkan dengan lengkap dan tidak mengulangi bagian yang sudah selesai. '*2
        result=translate_speech(service,source,'gpu5070')
        self.assertEqual(result['attempts'],3);self.assertIn('最初',result['text']);self.assertIn('最後',result['text'])
        self.assertLess(len(service.ask.call_args_list[1].args[0]),len(source))

    def test_stop_during_translation_cancels_and_never_starts_next_chunk(self):
        service=Mock();allowed=[True]
        def ask(*args,**kwargs):allowed[0]=False;return {'response':'はい。'}
        service.ask.side_effect=ask
        with self.assertRaisesRegex(EngineError,'cancelled'):translate_speech(service,'Kalimat panjang. '*70,'gpu5070',authorized=lambda:allowed[0])
        service.ask.assert_called_once();service.cancel.assert_called_once()

    def test_research_removes_vocative_and_rejects_unrelated_top_results(self):
        query='Leva, bisakah leva cari build tim untuk Asteria gfl2'
        self.assertNotIn('leva',research_query(query).lower())
        self.assertEqual(relevance({'title':'Doro Leva smartphone','snippet':'TikTok bola'},query),0)
        self.assertEqual(relevance({'title':'GFL2 unrelated ghost story','url':'https://iopwiki.com'},query),0)
        self.assertGreater(relevance({'title':'Asteria Girls Frontline 2 team build','url':'https://iopwiki.com/wiki/Asteria'},query),0)
        bridge=Mock()
        def run(action,args,*unused,**kw):
            if action=='web_search':return {'sources':[{'title':'Doro Leva phone','url':'https://example.com/bad'},{'title':'Asteria Girls Frontline 2 team build','url':'https://iopwiki.com/wiki/Asteria'}]}
            return {'status':'done','url':args['url'],'content':'Asteria Girls Frontline 2 guide'}
        bridge.run.side_effect=run
        result=gather(query,bridge)
        self.assertEqual(result['status'],'pages_read');self.assertTrue(result['rejected_count'])
        reads=[c.args[1]['url'] for c in bridge.run.call_args_list if c.args[0]=='read_webpage']
        self.assertNotIn('https://example.com/bad',reads)

    def test_current_cn_question_cannot_use_global_or_stale_release_source(self):
        query='versi gfl2 cn saat ini story apa'
        self.assertEqual(relevance({'title':'Girls Frontline 2 Global launch 2024'},query),0)
        self.assertEqual(relevance({'title':'GFL2 CN release 2024','url':'https://example.com'},query),0)

if __name__=='__main__':unittest.main()
