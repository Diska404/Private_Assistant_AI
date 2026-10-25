import unittest
from unittest.mock import Mock,patch
from mic_recovery import MicRecovery,failure_details
import test_speech_pipeline as fixtures

class MicRecoveryTests(unittest.TestCase):
    def test_retries_are_delayed_bounded_and_claimed_once(self):
        r=MicRecovery()
        for i,delay in enumerate((5,15,45)):
            now=100*i;r.failed(now=now)
            self.assertFalse(r.claim(now=now+delay-1));self.assertTrue(r.claim(now=now+delay))
            self.assertFalse(r.claim(now=now+delay))
        r.failed(now=500);self.assertIsNone(r.retry_at);self.assertFalse(r.claim(now=1000))

    def test_fatal_configuration_does_not_retry_and_manual_reset_allows_fresh_attempt(self):
        r=MicRecovery();r.failed(retryable=False,now=0);self.assertIsNone(r.retry_at)
        r.reset();r.failed(now=0);self.assertEqual(r.remaining(now=1),4)

    def test_short_ready_period_does_not_reset_failures(self):
        r=MicRecovery();r.failed(now=0);r.ready(now=5);r.tick(now=20);self.assertEqual(r.failures,1)
        r.tick(now=65);self.assertEqual(r.failures,0)

    def test_windows_error_details_preserve_code_and_phase(self):
        e=OSError('paging file too small');e.winerror=1455
        result=failure_details(e,'asr_load')
        self.assertEqual(result['code'],'microphone_windows_memory');self.assertEqual(result['winerror'],1455)
        self.assertEqual(result['phase'],'asr_load');self.assertTrue(result['retryable'])
        self.assertFalse(failure_details(ValueError('speech_asr_assets_missing'))['retryable'])

    def window(self,paused=False):
        m=fixtures.SpeechPipelineTests().window('Dual GPU');m.closed=False;m.busy=False
        m.local_mic=Mock(active=False);m.local_mic_failed=True;m.mic_recovery=MicRecovery()
        m.desktop=Mock(paused=paused,sleeping=False)
        values={'always_listen':True,'asr_model':'qwen_asr_06b','asr_gpu':'auto','asr_language':'id','input_device_name':'Headset','input_hostapi':'MME'}
        m.preferences.get.side_effect=values.__getitem__;return m

    def test_due_retry_keeps_dual_request_and_configured_device(self):
        m=self.window();m.mic_recovery.failed(now=0)
        with patch('mic_recovery.time.monotonic',return_value=6):m.ensure_local_mic()
        self.assertFalse(m.local_mic_failed)
        self.assertEqual(m.local_mic.start.call_args.args,('Headset','MME','qwen_asr_06b','dual','id'))

    def test_retry_waits_during_pause_instead_of_starting_gpu_worker(self):
        m=self.window(paused=True);m.mic_recovery.failed(now=0)
        with patch('mic_recovery.time.monotonic',return_value=6):m.ensure_local_mic()
        m.local_mic.start.assert_not_called();self.assertTrue(m.local_mic_failed)

    def test_failed_worker_event_is_not_a_permanent_dead_end(self):
        m=self.window();m.add=Mock();m.local_mic.poll.return_value=[{'kind':'error','code':'local_microphone_OSError','retryable':True,'message':'Windows gagal'}]
        m.poll_local_mic();self.assertIsNotNone(m.mic_recovery.retry_at);self.assertEqual(m.local_notice,'Windows gagal')

if __name__=='__main__':unittest.main()
