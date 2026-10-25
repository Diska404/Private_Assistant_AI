import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'experiments')]
from chat_service import ChatService,session_worker
from voice_core import VoiceEvents
from voice_pack_service import VoicePackService
from seed_voice_adapter import asset_stamp

class Model:
    def __init__(self):self.process=None;self.closes=0
    def generate(self,messages):self.process=Mock();self.process.poll.return_value=None;return 'Halo.'
    def close(self):self.closes+=1;self.process=None

class Worker:
    def __init__(self):self.active=False;self.events=VoiceEvents();self.started=[];self.sent=[];self.stops=0
    def start(self,*args,initial_message=None):self.active=True;self.started.append(initial_message)
    def send(self,message):self.sent.append(message)
    def stop(self):self.active=False;self.stops+=1

class WarmTests(unittest.TestCase):
    def requests(self,models):
        return [{'id':i,'messages':[{'role':'user','content':'Halo'}],'mode':'local','local_model':m,'keep_warm':True}
            for i,m in enumerate(models,1)]

    def test_owned_session_reuses_model_without_adding_hidden_history(self):
        model=Model();events=[]
        data=''.join(json.dumps(r)+'\n' for r in self.requests(['saluki','saluki']))
        with patch('chat_service.sys.stdin',io.StringIO(data)),patch('chat_service.make_local',return_value=model) as factory:
            session_worker(events.append,idle_seconds=.03)
        self.assertEqual(factory.call_count,1)
        self.assertEqual([e['model_reused'] for e in events if e['kind']=='result'],[False,True])
        self.assertIsNone(model.process)
        self.assertEqual(events[-1]['kind'],'stopped')

    def test_profile_change_unloads_previous_model(self):
        models=[Model(),Model()];events=[]
        data=''.join(json.dumps(r)+'\n' for r in self.requests(['saluki','qwen4b']))
        with patch('chat_service.sys.stdin',io.StringIO(data)),patch('chat_service.make_local',side_effect=models):
            session_worker(events.append,idle_seconds=.03)
        self.assertTrue(all(m.process is None and m.closes>=1 for m in models))

    def test_idle_timeout_closes_weights_before_terminal_event(self):
        model=Model();events=[]
        class HeldInput:
            first=True
            def __iter__(self):return self
            def __next__(self):
                if self.first:self.first=False;return json.dumps(WarmTests().requests(['saluki'])[0])+'\n'
                time.sleep(.2);raise StopIteration
        def emit(event):
            if event['kind']=='stopped':self.assertIsNone(model.process)
            events.append(event)
        with patch('chat_service.sys.stdin',HeldInput()),patch('chat_service.make_local',return_value=model):
            session_worker(emit,idle_seconds=.03)
        self.assertEqual(events[-1]['kind'],'stopped')

    def test_persistent_client_roundtrip_keeps_owned_worker_and_cancels_it(self):
        code="import sys,json\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'kind':'result','id':r['id'],'provider':'local','response':'Halo.'}),flush=True)"
        service=ChatService([sys.executable,'-u','-c',code],persistent=True)
        try:
            service.ask('Satu','local');process=service.process
            service.ask('Dua','local')
            self.assertIs(service.process,process)
            self.assertEqual(len(service.history),4)
            service.cancel();self.assertIsNotNone(process.poll())
        finally:service.cancel()

    def test_cancellation_during_session_request_never_commits_late_history(self):
        code="import sys,time\nsys.stdin.readline();time.sleep(30)"
        service=ChatService([sys.executable,'-u','-c',code],persistent=True);result=[]
        thread=threading.Thread(target=lambda:result.append(service.ask('Halo','local')));thread.start()
        until=time.monotonic()+3
        while service.process is None and time.monotonic()<until:time.sleep(.01)
        service.cancel();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(result,[{'cancelled':True}]);self.assertEqual(service.history,[])

    def test_voice_keeps_idle_models_but_rejects_prior_request_and_releases_on_stop(self):
        service=VoicePackService(persistent=True);worker=Worker();service.worker=worker;service.events=worker.events
        with tempfile.TemporaryDirectory() as directory,patch('voice_pack_service.PREVIEWS',Path(directory)),\
             patch('voice_pack_service.resolve_pack',return_value={'actual':'leva_gfl2','available':True}),\
             patch('voice_pack_service.validate_preview',side_effect=lambda p:(Path(p),.2)):
            try:
                service.generate('leva_gfl2','Satu.');first=worker.started[0]
                service.accept_generated({'actual_pack':'leva_gfl2','path':first['output'],'request_id':first['request_id']})
                service.finish();self.assertFalse(service.active);self.assertTrue(service.loaded)
                service.generate('leva_gfl2','Dua.');self.assertEqual(len(worker.started),1);self.assertEqual(len(worker.sent),1)
                second=worker.sent[0]
                with self.assertRaisesRegex(ValueError,'stale'):
                    service.accept_generated({'actual_pack':'leva_gfl2','path':second['output'],'request_id':first['request_id']})
                service.stop();self.assertFalse(service.loaded)
            finally:service.stop()

    def test_busy_voice_is_terminated_on_new_request_instead_of_queueing_stale_audio(self):
        service=VoicePackService(persistent=True);worker=Worker();service.worker=worker;service.events=worker.events
        with tempfile.TemporaryDirectory() as directory,patch('voice_pack_service.PREVIEWS',Path(directory)),\
             patch('voice_pack_service.resolve_pack',return_value={'actual':'leva_gfl2','available':True}):
            try:
                service.generate('leva_gfl2','Satu.');service.generate('leva_gfl2','Dua.')
                self.assertEqual(len(worker.started),2);self.assertEqual(worker.sent,[])
            finally:service.stop()

    def test_asset_changes_invalidate_voice_cache_signature(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model';path.write_bytes(b'one');first=asset_stamp([path])
            path.write_bytes(b'changed');self.assertNotEqual(first,asset_stamp([path]))

    def test_voice_session_does_not_read_stdin_during_native_model_loading(self):
        from voice_pack_worker import session
        reading=threading.Event();executing=threading.Event();overlap=[]
        class Input:
            count=0
            def readline(self):
                if executing.is_set():overlap.append(True)
                reading.set();self.count+=1
                return json.dumps({'request_id':1})+'\n' if self.count==1 else ''
        def run(request,cache,emit=None):
            reading.clear();executing.set();time.sleep(.04)
            self.assertFalse(reading.is_set())
            executing.clear();return {'kind':'generated'}
        output=io.StringIO()
        with patch('voice_pack_worker.sys.stdin',Input()),patch('voice_pack_worker.run',side_effect=run):
            session(output,idle_seconds=.1)
        events=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(overlap,[]);self.assertEqual(events[0]['request_id'],1)
        self.assertEqual(events[-1]['kind'],'stopped')

if __name__=='__main__':unittest.main()
