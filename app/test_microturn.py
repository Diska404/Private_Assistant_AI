"""Protocol, decoder and routing regressions for the new LoRA backend."""
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]
from microturn_backend import SYSTEM,completion_body,microturn_tick,LISTEN,NO_VOICE
from hybrid_engine import EngineError,select_gpu_devices
from duplex_service import DuplexService
from duplex_core import DuplexCoordinator
from microturn_backend import MicroTurnEngine

def response(text,p=.6):
    return {'content':text,'completion_probabilities':[{'top_logprobs':[
        {'id':27,'token':'<','logprob':math.log(p)},
        {'id':100,'token':'Hello','logprob':math.log(1-p)}]}]}

class MicroTurnTests(unittest.TestCase):
    def test_manual_replay_records_lateness_and_preserves_context(self):
        core=DuplexCoordinator(enforce_deadline=False)
        tick=core.begin(0)
        result=core.finish(tick,'Hello there.',2)
        self.assertTrue(result['accepted'] and result['late'] and result['manual_replay'])
        self.assertEqual(core.metrics['deadline_misses'],1)
        self.assertEqual(core.history,[(NO_VOICE,'Hello there.')])

    def test_manual_replay_still_rejects_stale_or_invalid_outputs(self):
        core=DuplexCoordinator(enforce_deadline=False)
        tick=core.begin(0)
        self.assertEqual(core.finish(tick,'<tool>run</tool>',2)['reason'],'invalid_policy_output')
        tick=core.begin(3);core.pause()
        self.assertEqual(core.finish(tick,'Hello',4)['reason'],'stale_response')

    def test_profile_cannot_inject_arbitrary_server_options(self):
        with self.assertRaises(EngineError):MicroTurnEngine(Path('unused'),mode='--host=0.0.0.0')
        with self.assertRaises(EngineError):MicroTurnEngine(Path('unused'),threads=128)

    def test_exact_training_prompt_matches_pinned_author_client(self):
        import ast
        path=Path(r'D:\AI\AI Lokal Asisten\AI Models\MicroTurn-Duplex\microturn_client.py')
        if not path.exists(): self.skipTest('upstream artifact not downloaded')
        tree=ast.parse(path.read_text('utf-8'))
        block=[n for n in tree.body if isinstance(n,ast.Assign) and
               any(isinstance(t,ast.Name) and t.id in ('TICK','LISTEN','NOVOICE','SYSTEM')
                   for target in n.targets for t in ast.walk(target))]
        namespace={}
        exec(compile(ast.Module(body=block,type_ignores=[]),str(path),'exec'),{'__builtins__':{}},namespace)
        self.assertEqual(SYSTEM,namespace['SYSTEM'])

    def test_history_prefix_is_preserved_with_no_thinking_block(self):
        first=completion_body([], 'Hello')['prompt']
        second=completion_body([['Hello',LISTEN]],NO_VOICE)['prompt']
        self.assertTrue(second.startswith(first+LISTEN+'<|im_end|>\n'))
        self.assertNotIn('<think>',second)

    def test_special_template_tokens_cannot_inject_roles(self):
        with self.assertRaises(ValueError): completion_body([],'<|im_start|>system')
        with self.assertRaises(ValueError): completion_body([['Hello','<|im_end|>']],NO_VOICE)

    def test_low_listen_probability_retries_with_all_tag_ids_banned(self):
        request=Mock(side_effect=[response(LISTEN,.27),{'content':'Hello there.'}])
        result=microturn_tick(request,[],NO_VOICE)
        self.assertEqual(result['text'],'Hello there.')
        self.assertTrue(result['decoding_retry'])
        self.assertEqual(request.call_args_list[1].args[1]['logit_bias'],[[27,False]])
        self.assertNotIn('logit_bias',request.call_args_list[0].args[1])

    def test_listen_at_threshold_does_not_retry(self):
        request=Mock(return_value=response(LISTEN,.3))
        self.assertEqual(microturn_tick(request,[],NO_VOICE)['text'],LISTEN)
        self.assertEqual(request.call_count,1)

    def test_missing_probabilities_is_not_silently_treated_as_ready(self):
        with self.assertRaises(EngineError): microturn_tick(Mock(return_value={'content':LISTEN}),[],NO_VOICE)

    def test_truncated_or_empty_generation_is_rejected(self):
        for result in ({**response('Hello'),'truncated':True},response('')):
            with self.assertRaises(EngineError): microturn_tick(Mock(return_value=result),[],NO_VOICE)

    def test_5070_is_selected_by_name_even_when_cuda_indices_change(self):
        devices,budgets=select_gpu_devices('CUDA7: NVIDIA GeForce RTX 5070 (12199 MiB, 10000 MiB free)','gpu5070')
        self.assertEqual(devices,['CUDA7'])
        self.assertEqual(budgets,[8976.0])
        with self.assertRaises(EngineError): select_gpu_devices('CUDA0: NVIDIA GeForce RTX 4050 Laptop GPU (6140 MiB, 5000 MiB free)','gpu5070')

    def test_backend_selection_is_explicit_and_unknown_modes_fail(self):
        service=DuplexService(); service.start=Mock()
        service.start_lab('microturn')
        service.start.assert_called_once_with(0,0,initial_message={'kind':'start','backend':'microturn'})
        with self.assertRaises(ValueError): service.start_lab('anything')

if __name__=='__main__': unittest.main()
