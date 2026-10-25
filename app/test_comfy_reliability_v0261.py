import json,queue,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from assistant_tools import comfy_generation_requested,AssistantTools
from comfy_service import ComfyService,ComfyError
from agent_runtime import _run_agent
from hybrid_engine import LocalEngine,EngineError
import test_mic_recovery as micfixtures


class ComfyReliabilityTests(unittest.TestCase):
    def test_generation_typos_and_template_intention(self):
        for value in ('bisakah leva buat 1 generat gambar dengan template bebas','langsung mengenerate gambar','buat template lalu langsung generate','buat gambar dengan ComfyUI'):
            self.assertTrue(comfy_generation_requested(value),value)
        for value in ('buka comfyui dan buatkan template gambar untuk mengenerate gambar','buat template saja','jangan generat gambar','belum digenerate','buat template untuk menghasilkan gambar'):
            self.assertFalse(comfy_generation_requested(value),value)
    def test_previous_image_engine_is_preserved(self):
        tools=AssistantTools.__new__(AssistantTools);tools._resume_goal='';tools.image_engine_hint='comfyui';tools._fooocus=Mock()
        result=tools.execute('image_action',{'engine':'fooocus','action':'generate'},'buat 1 generat gambar dengan template bebas')
        self.assertEqual(result['code'],'image_engine_context_mismatch');tools._fooocus.generate.assert_not_called()
    def test_flux_vae_cannot_enter_four_channel_template(self):
        with tempfile.TemporaryDirectory() as folder:
            service=ComfyService(storage=folder)
            with self.assertRaisesRegex(ComfyError,'incompatible_flux'):
                service.check_vae({'1':{'class_type':'EmptyLatentImage'},'2':{'class_type':'VAELoader','inputs':{'vae_name':'ae.safetensors'}}})
            service.check_vae({'1':{'class_type':'EmptyLatentImage'},'2':{'class_type':'CheckpointLoaderSimple'}})
    def test_external_vae_is_not_added_by_model_without_request(self):
        tools=AssistantTools.__new__(AssistantTools);tools._resume_goal='';tools._comfy=Mock()
        result=tools.execute('comfy_action',{'action':'prepare','checkpoint':'sdxl.safetensors','vae':'other.safetensors'},'buat template comfyui')
        self.assertEqual(result['status'],'failed');tools._comfy.prepare.assert_not_called()
    def test_tool_context_uses_token_count_and_preserves_goal_and_latest_evidence(self):
        engine=LocalEngine.__new__(LocalEngine);engine.max_output_tokens=512;engine.context_size=2000;engine.system='system';engine.thinking_budget=0
        observed=[]
        def request(path,body,timeout=10):
            if path=='/apply-template':observed.append(body['messages']);return {'prompt':str(len(body['messages']))}
            return {'tokens':[0]*int(body['content'])*400}
        engine.request=request
        goal={'role':'user','content':'Tujuan aktif pengguna, pertahankan sampai selesai: buat template'}
        latest={'role':'user','content':'Hasil host: workflow tersimpan abc123'}
        result=engine.fit_tool_messages([{'role':'user','content':'old history'},goal,{'role':'assistant','content':'older tool selection'},latest],[])
        self.assertIn(goal,result);self.assertIn(latest,result);self.assertNotIn('old history',[m['content'] for m in result]);self.assertLessEqual(engine.last_tool_budget['prompt_tokens'],1488)
    def test_transport_failure_after_publish_keeps_verified_workflow_receipt(self):
        model=Mock();model.propose_tool.side_effect=[{'action':'comfy_action','args':{'action':'publish','workflow_id':'123456abcdef'}},EngineError('native_tool_context_overflow')]
        commands=queue.Queue()
        def emit(event):commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':{'status':'done','reply':'Workflow tersimpan dan terbaca kembali. Belum generate.','workflow_id':'123456abcdef'}})
        result=_run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'simpan template ComfyUI'}]},model,commands,emit)
        self.assertTrue(result['incomplete']);self.assertIn('123456abcdef',result['response']);self.assertEqual(len(result['tool_receipts']),1)
    def test_idle_mic_does_not_bootstrap_during_agent_or_image_work(self):
        for field in ('busy','_image_gpu_active'):
            m=micfixtures.MicRecoveryTests().window();m.local_mic_failed=False;setattr(m,field,True)
            m.ensure_local_mic();m.local_mic.start.assert_not_called()
    def test_prepare_can_retry_after_server_readiness_but_never_repeats_success(self):
        model=Mock();args={'action':'prepare','checkpoint':'test.safetensors','positive':'lake'}
        model.propose_tool.side_effect=[{'action':'comfy_action','args':args},{'action':'comfy_action','args':{'action':'status'}},{'action':'comfy_action','args':args},{'action':'respond','args':{'text':'Template tersimpan.','speech_text':''}}]
        commands=queue.Queue();answers=iter([{'status':'failed','code':'comfy_service_unreachable','retryable':True,'reply':'Belum siap'},{'status':'done','reply':'API siap'},{'status':'done','workflow_id':'123456abcdef','reply':'Template tersimpan.'}]);calls=[]
        def emit(event):
            calls.append(event['args']);commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':next(answers)})
        result=_run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'buat template ComfyUI, jangan generate'}]},model,commands,emit)
        self.assertFalse(result.get('incomplete',False));self.assertEqual(sum(r['action']=='prepare' for r in calls),2)


if __name__=='__main__':unittest.main()
