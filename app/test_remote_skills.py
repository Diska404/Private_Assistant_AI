from pathlib import Path
import json
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch
from spoken_text import prepare_spoken_text
from reply_voice import ReplyVoice,speech_chunks
from file_workspace import FileWorkspace,checked_path
from workflow_skills import WorkflowSkills
from assistant_tools import AssistantTools,selected_skills,validate_call
from agent_runtime import run_agent
from system_controls import control
from receipt_state import unresolved_receipts
from scheduled_tasks import completion_status


class SpeechPresentationTests(unittest.TestCase):
    def test_url_emoji_and_markup_are_not_spelled_out(self):
        source='Siap 😊. Baca [artikel eGPU](https://example.com/a). Sumber: https://example.com/b?q=1 😀'
        spoken=prepare_spoken_text(source)
        self.assertIn('artikel eGPU',spoken);self.assertNotIn('http',spoken);self.assertNotIn('example.com',spoken);self.assertNotIn('😊',spoken)
        self.assertIn('https://',source)
        self.assertNotIn('edlink.id',prepare_spoken_text('Bukalah edlink.id untuk tugas.'))

    def test_url_labels_and_japanese_are_cleaned(self):
        spoken=prepare_spoken_text('確認したよ😊。[https://example.com](https://example.com) 結果は画面にあるよ。','ja')
        self.assertIn('結果は画面',spoken);self.assertNotIn('example',spoken);self.assertNotIn('😊',spoken)
        self.assertIn('画面',prepare_spoken_text('https://example.com','ja'))
        self.assertNotIn('リンクは。',prepare_spoken_text('リンクは https://example.com 。結果は画面にあります。','ja'))

    def test_tables_code_and_paths_use_short_screen_cues(self):
        text='Jam 19:00 WIB.\n| Nama | Nilai |\n|---|---|\n| GPU | 40 |\n```python\nsecret()\n```\nD:\\catatan\\tugas.txt'
        spoken=prepare_spoken_text(text)
        self.assertIn('19:00',spoken);self.assertNotIn('secret',spoken);self.assertNotIn('tugas.txt',spoken)
        self.assertEqual(spoken.count('tabel'),1)

    def test_emoji_only_is_silent_and_plain_prose_preserved(self):
        self.assertEqual(speech_chunks('😊💙✨'),[])
        self.assertEqual(prepare_spoken_text('Aku siap menemanimu.'),'Aku siap menemanimu.')
        voice=ReplyVoice(Mock());self.assertIsNone(voice.speak('😊','higgs_jp_identity'));voice.service.generate.assert_not_called()

    def test_emoticon_and_thinking_removed_without_losing_important_numbers(self):
        spoken=prepare_spoken_text('<think>internal</think> Gunakan RTX 4050 pada jam 19:00 :)')
        self.assertNotIn('internal',spoken);self.assertNotIn(':)',spoken);self.assertIn('4050',spoken);self.assertIn('19:00',spoken)
        self.assertNotIn(' .',prepare_spoken_text('Siap 😊.'))


class FileOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.files=FileWorkspace(self.root/'history');self.files.observed.add(str(self.root))
    def runfile(self,action,path,**kwargs):return self.files.run({'action':action,'path':str(path),**kwargs},str(self.root))

    def test_write_read_and_conflict_aware_undo(self):
        path=self.root/'memo.txt';result=self.runfile('write',path,text='Tugas matematika diskrit pukul 19:00.')
        self.assertIn('diskrit',self.runfile('read',path)['content'])
        ident=result['operation_id'];path.write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'undo_conflict'):self.files.undo(ident,lambda:True)
        path.write_text('Tugas matematika diskrit pukul 19:00.',encoding='utf-8');self.files.undo(ident,lambda:True)
        self.assertFalse(path.exists());self.assertEqual(self.files.undo(ident,lambda:True)['status'],'done')

    def test_overwrite_is_backed_up_and_restored(self):
        path=self.root/'memo.txt';path.write_text('original',encoding='utf-8')
        result=self.runfile('write',path,text='new');self.files.undo(result['operation_id'],lambda:True)
        self.assertEqual(path.read_text('utf-8'),'original')

    def test_copy_move_and_undo(self):
        a=self.root/'a.txt';b=self.root/'b.txt';c=self.root/'c.txt';a.write_text('a',encoding='utf-8')
        copied=self.runfile('copy',a,destination=str(b));self.assertTrue(b.exists())
        self.files.undo(copied['operation_id'],lambda:True);self.assertFalse(b.exists())
        moved=self.runfile('move',a,destination=str(c));self.assertFalse(a.exists())
        self.files.undo(moved['operation_id'],lambda:True);self.assertTrue(a.exists());self.assertFalse(c.exists())

    def test_existing_destination_and_unobserved_path_rejected(self):
        a=self.root/'a.txt';b=self.root/'b.txt';a.write_text('a');b.write_text('b')
        with self.assertRaises(ValueError):self.runfile('copy',a,destination=str(b))
        nested=self.root/'unknown'/'memo.txt'
        with self.assertRaisesRegex(ValueError,'not_observed'):self.runfile('write',nested,text='x')

    def test_search_and_protected_paths(self):
        (self.root/'tugas.txt').write_text('data');(self.root/'API Key.txt').write_text('not-for-reading')
        rows=self.runfile('list',self.root)['files'];self.assertEqual(len(rows),1)
        self.assertEqual(len(self.runfile('search',self.root,text='tugas')['paths']),1)
        with self.assertRaises(ValueError):self.runfile('read',self.root/'API Key.txt')
        with self.assertRaises(ValueError):checked_path(r'C:\Windows\System32\test.txt')

    def test_folder_undo_never_deletes_children(self):
        folder=self.root/'folder';row=self.runfile('mkdir',folder)
        (folder/'keep.txt').write_text('keep')
        with self.assertRaises(OSError):self.files.undo(row['operation_id'],lambda:True)
        self.assertTrue((folder/'keep.txt').is_file())


class RemoteToolTests(unittest.TestCase):
    def test_new_tools_selected_lazily(self):
        names={s.name for s in selected_skills('halo')}
        self.assertNotIn('browser_action',names);self.assertNotIn('file_action',names)
        self.assertIn('browser_action',{s.name for s in selected_skills('isi formulir web')})
        self.assertIn('file_action',{s.name for s in selected_skills('simpan catatan di folder')})
        validate_call('browser_action',{'action':'tabs'})

    def test_file_overwrite_requires_explicit_update(self):
        tools=AssistantTools.__new__(AssistantTools);tools.files=Mock()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x.txt';path.write_text('keep')
            result=tools.execute('file_action',{'action':'write','path':str(path),'text':'new'},'buat catatan')
        self.assertEqual(result['status'],'needs_input');tools.files.run.assert_not_called()

    def test_settings_do_not_change_from_read_only_or_wrong_subject(self):
        tools=AssistantTools.__new__(AssistantTools);tools._bridge=Mock()
        result=tools.execute('system_settings',{'action':'volume','value':'20'},'lihat volume saya')
        self.assertEqual(result['status'],'needs_input');tools._bridge.run.assert_not_called()
        result=tools.execute('system_settings',{'action':'volume','value':'20'},'atur kecerahan ke 20')
        self.assertEqual(result['status'],'needs_input')

    def test_audio_setting_reads_back_actual_value(self):
        endpoint=Mock();endpoint.GetMasterVolumeLevelScalar.side_effect=[.5,.2];endpoint.GetMute.return_value=0
        device=Mock();device.EndpointVolume=endpoint;device.FriendlyName='fixture'
        with patch.dict('sys.modules',{'pycaw':Mock(),'pycaw.pycaw':Mock(AudioUtilities=Mock(GetSpeakers=Mock(return_value=device)))}):
            result=control({'action':'volume','value':'20'})
        self.assertEqual(result['status'],'done');self.assertEqual(result['after']['volume_percent'],20)

    def test_browser_input_requires_reinspection_before_success(self):
        local=Mock();final={'action':'respond','args':{'text':'Selesai','speech_text':'Selesai'}}
        local.propose_tool.side_effect=[{'action':'browser_action','args':{'action':'fill','tab':'fixture','element':'fixture:0','text':'hello'}},final,final,final]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'dispatched','reply':'Input terkirim'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'isi formulir web'}]},local,commands,emit)
        self.assertTrue(result['incomplete']);self.assertNotEqual(result['response'],'Selesai')

    def test_curated_workflows_are_data_and_missing_catalog_is_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalog.json';store=WorkflowSkills(path)
            self.assertEqual(store.public(),[])
            path.write_text(json.dumps([{'id':'web','title':'Web','description':'test','triggers':['browser'],'instructions':'Inspect before action.','source':'fixture'}]))
            self.assertEqual(store.relevant('buka browser')[0]['id'],'web')
            with self.assertRaises(ValueError):store.get('../../other')

    def test_browser_stale_snapshot_is_recoverable_and_url_slash_is_equivalent(self):
        tools=AssistantTools.__new__(AssistantTools);tools._bridge=Mock();tools.allowed_web_urls=set()
        tools._bridge.run.side_effect=ValueError('stale_browser_snapshot')
        result=tools.execute('browser_action',{'action':'fill','tab':'x','element':'old:0','text':'x'},'isi formulir web')
        self.assertTrue(result['retryable']);self.assertIn('inspect',result['reply'])
        tools._bridge.run.side_effect=None;tools._bridge.run.return_value={'status':'done'}
        result=tools.execute('browser_action',{'action':'open','url':'https://example.com'},'buka https://example.com/')
        self.assertEqual(result['status'],'done')

    def test_recovered_input_is_complete_only_after_same_action_and_inspection(self):
        receipts=[{'name':'browser_action','args':{'action':'click','tab':'1'},'result':{'status':'failed','retryable':True}},
                  {'name':'browser_action','args':{'action':'inspect','tab':'1'},'result':{'status':'done'}}]
        self.assertEqual(len(unresolved_receipts(receipts)),1)
        receipts.append({'name':'browser_action','args':{'action':'click','tab':'1'},'result':{'status':'dispatched'}})
        self.assertTrue(unresolved_receipts(receipts))
        receipts.append({'name':'browser_action','args':{'action':'inspect','tab':'1'},'result':{'status':'done'}})
        self.assertEqual(unresolved_receipts(receipts),[])
        self.assertEqual(completion_status({'tool_receipts':receipts}),'completed')

    def test_exact_file_text_cannot_be_rewritten_by_model(self):
        tools=AssistantTools.__new__(AssistantTools);tools.files=Mock()
        result=tools.execute('file_action',{'action':'write','path':r'D:\fixture\test.txt','text':'Changed'},'buat file lalu tulis persis "Keep this."')
        self.assertEqual(result['code'],'literal_file_text_mismatch');tools.files.run.assert_not_called()


if __name__=='__main__':unittest.main()
