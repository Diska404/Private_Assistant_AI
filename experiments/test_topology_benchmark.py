import unittest
from unittest.mock import patch
import topology_benchmark as bench

class BenchmarkEvidenceTests(unittest.TestCase):
    def test_coordinators_cannot_measure_gpu_concurrently(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'gpu.lock';first=bench.acquire_gpu_lock(path)
            try:
                with self.assertRaises(RuntimeError):bench.acquire_gpu_lock(path)
            finally:first.close()
            again=bench.acquire_gpu_lock(path);again.close()

    def test_rpc_evidence_requires_each_endpoint_and_excludes_native_cuda(self):
        log='0.01 I load_tensors: CPU_Mapped model buffer size = 10.0 MiB\n0.01 I load_tensors: RPC0[127.0.0.1:4001] model buffer size = 100.0 MiB\n0.01 I load_tensors: RPC0[127.0.0.1:4002] model buffer size = 200.0 MiB\n'
        buffers=bench.parse_buffers(log)
        self.assertTrue(bench.rpc_placement_proven(buffers,['127.0.0.1:4001','127.0.0.1:4002']))
        self.assertFalse(bench.rpc_placement_proven(buffers,['127.0.0.1:4001','127.0.0.1:4003']))
        self.assertFalse(bench.rpc_placement_proven(buffers+[{'device':'CUDA0','mib':3}],['127.0.0.1:4001']))

    def test_gpu_hidden_with_minus_one_not_empty_windows_environment(self):
        self.assertEqual(bench.environment([])['CUDA_VISIBLE_DEVICES'],'-1')

    def test_rpc_registered_before_list_devices_early_exit(self):
        with patch.object(bench.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='  RPC0: remote (6140 MiB, 4000 MiB free)';run.return_value.stderr=''
            rows,_=bench.discover(bench.environment([]),'127.0.0.1:4001')
            args=run.call_args.args[0]
            self.assertLess(args.index('--rpc'),args.index('--list-devices'))
            self.assertEqual(rows[0]['device'],'RPC0')

    def test_exact_checks_do_not_accept_invalid_json_arithmetic_or_partial_match(self):
        self.assertFalse(bench.exact_check('{"hasil":17*24}',{'hasil':408}))
        self.assertFalse(bench.exact_check('{"hasil":408,"extra":1}',{'hasil':408}))
        self.assertTrue(bench.exact_check('```json\n{"hasil":408}\n```',{'hasil':408}))

    def test_summary_counts_failed_and_incomplete_and_ignores_unscored_prose(self):
        row={'requests':[{'status':'ok','ttft_ms':20,'total_ms':40,'exact_pass':True,'timings':{'predicted_per_second':10}},
                         {'status':'incomplete','exact_pass':False},{'status':'error','exact_pass':False},
                         {'status':'ok','ttft_ms':40,'total_ms':80,'exact_pass':None,'timings':{}}],
             'batch_makespan_ms':[200,400]}
        result=bench.summarize(row)
        self.assertEqual((result['n'],result['complete'],result['exact_checks_passed'],result['exact_checks_total']),(4,2,1,3))
        self.assertEqual(result['ttft_p50_ms'],30);self.assertEqual(result['batch_makespan_p50_ms'],300)

if __name__=='__main__':unittest.main()
