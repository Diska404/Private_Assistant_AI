import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from comfy_service import ComfyService,ComfyClient,ComfyError,validate_graph,ui_workflow
from assistant_tools import AssistantTools,selected_skills
from receipt_state import unresolved_receipts
from task_journal import TaskJournal
from agent_runtime import run_agent
import queue
import subprocess
import sys
import threading
import time
from unittest.mock import patch


def schemas():
    return {
        'Source':{'input':{'required':{'name':[['one.safetensors','two.safetensors']], 'seed':['INT',{'min':0,'max':100,'control_after_generate':True}]}},'output':['IMAGE'],'output_node':False},
        'Sink':{'input':{'required':{'images':['IMAGE'],'filename_prefix':['STRING',{}]}},'output':[],'output_node':True},
        'Wrong':{'input':{'required':{}},'output':['MODEL']}}


def graph():
    return {'1':{'class_type':'Source','inputs':{'name':'one.safetensors','seed':1}},
            '2':{'class_type':'Sink','inputs':{'images':['1',0],'filename_prefix':'Leva/test'}}}


class ComfyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=ComfyService(storage=Path(self.temp.name));self.service.client=Mock(base='http://127.0.0.1:8188')
        self.service.client.schemas.return_value=schemas()

    def test_live_schema_validation_rejects_wrong_model_link_missing_input_and_cycles(self):
        g=graph();self.assertEqual(validate_graph(g,schemas())['links'],1)
        g['1']['inputs']['name']='invented.safetensors'
        with self.assertRaisesRegex(ComfyError,'not_available'):validate_graph(g,schemas())
        g=graph();g['1']['class_type']='Wrong';g['1']['inputs']={}
        with self.assertRaisesRegex(ComfyError,'link_type'):validate_graph(g,schemas())
        g=graph();del g['2']['inputs']['images']
        with self.assertRaisesRegex(ComfyError,'missing'):validate_graph(g,schemas())
        g=graph();g['2']['inputs']['images']=['99',0]
        with self.assertRaises(ComfyError):validate_graph(g,schemas())
        g=graph();g['1']['inputs']['name']=['2',0]
        with self.assertRaises(ComfyError):validate_graph(g,schemas())

    def test_dual_template_requires_visible_helper_gpu_and_uses_real_device_node(self):
        self.service.client.schemas.return_value={'LevaVAEDecodeDevice':{'input':{'required':{'device':[['cuda:0 | RTX 5070']]}}}}
        with self.assertRaisesRegex(ComfyError,'not_visible'):self.service.prepare('one.safetensors','test',vae_device='rtx4050')
        self.service.client.request.assert_not_called()
        self.service.client.schemas.return_value={'LevaVAEDecodeDevice':{'input':{'required':{'device':[['cuda:0 | RTX 5070','cuda:1 | RTX 4050 Laptop GPU']]}}}}
        self.service.prepare_graph=Mock(return_value={'status':'done'})
        self.service.prepare('one.safetensors','test',vae_device='rtx4050')
        actual=self.service.prepare_graph.call_args.args[0]
        node=next(row for row in actual.values() if row['class_type']=='LevaVAEDecodeDevice')
        self.assertEqual(node['inputs']['device'],'cuda:1 | RTX 4050 Laptop GPU')
        self.assertEqual(actual['7']['inputs']['images'],['6',0])

    def test_nonfinite_unknown_nodes_and_paid_api_nodes_rejected(self):
        g=graph();g['1']['inputs']['seed']=float('nan')
        with self.assertRaisesRegex(ComfyError,'numeric_type'):validate_graph(g,schemas())
        g=graph();g['1']['class_type']='NotInstalled'
        with self.assertRaises(ComfyError):validate_graph(g,schemas())
        s=schemas();s['Source']['api_node']=True
        with self.assertRaisesRegex(ComfyError,'paid_api'):validate_graph(graph(),s)

    def test_ui_export_preserves_seed_widget_and_bidirectional_links(self):
        ui=ui_workflow(graph(),schemas())
        self.assertEqual(ui['nodes'][0]['widgets_values'],['one.safetensors',1,'fixed'])
        self.assertEqual(ui['links'],[[1,1,0,2,0,'IMAGE']])
        self.assertEqual(ui['nodes'][0]['outputs'][0]['links'],[1]);self.assertEqual(ui['nodes'][1]['inputs'][0]['link'],1)

    def test_prepare_never_posts_and_reopened_connector_retains_graph_and_ids(self):
        result=self.service.prepare_graph(graph());ident=result['workflow_id']
        self.service.client.request.assert_not_called()
        self.assertEqual(result['workflow_state'],'prepared')
        reopened=ComfyService(storage=self.service.storage)
        self.assertEqual(reopened.describe(ident)['map'],result['map'])

    def test_publish_readback_and_lost_upload_response_recovery(self):
        result=self.service.prepare_graph(graph());ident=result['workflow_id'];folder=self.service.storage/ident
        workflow=json.loads((folder/'workflow.json').read_text('utf-8'))
        self.service.client.request.side_effect=[ComfyError('comfy_http_409:{}'),workflow]
        result=self.service.publish(ident);self.assertTrue(result['published'])
        self.assertIn('overwrite=false',self.service.client.request.call_args_list[0].args[0])
        self.service.client.request.reset_mock();self.service.publish(ident);self.service.client.request.assert_not_called()

    def test_changed_graph_or_ui_file_cannot_be_submitted(self):
        for filename in ('api.json','workflow.json'):
            ident=self.service.prepare_graph(graph())['workflow_id']
            with (self.service.storage/ident/filename).open('ab') as file:file.write(b' ')
            with self.assertRaisesRegex(ComfyError,'changed_after_prepare'):self.service.submit(ident)
        self.service.client.request.assert_not_called()

    def test_lost_submit_response_is_persisted_and_never_replayed_after_restart(self):
        ident=self.service.prepare_graph(graph())['workflow_id']
        self.service.client.request.side_effect=ComfyError('comfy_service_unreachable')
        with self.assertRaises(ComfyError):self.service.submit(ident)
        record=self.service._record(ident);self.assertTrue(record['submission_attempted']);prompt=record['prompt_id']
        reopened=ComfyService(storage=self.service.storage);reopened.client=Mock(base=self.service.client.base)
        reopened.client.request.side_effect=[{}, {'queue_running':[],'queue_pending':[[1,prompt]]}]
        self.assertEqual(reopened.submit(ident)['workflow_state'],'queued')
        self.assertTrue(all('/prompt'!=call.args[0] for call in reopened.client.request.call_args_list))

    def test_history_error_is_failure_and_success_is_verified_only_from_history(self):
        ident=self.service.prepare_graph(graph())['workflow_id'];record=self.service._record(ident);record['prompt_id']='fixture';self.service._save(record)
        self.service.client.request.return_value={'fixture':{'status':{'completed':False,'status_str':'error','messages':[['execution_error',{}]]},'outputs':{}}}
        self.assertEqual(self.service.poll(ident)['status'],'failed')
        self.service.client.request.return_value={'fixture':{'status':{'completed':True,'status_str':'success'},'outputs':{'2':{'images':[{'filename':'test.png','type':'output'}]}}}}
        result=self.service.poll(ident);self.assertTrue(result['task_verified']);self.assertEqual(result['outputs'][0]['filename'],'test.png')

    def test_loopback_only_and_cross_server_record_rejected(self):
        for url in ('https://example.com','http://192.168.1.2:8188','http://user:pass@127.0.0.1:8188','http://127.0.0.1:8188/path'):
            with self.assertRaises(ComfyError):ComfyClient(url)
        ident=self.service.prepare_graph(graph())['workflow_id']
        with self.assertRaisesRegex(ComfyError,'server_mismatch'):ComfyService(base='http://127.0.0.1:8199',storage=self.service.storage).describe(ident)

    def test_host_rejects_generation_when_only_map_requested_and_deferred_tasks(self):
        tools=AssistantTools.__new__(AssistantTools);tools._comfy=Mock();tools._resume_goal=''
        self.assertEqual(tools.execute('comfy_action',{'action':'submit','workflow_id':'123456abcdef'},'Buat workflow ComfyUI saja, jangan generate')['status'],'needs_input')
        tools._comfy.submit.assert_not_called()
        self.assertEqual(tools.execute('comfy_action',{'action':'prepare'},'ingatkan saya jam 19:00 lalu buat workflow ComfyUI')['status'],'needs_input')
        tools._comfy.prepare.assert_not_called()
        tools._comfy.submit.return_value={'status':'running'}
        self.assertEqual(tools.execute('comfy_action',{'action':'submit','workflow_id':'123456abcdef'},'Jalankan workflow ComfyUI ini')['status'],'running')

    def test_receipts_and_journal_retain_job_identity_and_do_not_resolve_other_job(self):
        rows=[{'name':'comfy_action','args':{'action':'submit'},'result':{'status':'running','workflow_id':'a'}}]
        rows.append({'name':'comfy_action','args':{'action':'poll','workflow_id':'b'},'result':{'status':'done'}})
        self.assertTrue(unresolved_receipts(rows));rows[-1]['args']['workflow_id']='a';self.assertEqual(unresolved_receipts(rows),[])
        journal=TaskJournal(Path(self.temp.name)/'tasks.sqlite3');task=journal.begin('ComfyUI workflow');journal.intent(task,1,'comfy_action',{'action':'submit'})
        journal.receipt(task,1,{'status':'running','workflow_id':'123456abcdef','prompt_id':'queue-id','workflow_state':'queued'})
        resumed=TaskJournal(journal.path).get(task);self.assertEqual(resumed['steps'][0]['result']['prompt_id'],'queue-id')
        self.assertIn('comfy_action',[s.name for s in selected_skills('Buka ComfyUI dan susun peta node')])

    def test_local_model_released_before_queue_and_not_reloaded_to_poll(self):
        model=Mock();model.propose_tool.return_value={'action':'comfy_action','args':{'action':'submit','workflow_id':'123456abcdef'}}
        commands=queue.Queue()
        def emit(event):
            model.close.assert_called_once()
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'running','workflow_id':'123456abcdef','prompt_id':'queue-id'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Jalankan workflow ComfyUI ini'}]},model,commands,emit)
        self.assertTrue(result['incomplete']);self.assertEqual(result['workflow_id'],'123456abcdef');self.assertEqual(model.propose_tool.call_count,1)

    def test_backend_ready_does_not_allow_model_to_claim_ui_opened(self):
        model=Mock();model.propose_tool.side_effect=[{'action':'comfy_action','args':{'action':'status'}},*[{'action':'respond','args':{'text':'ComfyUI sudah dibuka.','speech_text':''}} for _ in range(3)]]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'API siap'}})
        result=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Buka ComfyUI'}]},model,commands,emit)
        self.assertTrue(result['incomplete']);self.assertIn('UI',result['response'])

    def test_router_complex_tool_call_has_room_for_structured_arguments(self):
        from router_provider import RouterClient
        from hybrid_engine import OnlineUnavailable
        client=RouterClient('http://127.0.0.1:20128/v1','fixture')
        client.request=Mock(return_value={'choices':[{'finish_reason':'tool_calls','message':{}}]})
        client.completion([], '', [s.declaration() for s in selected_skills('ComfyUI workflow')])
        self.assertEqual(client.request.call_args.args[1]['max_tokens'],2048)
        client.completion([], '', [s.declaration() for s in selected_skills('jam berapa')])
        self.assertEqual(client.request.call_args.args[1]['max_tokens'],512)
        client.request.return_value={'choices':[{'finish_reason':'length','message':{}}]}
        with self.assertRaisesRegex(OnlineUnavailable,'router_output_limit'):client.completion([], '')

    def test_pause_cancels_gpu_probe_without_launching_a_late_server(self):
        service=ComfyService(storage=Path(self.temp.name)/'cancelled-start')
        service.client=Mock();service.client.request.side_effect=ComfyError('comfy_service_unreachable')
        service.installation=Mock(return_value=(Path(self.temp.name),Path(sys.executable),Path(self.temp.name)))
        real_popen=subprocess.Popen;result=[]
        def probe_only(command,**kwargs):
            return real_popen([sys.executable,'-u','-c','import time;time.sleep(20)'],**kwargs)
        with patch('comfy_service.subprocess.Popen',side_effect=probe_only) as spawn:
            worker=threading.Thread(target=lambda:result.append(service.start()));worker.start()
            until=time.monotonic()+5
            while service.probe_owner is None and time.monotonic()<until:time.sleep(.01)
            self.assertIsNotNone(service.probe_owner)
            start=time.monotonic();service.stop();self.assertLess(time.monotonic()-start,1)
            worker.join(5);self.assertFalse(worker.is_alive());self.assertEqual(result[0]['status'],'cancelled')
            self.assertIsNone(service.process);self.assertEqual(spawn.call_count,1)

    def test_generation_can_be_enabled_by_new_instruction_without_ignoring_new_negation(self):
        from assistant_tools import comfy_generation_requested
        for text in ('Buat workflow saja','jangan jalankan workflow ini','belum digenerate','tanpa render','tidak usah generate dulu'):
            self.assertFalse(comfy_generation_requested(text))
        tools=AssistantTools.__new__(AssistantTools);tools._comfy=Mock();tools._resume_goal='Buat workflow ComfyUI, jangan generate dulu';tools._continuation={'id':'fixture'}
        tools._comfy.submit.return_value={'status':'running'}
        self.assertEqual(tools.execute('comfy_action',{'action':'submit','workflow_id':'123456abcdef'},'sekarang generate workflow itu')['status'],'running')

    def test_cancel_during_schema_check_never_queues_generation(self):
        ident=self.service.prepare_graph(graph())['workflow_id']
        self.assertEqual(self.service.submit(ident,authorized=lambda:False)['status'],'cancelled')
        self.service.client.request.assert_not_called()
        self.assertFalse(self.service._record(ident).get('submission_attempted'))


if __name__=='__main__':unittest.main()
