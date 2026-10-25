from pathlib import Path
import difflib
import json
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
from terminal_service import TerminalService
from project_workspace import ProjectWorkspace
from task_journal import TaskJournal
from agent_runtime import run_agent
from assistant_tools import AssistantTools
from desktop_service import DesktopService
from receipt_state import unresolved_receipts


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'project';self.root.mkdir();self.project=ProjectWorkspace(Path(self.temp.name)/'history')
    def diff(self,name,before,after):return ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))

    def test_large_file_chunk_search_preview_apply_rollback(self):
        before=''.join(f'line {i}\n' for i in range(1000));path=self.root/'large.txt';path.write_text(before,encoding='utf-8')
        read=self.project.read(self.root,'large.txt',900,3);self.assertEqual(read['total_lines'],1000);self.assertIn('line 900',read['content'])
        self.assertEqual(self.project.search(self.root,'line 900')['matches'][0]['line'],901)
        after=before.replace('line 900\n','line fixed\n');preview=self.project.preview(self.root,self.diff('large.txt',before,after))
        self.assertEqual(path.read_text('utf-8'),before)
        self.project.change(preview['patch_id']);self.assertEqual(path.read_text('utf-8'),after)
        self.project.change(preview['patch_id'],True);self.assertEqual(path.read_text('utf-8'),before)

    def test_multifile_conflict_checks_all_targets_before_writing(self):
        for name in ('a.txt','b.txt'):(self.root/name).write_text('old\n')
        preview=self.project.preview(self.root,self.diff('a.txt','old\n','new\n')+self.diff('b.txt','old\n','new\n'))
        (self.root/'b.txt').write_text('user edited\n')
        with self.assertRaisesRegex(ValueError,'changed_since_preview'):self.project.change(preview['patch_id'])
        self.assertEqual((self.root/'a.txt').read_text(),'old\n')

    def test_creation_context_mismatch_and_traversal(self):
        text='--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,1 @@\n+created\n'
        preview=self.project.preview(self.root,text);self.project.change(preview['patch_id']);self.assertTrue((self.root/'new.txt').is_file())
        self.project.change(preview['patch_id'],True);self.assertFalse((self.root/'new.txt').exists())
        with self.assertRaises(ValueError):self.project.preview(self.root,text.replace('b/new.txt','b/../escape.txt'))
        (self.root/'file.txt').write_text('actual\n')
        with self.assertRaisesRegex(ValueError,'context_conflict'):self.project.preview(self.root,self.diff('file.txt','wrong\n','new\n'))

    def test_crlf_and_rollback_conflict(self):
        path=self.root/'file.txt';path.write_bytes(b'a\r\nb\r\n')
        preview=self.project.preview(self.root,self.diff('file.txt','a\nb\n','a\nc\n'))
        self.project.change(preview['patch_id']);self.assertEqual(path.read_bytes(),b'a\r\nc\r\n')
        path.write_bytes(b'changed\r\n')
        with self.assertRaisesRegex(ValueError,'rollback_file_changed'):self.project.change(preview['patch_id'],True)

    def test_git_checkpoint_preserves_working_tree_and_branch(self):
        def git(*args):
            return subprocess.run(['git','-C',str(self.root),*args],capture_output=True,text=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout.strip()
        git('init','-b','main');(self.root/'file.txt').write_text('old\n');git('add','file.txt')
        git('-c','user.name=Leva Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-m','fixture')
        (self.root/'file.txt').write_text('new\n');row=self.project.git(self.root,True)
        self.assertEqual(git('branch','--show-current'),'main');self.assertEqual((self.root/'file.txt').read_text(),'new\n')
        self.assertEqual(git('show',row['checkpoint_ref']+':file.txt'),'new')

    def test_context_only_agent_patch_and_explicit_user_protected_file(self):
        (self.root/'calc.py').write_text('def add(a,b):\n    return a-b\n')
        text='*** Begin Patch\n*** Update File: calc.py\n@@\n def add(a,b):\n-    return a-b\n+    return a+b\n*** End Patch\n'
        row=self.project.preview(self.root,text)
        with self.assertRaisesRegex(ValueError,'user_protected'):self.project.change(row['patch_id'],protected=['calc.py'])
        self.project.change(row['patch_id']);self.assertIn('a+b',(self.root/'calc.py').read_text())
        (self.root/'duplicate.txt').write_text('same\nsame\n')
        with self.assertRaisesRegex(ValueError,'not_unique'):self.project.preview(self.root,'--- a/duplicate.txt\n+++ b/duplicate.txt\n@@\n-same\n+new\n')


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.service=TerminalService(self.root/'history');self.addCleanup(self.service.stop_all)
    def finish(self,ident):
        for _ in range(10):
            result=self.service.poll(ident,wait=1)
            if result['status']!='running':return result
        self.fail('process did not finish')

    def test_streaming_python_exit_and_incremental_cursor(self):
        row=self.service.start('python','import time; print("first",flush=True); time.sleep(.3); print("second")',self.root)
        self.assertEqual(row['status'],'running');result=self.finish(row['process_id'])
        self.assertEqual(result['exit_code'],0);self.assertIn('first',result['output']);self.assertIn('second',result['output'])
        self.assertEqual(self.service.poll(row['process_id'],result['cursor'])['output'],'')

    def test_powershell_and_nonzero_exit(self):
        row=self.service.start('powershell','Write-Output "Leva PowerShell"; exit 7',self.root)
        result=self.finish(row['process_id']);self.assertEqual(result['status'],'failed');self.assertEqual(result['exit_code'],7)
        self.assertIn('Leva PowerShell',result['output'])

    def test_timeout_and_stop_only_owned_processes(self):
        row=self.service.start('python','import time; time.sleep(15)',self.root,1)
        self.assertEqual(self.finish(row['process_id'])['state'],'timed_out')
        row=self.service.start('python','import time; time.sleep(15)',self.root)
        self.assertEqual(self.service.stop(row['process_id'])['state'],'cancelled')
        with self.assertRaisesRegex(ValueError,'not_owned'):self.service.stop('unknown')

    def test_restart_exposes_interruption_without_replay(self):
        with self.service.connection() as db:db.execute("INSERT INTO processes VALUES('fixture','x','python','not executed','running',NULL,'0','','')")
        with patch('terminal_service.subprocess.Popen') as popen:
            reopened=TerminalService(self.root/'history');result=reopened.poll('fixture')
        popen.assert_not_called();self.assertEqual(result['state'],'interrupted')

    def test_stop_kills_owned_child_tree_and_preserves_an_unrelated_fixture(self):
        import psutil
        sibling=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            code='import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],creationflags=0x08000000); print(p.pid,flush=True); time.sleep(30)'
            row=self.service.start('python',code,self.root)
            output=''
            for _ in range(10):
                output=self.service.poll(row['process_id'],wait=.1)['output'].strip()
                if output:break
            self.assertTrue(output);child=int(output.splitlines()[0]);self.service.stop(row['process_id'])
            for _ in range(10):
                if not psutil.pid_exists(child):break
                time.sleep(.05)
            self.assertFalse(psutil.pid_exists(child));self.assertIsNone(sibling.poll())
        finally:sibling.terminate();sibling.wait(timeout=5)

    def test_python_command_identity_ignores_literal_quote_formatting(self):
        first=self.service.start('python','print("same")',self.root);a=self.finish(first['process_id'])
        second=self.service.start('python',"print('same')",self.root);b=self.finish(second['process_id'])
        self.assertEqual(a['command_id'],b['command_id'])


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.journal=TaskJournal(Path(self.temp.name)/'tasks.sqlite3')
    def test_question_without_any_tool_is_durable_and_fresh_requests_stay_fresh(self):
        local=Mock();local.propose_tool.return_value={'action':'ask_user','args':{'text':'Nama folder mana?','speech_text':'Nama folder mana?'}}
        with patch('task_journal.TaskJournal',return_value=self.journal):
            result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Buat catatan lalu uji proyek'}]},local,queue.Queue(),Mock())
        self.assertTrue(result['needs_input']);reopened=TaskJournal(self.journal.path)
        self.assertEqual(reopened.get(result['task_id'])['status'],'waiting_input')
        self.assertEqual(reopened.continuation('D:\\My Project')['goal'],'Buat catatan lalu uji proyek')
        self.assertIsNone(reopened.continuation('hai'));self.assertIsNone(reopened.continuation('buka Notepad'))

    def test_full_chrome_edge_goal_survives_profile_clarification(self):
        inventory={'profiles':[{'id':'chrome-stable:Profile 1','name':'Diska','channel':'stable','profile_directory':'Profile 1','user_data_root':'C:/fixture','directory_exists':True}]}
        with patch('desktop_service.inspect_profiles',return_value=inventory):desktop=DesktopService(Mock())
        desktop.browser.launch.return_value={'new_window_observed':True}
        goal='buka Chrome untuk ChatGPT dan buka Edge untuk EdLink'
        commands=queue.Queue()
        def emit(event):
            receipt=desktop.tools.execute(event['name'],event['args'],current[0])
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':receipt})
        first=Mock();first.propose_tool.return_value={'action':'open_browser','args':{'profile':'','url':'https://chatgpt.com/'}}
        current=[goal]
        with patch('task_journal.TaskJournal',return_value=self.journal):
            result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':goal}]},first,commands,emit)
            self.assertEqual(desktop.handle('Diska')['kind'],'chat')
            context=desktop.tools.context('Diska');self.assertEqual(context['continuation']['goal'],goal)
            second=Mock();second.propose_tool.side_effect=[{'action':'open_browser','args':{'profile':'Diska','url':'https://chatgpt.com/'}},{'action':'open_browser','args':{'profile':'','url':'https://edlink.id/','browser':'edge'}},{'action':'respond','args':{'text':'Kedua browser sudah menerima tujuan.','speech_text':'Kedua browser sudah menerima tujuan.'}}]
            current[0]='Diska'
            with patch.object(desktop,'open_edge',return_value={'status':'done','reply':'Edge observed'}) as edge:
                final=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Diska'}],'tool_context':context},second,commands,emit)
            edge.assert_called_once();desktop.browser.launch.assert_called_once()
        self.assertFalse(final['incomplete']);self.assertEqual(self.journal.get(result['task_id'])['status'],'continued')
        self.assertEqual(self.journal.get(final['task_id'])['parent'],result['task_id'])

    def test_running_terminal_receipts_need_final_poll(self):
        rows=[{'name':'terminal','args':{'action':'start'},'result':{'status':'running','process_id':'x'}}]
        self.assertTrue(unresolved_receipts(rows))
        rows.append({'name':'terminal','args':{'action':'poll','process_id':'x'},'result':{'status':'done','exit_code':0}})
        self.assertEqual(unresolved_receipts(rows),[])

    def test_empty_optional_numeric_arguments_use_host_defaults(self):
        tools=AssistantTools.__new__(AssistantTools);tools.desktop=Mock(preferences=None);tools._workspace_root=Path(self.temp.name);tools._terminal=Mock();tools._terminal.poll.return_value={'status':'done'}
        result=tools.execute('terminal',{'action':'poll','process_id':'fixture','cursor':'','wait':''},'uji proyek')
        tools._terminal.poll.assert_called_once_with('fixture','0','1');self.assertEqual(result['status'],'done')

    def test_terminal_failure_does_not_recover_from_unrelated_command(self):
        rows=[{'name':'terminal','args':{'action':'poll'},'result':{'status':'failed','retryable':True,'command_id':'a'}},
              {'name':'terminal','args':{'action':'poll'},'result':{'status':'done','command_id':'b'}}]
        self.assertTrue(unresolved_receipts(rows));rows[-1]['result']['command_id']='a';self.assertEqual(unresolved_receipts(rows),[])


class AdditionalRoadmapTests(unittest.TestCase):
    def test_ocr_path_does_not_load_caption_model(self):
        import feature_worker
        with patch('feature_worker.capture',return_value=(Path('fixture.png'),{'left':0,'top':0})),patch('feature_worker.ocr',return_value=[]),patch('feature_worker.caption',return_value='scene') as caption,patch('feature_worker.ctypes.windll.user32.GetForegroundWindow',return_value=123):
            result=feature_worker.describe({'monitor':'1'});caption.assert_not_called();self.assertEqual(result['caption'],'')
            self.assertEqual(feature_worker.describe({'monitor':'1','detail':'scene'})['caption'],'scene')

    def test_comfy_connector_is_read_only_and_returns_queue_counts(self):
        from local_connectors import comfyui
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{"queue_running":[[1,"private prompt"]],"queue_pending":[]}'
        opener=Mock();opener.open.return_value=response
        with patch('local_connectors.urllib.request.build_opener',return_value=opener):
            result=comfyui('queue');self.assertEqual(result['data'],{'running_count':1,'pending_count':0})
        self.assertNotIn('private prompt',json.dumps(result));self.assertTrue(opener.open.call_args.args[0].endswith('/queue'))
        with self.assertRaises(ValueError):comfyui('stats','http://192.168.1.1:8188')

    def test_textual_router_tool_json_is_validated_against_declared_tools(self):
        from router_provider import RouterClient
        from assistant_tools import selected_skills
        client=RouterClient('http://127.0.0.1:20128/v1','fixture');tools=[s.declaration() for s in selected_skills('jam berapa')]
        with patch.object(client,'completion',return_value={'content':'{"action":"get_time","args":{}}'}):self.assertEqual(client.propose_tool([],"",tools)['action'],'get_time')
        with patch.object(client,'completion',return_value={'content':'{"action":"terminal","args":{"action":"start"}}'}):
            from hybrid_engine import OnlineUnavailable
            with self.assertRaises(OnlineUnavailable):client.propose_tool([],"",tools)


if __name__=='__main__':unittest.main()
