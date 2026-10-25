import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock,patch

from assistant_tools import AssistantTools,image_open_only,selected_skills
from agent_runtime import run_agent
from comfy_service import ComfyError
from fooocus_service import FooocusService
from image_jobs import ImageJobs
from task_journal import TaskJournal


class ImageSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
    def tools(self):
        tools=AssistantTools.__new__(AssistantTools);tools._resume_goal='';tools._continuation=None;tools._image_submissions={}
        tools._fooocus=Mock();tools._fooocus.last_submission_id=None;tools._fooocus.status.return_value={'status':'done'}
        return tools
    def test_open_only_asks_followup_and_new_reply_resumes_original_task(self):
        journal=TaskJournal(self.folder/'tasks.sqlite3');commands=queue.Queue();model=Mock()
        model.propose_tool.return_value={'action':'comfy_action','args':{'action':'open'}}
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'ComfyUI terbuka.'}})
        with patch('task_journal.TaskJournal',return_value=journal):result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Leva buka comfyui'}]},model,commands,emit)
        self.assertTrue(result['needs_input']);self.assertIn('membuat baru',result['response']);self.assertEqual(model.propose_tool.call_count,1)
        continued=journal.continuation('buat baru saja, gunakan checkpoint Juggernaut')
        self.assertEqual(continued['id'],result['task_id']);self.assertEqual(continued['goal'],'Leva buka comfyui')
        self.assertIsNone(journal.continuation('buat laporan matematika diskrit'))
    def test_image_open_intent_does_not_capture_direct_generation(self):
        self.assertTrue(image_open_only('leva buka foookus dulu'))
        self.assertFalse(image_open_only('buka Fooocus lalu generate gambar apa saja'))
        self.assertIn('image_action',[s.name for s in selected_skills('buatkan gambar dengan foookus lalu generate')])
    def test_direct_generation_uses_tool_without_requesting_extra_permission(self):
        tools=self.tools();tools._fooocus.generate.return_value={'status':'running','job_id':'123456abcdef','workflow_id':'123456abcdef'}
        monitor=Mock()
        with patch('image_jobs.ImageJobs',return_value=monitor):
            result=tools.execute('image_action',{'engine':'fooocus','action':'generate'},'Buatkan gambar dengan foookus, pilih salah satu model lokal dan langsung generate saja')
        self.assertEqual(result['status'],'running');tools._fooocus.generate.assert_called_once();monitor.track.assert_called_once_with('fooocus','123456abcdef')
    def test_opening_does_not_authorize_generation_or_stopping_server(self):
        tools=self.tools()
        self.assertEqual(tools.execute('image_action',{'engine':'fooocus','action':'generate'},'buka Fooocus')['status'],'needs_input')
        self.assertEqual(tools.execute('image_action',{'engine':'fooocus','action':'stop_server'},'buatkan gambar dengan Fooocus')['status'],'needs_input')
        tools._fooocus.generate.assert_not_called();tools._fooocus.stop.assert_not_called()
    def test_repeat_generation_in_same_request_observes_existing_job(self):
        tools=self.tools();tools._fooocus.generate.return_value={'status':'running','job_id':'123456abcdef'};tools._fooocus.poll.return_value={'status':'running'}
        with patch('image_jobs.ImageJobs'):
            tools.execute('image_action',{'engine':'fooocus','action':'generate'},'generate gambar dengan Fooocus')
            tools.execute('image_action',{'engine':'fooocus','action':'generate','positive':'different prompt'},'generate gambar dengan Fooocus')
        tools._fooocus.generate.assert_called_once();tools._fooocus.poll.assert_called_once_with('123456abcdef')
    def test_lost_response_retains_job_and_blocks_duplicate_submission(self):
        tools=self.tools()
        def lost(*args,**kwargs):tools._fooocus.last_submission_id='123456abcdef';raise ComfyError('comfy_service_unreachable')
        tools._fooocus.generate.side_effect=lost;tools._fooocus.poll.return_value={'status':'running'}
        with patch('image_jobs.ImageJobs'):
            result=tools.execute('image_action',{'engine':'fooocus','action':'generate'},'generate gambar dengan Fooocus')
            self.assertEqual(result['status'],'unverified');self.assertEqual(result['job_id'],'123456abcdef')
            tools.execute('image_action',{'engine':'fooocus','action':'generate'},'generate gambar dengan Fooocus')
        self.assertEqual(tools._fooocus.generate.call_count,1)
    def test_local_generation_releases_model_and_returns_background_job(self):
        model=Mock();model.propose_tool.return_value={'action':'image_action','args':{'engine':'fooocus','action':'generate'}};commands=queue.Queue()
        def emit(event):
            model.close.assert_called_once();commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'running','job_id':'123456abcdef'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'generate gambar dengan Fooocus'}]},model,commands,emit)
        self.assertTrue(result['image_job_active']);self.assertEqual(model.propose_tool.call_count,1)
    def test_model_cannot_claim_generation_without_execution(self):
        model=Mock();model.propose_tool.return_value={'action':'respond','args':{'text':'Gambar selesai.','speech_text':''}}
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'generate gambar dengan Fooocus'}]},model,queue.Queue(),Mock())
        self.assertTrue(result['incomplete']);self.assertIn('belum',result['response'])
    def test_cold_start_can_continue_to_generate_without_duplicate_action_block(self):
        model=Mock();model.propose_tool.side_effect=[{'action':'image_action','args':{'engine':'fooocus','action':action}} for action in ('generate','status','generate')]
        commands=queue.Queue();results=iter([{'status':'running','reply':'Server sedang mulai'},{'status':'done','reply':'Siap'},{'status':'running','job_id':'123456abcdef'}])
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':next(results)})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Buatkan gambar dengan Fooocus, pilih bebas dan generate'}]},model,commands,emit)
        self.assertTrue(result['image_job_active']);self.assertEqual(model.propose_tool.call_count,3)
    def test_monitor_persists_across_restart_and_never_submits(self):
        monitor=ImageJobs(self.folder/'jobs.sqlite3');monitor.track('fooocus','123456abcdef');tools=self.tools()
        tools._fooocus.poll.return_value={'status':'running'};self.assertEqual(monitor.observe(tools),[])
        tools._fooocus.poll.return_value={'status':'done','reply':'Selesai','outputs':[{'path':'example.png'}]}
        reopened=ImageJobs(monitor.path);self.assertEqual(len(reopened.observe(tools)),1)
        reopened.acknowledge('fooocus','123456abcdef');self.assertEqual(reopened.observe(tools),[])
        tools._fooocus.generate.assert_not_called()
    def test_offline_server_does_not_trigger_restart_or_replay(self):
        monitor=ImageJobs(self.folder/'jobs.sqlite3');monitor.track('fooocus','123456abcdef');tools=self.tools();tools._fooocus.poll.side_effect=ComfyError('offline')
        self.assertEqual(monitor.observe(tools),[]);self.assertTrue(monitor.pending());tools._fooocus.start.assert_not_called();tools._fooocus.generate.assert_not_called()
    def test_gui_delivers_completion_once_without_loading_a_model(self):
        from gui import LevaWindow
        window=LevaWindow.__new__(LevaWindow);window.closed=False;window.busy=False;window.desktop=Mock(paused=False,sleeping=False);window.root=Mock()
        window.image_jobs=ImageJobs(self.folder/'jobs.sqlite3');window.image_jobs.track('fooocus','123456abcdef')
        window.image_events=queue.Queue();window.image_events.put({'engine':'fooocus','id':'123456abcdef','result':{'status':'done','reply':'Gambar selesai','outputs':[]}})
        window.image_job_busy=False;window.add=Mock();window.add_image_files=Mock()
        window.poll_image_jobs();window.poll_image_jobs();window.add.assert_called_once();self.assertEqual(window.image_jobs.pending(),[])


class FooocusCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'Fooocus/models/checkpoints').mkdir(parents=True);(self.root/'Fooocus/webui.py').write_text('fixture',encoding='utf-8');(self.root/'python_embeded').mkdir();(self.root/'python_embeded/python.exe').touch()
        self.service=FooocusService(self.root,storage=self.root/'state')
    def weight(self,path,family='sdxl'):
        path.parent.mkdir(parents=True,exist_ok=True);header=json.dumps({'conditioner.embedders.1.test':{}} if family=='sdxl' else {'other.architecture':{}}).encode();path.write_bytes(len(header).to_bytes(8,'little')+header)
    def test_catalog_reads_headers_and_keeps_invalid_original_config(self):
        path=self.root/'Fooocus/config.txt';path.write_text('{broken',encoding='utf-8');self.weight(self.root/'Fooocus/models/checkpoints/model.safetensors')
        result=self.service.catalog(query='model.safetensors');self.assertEqual(result['models'][0]['family'],'sdxl');self.assertIn('tidak valid',result['warning']);self.assertEqual(path.read_text('utf-8'),'{broken')
    def test_extra_roots_detect_ambiguous_model_names(self):
        self.weight(self.root/'Fooocus/models/checkpoints/same.safetensors');self.weight(self.root/'extra/same.safetensors')
        self.service.extra_roots=[self.root/'extra'];rows=self.service.catalog(query='same.safetensors')['models'];self.assertTrue(rows[0]['ambiguous'])
    def test_gpu_selection_does_not_pick_unsupported_larger_gpu(self):
        device=self.service.pick_gpu([{'index':0,'name':'5070','total':12,'compatible':False},{'index':1,'name':'4050','total':6,'compatible':True}]);self.assertEqual(device['name'],'4050')
    def test_unknown_architecture_is_not_used_for_fooocus(self):
        self.weight(self.root/'Fooocus/models/checkpoints/unknown.safetensors','other')
        with self.assertRaisesRegex(ComfyError,'missing_or_ambiguous'):self.service.generate('unknown')
    def test_generation_with_delegated_details_selects_verified_model_and_prompt(self):
        self.weight(self.root/'Fooocus/models/checkpoints/juggernautXL_v8.safetensors');self.service.client=Mock(base='http://127.0.0.1:7866');self.service.client.request.return_value={'state':'queued'}
        result=self.service.generate();self.assertEqual(result['model'],'juggernautXL_v8.safetensors');self.assertTrue(result['positive'])
        self.assertNotIn('token',json.dumps(result).lower());self.assertTrue(self.service._record(result['job_id'])['submission_attempted'])
    def test_fooocus_session_does_not_rewrite_original_configuration(self):
        self.weight(self.root/'Fooocus/models/checkpoints/juggernautXL_v8.safetensors');original=self.root/'Fooocus/config.txt';original.write_text('{broken',encoding='utf-8')
        with patch('fooocus_service.FooocusService.catalog',return_value={'models':[{'name':'juggernautXL_v8.safetensors','family':'sdxl','ambiguous':False}]}):path=self.service.session_config()
        config=json.loads(path.read_text('utf-8'));self.assertEqual(config['checkpoint_downloads'],{});self.assertEqual(original.read_text('utf-8'),'{broken')


if __name__=='__main__':unittest.main()
