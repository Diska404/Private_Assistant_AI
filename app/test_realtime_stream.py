import io
import json
from pathlib import Path
import queue
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch
import wave
from llm_stream import ContentFilter,AdaptiveSegmenter,generate_stream
from process_trace import TraceHub
from live_speech_pipeline import LiveSpeechPipeline,SpeechRuntimePool

class TextTests(unittest.TestCase):
    def test_reasoning_split_and_side_channel_never_reach_content(self):
        f=ContentFilter();result=''
        for part in ('<th','ink>secret','</thi','nk>Halo.'):result+=f.feed(part)
        self.assertEqual(result,'Halo.')
    def test_phrase_before_full_reply_and_decimal_abbreviation_integrity(self):
        s=AdaptiveSegmenter();self.assertEqual(s.feed('Halo! Tentu aku'),['Halo!'])
        self.assertEqual(s.feed(' bisa membantu.'),['Tentu aku bisa membantu.'])
        s=AdaptiveSegmenter();self.assertEqual(s.feed('Dr. Raka menghitung 0.9 dan 0.11.'),['Dr. Raka menghitung 0.9 dan 0.11.'])
    def test_code_link_and_emoji_are_not_read_as_raw_text(self):
        s=AdaptiveSegmenter();out=[]
        for delta in ('Halo! ```py\n','danger()\n```\n','Sumber https://example.com/a 💗.'):out+=s.feed(delta)
        out+=s.feed('',final=True);text=' '.join(out)
        self.assertNotIn('danger',text);self.assertNotIn('https',text);self.assertNotIn('💗',text)
    def test_japanese_endings_and_last_fragment_are_retained(self):
        s=AdaptiveSegmenter('ja');self.assertEqual(s.feed('こんにちは。元気です'),['こんにちは。'])
        self.assertEqual(s.feed('',final=True),['元気です'])
    def test_stream_uses_backend_content_and_real_timings(self):
        rows=[{'choices':[{'delta':{'reasoning_content':'hidden'}}]},
          {'choices':[{'delta':{'content':'Halo!'}}]},
          {'choices':[{'delta':{},'finish_reason':'stop'}],'timings':{'predicted_per_second':42}},'[DONE]']
        body=b''.join(b'data: '+(r.encode() if isinstance(r,str) else json.dumps(r).encode())+b'\n\n' for r in rows)
        engine=Mock();engine.endpoint='http://fixture';engine.api_key='fixture';engine.system='fixture';engine.max_output_tokens=40;engine.sampling={};engine.chat_template_kwargs={};engine.load_seconds=.1;engine.opener.open.return_value=io.BytesIO(body)
        deltas=[];events=[];self.assertEqual(generate_stream(engine,[],deltas.append,events.append),'Halo!')
        self.assertEqual(deltas,['Halo!']);self.assertEqual(events[-1]['timings']['predicted_per_second'],42)
        self.assertFalse(any('tool.' in e['event_type'] for e in events))

class TraceTests(unittest.TestCase):
    def test_private_modes_no_trace_or_cross_mode_replay(self):
        for mode in ('secret','companion_avatar'):
            hub=TraceHub(mode);hub.emit('model.ready','backend',{'prompt_tokens':1});self.assertEqual(hub.snapshot(mode),[])
        hub=TraceHub('chat');hub.emit('model.ready','backend');self.assertEqual(hub.snapshot('assistant'),[])
    def test_metrics_allowlist_and_sequence_under_concurrency(self):
        hub=TraceHub('assistant',capacity=1000)
        def produce():
            for _ in range(250):hub.emit('model.ready','backend',{'path':'C:/private','prompt':'secret','ttft_ms':1,'total_ms':float('nan')})
        threads=[threading.Thread(target=produce) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        rows=hub.snapshot('assistant');self.assertEqual([r['seq'] for r in rows],list(range(1,1001)))
        self.assertEqual(rows[0]['metrics'],{'ttft_ms':1});self.assertEqual(len(hub.snapshot('assistant',after=995)),5)

class FakeService:
    def __init__(self,persistent=False):
        self.persistent=persistent;self.events=queue.Queue();self.play_stop=threading.Event();self.output_level=0;self.output_telemetry=Mock();self.worker=Mock(active=True);self.synthesizing=False;self.playing=False
        self.folder=tempfile.TemporaryDirectory();self.generated=None;self.stream_audio=False;self.actual_pack='higgs_leva'
    def generate(self,pack,text,**kwargs):
        self.synthesizing=True;path=Path(self.folder.name)/(str(time.time_ns())+'.wav')
        with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(struct.pack('<h',500)*4800)
        self.events.put({'kind':'generated','path':str(path)});return {'actual':pack}
    def accept_generated(self,event):self.generated=Path(event['path']);self.synthesizing=False
    def check_timeout(self):return False
    def finish(self):pass
    def stop(self):self.worker.active=False;self.play_stop.set()
    def audio_status(self,*args,**kwargs):pass

class PipelineTests(unittest.TestCase):
    def make(self,**kwargs):
        self.output=[]
        class Sink:
            def start(s):pass
            def write(s,data):self.output.append(data);time.sleep(.001)
            def stop(s):pass
            def abort(s):pass
            def close(s):pass
        return LiveSpeechPipeline('higgs_leva',service_factory=FakeService,output_factory=lambda rate:Sink(),**kwargs)
    def wait(self,p):
        until=time.monotonic()+4
        while p.active and time.monotonic()<until:p.poll();time.sleep(.005)
        p.poll();self.assertFalse(p.active)
    def test_audio_starts_before_final_text_and_order_is_not_duplicated(self):
        p=self.make();p.feed('Halo! ')
        deadline=time.monotonic()+2
        while not self.output and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(self.output);self.assertFalse(p.input_done)
        p.feed('Aku siap membantu.',final=True);self.wait(p)
        self.assertEqual(p.metrics['synthesized'],2);self.assertEqual(sum(map(len,self.output)),2*9600)
    def test_japanese_wait_does_not_block_llm_feed_or_deadlock(self):
        gate=threading.Event()
        def translate(text):gate.wait(2);return 'こんにちは。'
        p=self.make(language='ja',translate=translate)
        start=time.monotonic()
        for i in range(40):p.feed('Ini kalimat fixture. ')
        p.feed('',final=True);self.assertLess(time.monotonic()-start,.2)
        gate.set();self.wait(p);self.assertEqual(p.metrics['synthesized'],40)
    def test_cancel_rejects_late_text_and_cleans_owned_workers(self):
        p=self.make();p.feed('Halo! ');p.cancel();self.assertFalse(p.feed('Suara lama.',final=True))
        end=time.monotonic()+3
        while not p.cleanup_done and time.monotonic()<end:time.sleep(.01)
        self.assertTrue(p.cleanup_done);self.assertFalse(p.synth.worker.active)
    def test_pool_keeps_only_one_idle_runtime_then_releases(self):
        pool=SpeechRuntimePool(idle_seconds=.08);first=pool.take(FakeService);pool.release(first)
        self.assertIs(pool.take(FakeService),first);pool.release(first);time.sleep(.15)
        self.assertIsNone(pool.cached);self.assertFalse(first.worker.active)

    def test_release_all_rejects_a_late_cache_return(self):
        pool=SpeechRuntimePool();first=pool.take(FakeService);pool.close();pool.release(first)
        self.assertIsNone(pool.cached);self.assertFalse(first.worker.active)

class AssetTests(unittest.TestCase):
    def raw(self,external=False):
        doc={'asset':{'version':'2.0'},'extensions':{'VRMC_vrm':{'meta':{'name':'Fixture'}}},'buffers':[{'uri':'https://evil.example/a'}] if external else []}
        raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
        return b'glTF'+struct.pack('<IIII',2,20+len(raw),len(raw),0x4e4f534a)+raw
    def test_vrm_metadata_and_no_external_fetches(self):
        from avatar_assets import inspect
        self.assertEqual(inspect(self.raw())['name'],'Fixture')
        with self.assertRaisesRegex(ValueError,'external_resources'):inspect(self.raw(True))
        with self.assertRaises(ValueError):inspect(b'not model')

if __name__=='__main__':unittest.main()
