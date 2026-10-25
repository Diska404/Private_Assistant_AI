import base64
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import wave
from unittest.mock import Mock,patch
from asr_lab_metrics import score,summary,CONTEXT
from asr_lab import Store,Lab,server

def wav_bytes():
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(struct.pack('<h',300)*8000)
    return out.getvalue()

class ASRLabTests(unittest.TestCase):
    def test_embedded_microphone_worker_imports_before_any_device_is_opened(self):
        from speech_asr import ASR_PYTHON
        import subprocess
        import os
        if not ASR_PYTHON.is_file():self.skipTest('runtime ASR tidak terpasang')
        result=subprocess.run([str(ASR_PYTHON),'-B','-u',str(Path(__file__).with_name('local_mic_worker.py'))],
            input=json.dumps({'asr_model':'__invalid_model_for_bootstrap_probe__'}),capture_output=True,text=True,timeout=20,creationflags=0x08000000,
            env={**os.environ,'LEVA_MIC_DIAGNOSTICS':'0'})
        self.assertEqual(result.returncode,0,result.stderr)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(any(e.get('code')=='speech_asr_assets_missing' for e in events))
        self.assertFalse(any(e.get('microphone_open') is True for e in events))
    def test_alignment_distinguishes_error_types_and_wer_can_exceed_one(self):
        m=score('buka chrome diska','bukakan chrome lalu youtube')
        self.assertEqual(m['word_errors'],3);self.assertEqual(m['substitution'],2);self.assertEqual(m['insertion'],1)
        self.assertGreater(score('hai','satu dua tiga empat')['wer'],1)
        self.assertEqual(score('Halo, Leva!','halo leva')['wer'],0)
    def test_empty_reference_is_not_zero_wer_and_flags_false_speech(self):
        self.assertIsNone(score('','hai')['wer']);self.assertTrue(score('','hai')['false_speech'])
        self.assertFalse(score('','')['false_speech'])
    def test_slots_are_explicit_and_manual_reference_changes_remove_unspoken_expectations(self):
        critical=[{'name':'delay','variants':['2 menit','dua menit']},{'name':'larangan','variants':['jangan']}]
        m=score('dua menit jangan','2 menit',critical)
        self.assertEqual(m['critical_missing'],1);self.assertTrue(m['critical'][0]['present'])
        self.assertEqual(score('dua menit','dua menit',critical)['critical_missing'],0)
    def test_aggregate_separates_cold_warm_and_requires_confirmed_reference(self):
        rows=[]
        for confirmed,warm,errors in [(True,False,0),(False,False,3),(True,True,2)]:
            rows.append({'status':'done','reference_confirmed':confirmed,'result':{'gpu_name':'4050','model':'qwen','model_reused':warm,'asr_ms':1000},
                'metrics':{'reference_words':4,'word_errors':errors,'critical_missing':0,'false_speech':False},'condition':'quiet','context':CONTEXT})
        groups=summary(rows);self.assertEqual(len(groups),2)
        self.assertEqual(groups[0]['wer_micro'],0);self.assertEqual(groups[1]['wer_micro'],.5)
    def test_review_is_persistent_and_preserves_audit(self):
        with tempfile.TemporaryDirectory() as tmp, Store(tmp) as store:
            store.save({'id':'a','status':'done','reference':'buka chrome','critical':[],'result':{'text':'buka krom'}})
            row=store.review('a',{'reference':'buka krom','reference_confirmed':True,'review':'correct','notes':'ucapan memang krom'})
            self.assertEqual(row['metrics']['wer'],0)
            with Store(tmp) as reopened:self.assertTrue(reopened.get('a')['reference_confirmed'])
            self.assertEqual(store.db.execute('SELECT count(*) FROM reviews').fetchone()[0],1)
            store.save({'id':'b','status':'running'});store.recover();self.assertEqual(store.get('b')['status'],'interrupted')
    def test_replay_preserves_audio_and_reference_never_becomes_asr_context(self):
        with tempfile.TemporaryDirectory() as tmp, Store(tmp) as store:
            worker=Mock(process=None);worker.run.return_value={'ok':True,'text':'buka chrome','asr_ms':1,'model':'qwen','gpu_name':'4050','model_reused':False}
            lab=Lab(store,worker)
            fake=Mock();fake.finish.return_value={'samples':[]}
            with patch('asr_lab.Monitor',return_value=fake):
                first=lab.start({'audio':base64.b64encode(wav_bytes()).decode(),'prompt_id':'custom','reference':'RAHASIA REFERENSI','reference_confirmed':True})
                for _ in range(100):
                    if not lab.active:break
                    time.sleep(.01)
                second=lab.start({'replay_id':first['id'],'gpu':'rtx5070','prompt_id':'custom','reference':'JANGAN GANTI'})
                for _ in range(100):
                    if not lab.active:break
                    time.sleep(.01)
            self.assertEqual(first['audio_sha256'],second['audio_sha256']);self.assertEqual(second['reference'],'RAHASIA REFERENSI')
            self.assertNotIn('RAHASIA',worker.run.call_args.args[0]['context']);self.assertEqual(second['gpu'],'rtx5070')
    def test_invalid_audio_releases_lab_lock(self):
        with tempfile.TemporaryDirectory() as tmp, Store(tmp) as store:
            lab=Lab(store,Mock())
            with self.assertRaises(Exception):lab.start({'audio':'not base64'})
            self.assertTrue(lab.lock.acquire(blocking=False));lab.lock.release()
    def test_http_requires_local_token_and_exports_are_readable(self):
        with tempfile.TemporaryDirectory() as tmp, Store(tmp) as store:
            lab=Lab(store,Mock(process=None));http=server(lab,0)
            # The bound port is only known after construction in tests.
            # Production uses a fixed explicit port/Host match.
            port=http.server_port
            http.server_close()
            http=server(lab,port);threading.Thread(target=http.serve_forever,daemon=True).start()
            url='http://127.0.0.1:'+str(port);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                html=opener.open(url).read().decode();self.assertIn('ASR Evaluation Lab',html)
                import re
                token=re.search(r'name="lab-token" content="([^"]+)"',html).group(1)
                bad=urllib.request.Request(url+'/api/release',data=b'{}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError):opener.open(bad)
                foreign=urllib.request.Request(url+'/api/release',data=b'{}',headers={'Content-Type':'application/json','X-Leva-Lab':token,'Origin':'https://foreign.test'})
                with self.assertRaises(urllib.error.HTTPError):opener.open(foreign)
                good=urllib.request.Request(url+'/api/release',data=b'{}',headers={'Content-Type':'application/json','X-Leva-Lab':token})
                self.assertTrue(json.load(opener.open(good))['released'])
                self.assertEqual(json.load(opener.open(url+'/api/export.json'))['runs'],[])
                self.assertIn('reference',opener.open(url+'/api/export.csv').read().decode('utf-8-sig'))
            finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main()
