import queue,tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from terminal_service import TerminalService
from agent_contract import website_creation,development_evidence,correction_goal
from agent_runtime import _run_agent
from assistant_tools import selected_skills,validate_call,AssistantTools
from project_workspace import ProjectWorkspace
from file_workspace import FileWorkspace

class VoiceAgentTests(unittest.TestCase):
    def test_original_airplane_request_loads_development_and_bypasses_frontend(self):
        from conversation_frontend import conversation_request
        from pipeline_routing import route_spec
        text='bisakah anda membuat sebuah model 3d pesawat yang bisa free cam dalam bentuk web lokal, leva boleh menggunakan hermes agent atau langsung memberikan hasilnya disini dalam bentuk link web local host nya'
        self.assertTrue(website_creation(text))
        self.assertIn('project_action',{s.name for s in selected_skills(text)})
        service=Mock()
        result=conversation_request(service,text,route_spec('Dual GPU'),None,'id',True)
        self.assertEqual(result['kind'],'delegate');self.assertTrue(result['frontend_bypassed']);service.ask.assert_not_called()

    def test_website_without_word_code_loads_development_tools(self):
        names={s.name for s in selected_skills('buatkan website model pesawat free cam')}
        self.assertTrue({'project_action','terminal','file_action'}<=names)
        self.assertNotIn('get_weather',names)
        self.assertFalse(website_creation('jelaskan cara buat website'))
        self.assertFalse(website_creation('jangan buat website sekarang'))
        self.assertFalse(website_creation('buat website, hanya kode di chat'))
        self.assertFalse(website_creation('buat website tanpa berkas'))

    def test_host_preflight_and_no_false_completion_after_capability_refusal(self):
        local=Mock();local.propose_tool.return_value={'action':'respond','args':{'text':'Saya berjalan di server dan tidak bisa membuat website.','speech_text':''}}
        commands=queue.Queue();calls=[]
        def emit(event):
            calls.append(event);commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','root':'C:/fixture','reply':'Workspace aktif.'}})
        result=_run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'buatkan website'}]},local,commands,emit)
        self.assertEqual(calls[0]['name'],'project_action');self.assertEqual(calls[0]['args']['action'],'info')
        self.assertTrue(result['incomplete']);self.assertNotIn('berjalan di server',result['response'])

    def test_read_before_write_cannot_verify_created_file(self):
        read={'name':'project_action','args':{'action':'read','path':'index.html'},'result':{'status':'done','root':'C:/p','path':'index.html'}}
        write={'name':'project_action','args':{'action':'apply'},'result':{'status':'done','root':'C:/p','paths':['index.html']}}
        self.assertEqual(development_evidence([read,write]),(True,False))
        self.assertEqual(development_evidence([write,read]),(True,True))
        unrelated={**read,'result':{**read['result'],'root':'C:/other'}}
        self.assertEqual(development_evidence([write,unrelated]),(True,False))

    def test_patch_limit_matches_host_and_other_tool_limits_stay_bounded(self):
        validate_call('project_action',{'action':'preview','patch':'x'*12000})
        with self.assertRaises(ValueError):validate_call('project_action',{'action':'preview','patch':'x'*12001})
        with self.assertRaises(ValueError):validate_call('terminal',{'action':'start','code':'x'*3001})

    def test_correction_keeps_original_and_new_negation_verbatim(self):
        old='buatkan website iPhone';new='eh bukan iPhone, buatkan UI pesawat'
        combined=correction_goal(new,old)
        self.assertIn(old,combined);self.assertTrue(combined.endswith(new))
        self.assertEqual(correction_goal('jam berapa',old),'jam berapa')
        self.assertEqual(correction_goal('eh bukan itu, batalkan saja',old),'eh bukan itu, batalkan saja')

    def test_child_workspace_select_needs_no_redundant_path_question(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project';root.mkdir();child=root/'pesawat-3d';child.mkdir()
            outside=Path(folder)/'other';outside.mkdir()
            tools=AssistantTools.__new__(AssistantTools);tools.desktop=Mock(preferences=None)
            tools._workspace_root=root;tools.projects=ProjectWorkspace(Path(folder)/'history');tools.files=FileWorkspace(Path(folder)/'files')
            tools._resume_goal='';tools._continuation=None
            result=tools.execute('project_action',{'action':'select','root':str(child)},'buatkan web pesawat')
            self.assertEqual(result['status'],'done');self.assertEqual(tools.project_root(),child)
            result=tools.execute('project_action',{'action':'select','root':str(outside)},'buatkan web pesawat')
            self.assertEqual(result['status'],'needs_input')

    def test_static_preview_http_matches_file_and_stops_owned_server(self):
        import urllib.request
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);content=b'<!doctype html><title>Leva preview</title><h1>Verified</h1>'
            (root/'index.html').write_bytes(content);service=TerminalService(root/'history')
            try:
                result=service.serve(root)
                self.assertEqual(result['status'],'done');self.assertEqual(result['http_status'],200)
                self.assertEqual(result['lifetime_seconds'],1800)
                with urllib.request.urlopen(result['url'],timeout=3) as response:self.assertEqual(response.read(),content)
                self.assertEqual(service.poll(result['process_id'])['status'],'running')
                stopped=service.stop(result['process_id']);self.assertEqual(stopped['status'],'cancelled')
                with self.assertRaises(OSError):urllib.request.urlopen(result['url'],timeout=1)
            finally:service.stop_all()

    def test_static_preview_rejects_missing_entry_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            service=TerminalService(Path(folder)/'history')
            with self.assertRaisesRegex(ValueError,'preview_index_html_missing'):service.serve(folder)
            self.assertEqual(service.recent()['processes'],[])

    def test_failed_write_retries_after_parent_creation_and_clears_old_failure(self):
        self.run_write_recovery(True)

    def test_successful_write_is_not_repeated_after_folder_observation(self):
        self.run_write_recovery(False)

    def test_large_tool_call_budget_has_time_to_finish_without_changing_chat_timeout(self):
        from hybrid_engine import LocalEngine,EngineError
        local=LocalEngine(Path('server'),Path('model'),Path('runtime'),max_output_tokens=2048)
        local.start=Mock();local.request=Mock(return_value={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'function':{'name':'respond','arguments':{'text':'ok','speech_text':''}}}]}}]})
        self.assertEqual(local.propose_tool([],[])['action'],'respond')
        self.assertGreaterEqual(local.request.call_args.kwargs['timeout'],180)
        local.max_output_tokens=512;local.propose_tool([],[])
        self.assertEqual(local.request.call_args.kwargs['timeout'],90)
        local.request.side_effect=TimeoutError()
        with self.assertRaisesRegex(EngineError,'native_tool_timeout'):local.propose_tool([],[])

    def run_write_recovery(self,first_fails):
        write={'action':'file_action','args':{'action':'write','path':'C:/fixture/web/index.html','text':'<html>ok</html>'}}
        local=Mock();local.propose_tool.side_effect=[write,
            {'action':'file_action','args':{'action':'mkdir','path':'C:/fixture/web'}},write,
            {'action':'file_action','args':{'action':'read','path':'C:/fixture/web/index.html'}},
            {'action':'respond','args':{'text':'Berkas dibuat dan dibaca.','speech_text':''}}]
        commands=queue.Queue();calls=[];writes=[]
        def emit(event):
            calls.append(event);args=event['args'];result={'status':'done','reply':'ok','path':args.get('path','')}
            if args['action']=='write':
                writes.append(args)
                if first_fails and len(writes)==1:result={'status':'failed','reply':'folder belum diamati','code':'file_path_not_observed','retryable':True}
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        result=_run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'buatkan website'}]},local,commands,emit)
        self.assertEqual(len(writes),2 if first_fails else 1)
        self.assertEqual(result['response'],'Berkas dibuat dan dibaca.')
        self.assertFalse(result.get('incomplete'))

if __name__=='__main__':unittest.main()
