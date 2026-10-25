import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
import unittest
from unittest.mock import Mock
import urllib.request
import urllib.error
from process_trace import TraceHub
from trace_store import TraceStore,start_trace

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'trace.sqlite3';self.stores=[]
        self.addCleanup(lambda:[s.close() for s in self.stores])
    def store(self,**kw):
        s=TraceStore(self.path,**kw);self.stores.append(s);return s
    def test_restart_keeps_ids_spans_order_and_redacts_payload(self):
        s=self.store();h=TraceHub('assistant',store=s)
        h.emit('run.started','request_host');h.emit('tool.started','tool_executor')
        h.emit('tool.completed','tool_executor',{'exit_code':0,'password':'secret','path':'C:/private'})
        h.emit('run.completed','request_host');expected=h.snapshot('assistant');s.close()
        s=self.store();s.ready.wait(2)
        self.assertEqual(s.replay('assistant',h.run_id)['events'],expected)
        self.assertEqual(expected[1]['span_id'],expected[2]['span_id']);self.assertEqual(expected[1]['parent_span_id'],expected[0]['span_id'])
        self.assertNotIn('secret',json.dumps(expected));self.assertEqual(s.replay('chat',h.run_id)['events'],[])
    def test_retention_and_cursor_gap_are_visible(self):
        s=self.store(max_runs=2,max_events=5,run_limit=3)
        hs=[]
        for _ in range(3):
            h=TraceHub('chat',store=s);hs.append(h)
            for i in range(4):h.emit('model.ready','backend')
        self.assertTrue(s.flush());self.assertLessEqual(len(s.runs('chat')),2)
        self.assertEqual(s.replay('chat',hs[0].run_id)['events'],[])
        r=s.replay('chat',hs[-1].run_id)
        self.assertEqual([e['seq'] for e in r['events']],[2,3,4]);self.assertTrue(r['truncated'])
        self.assertFalse(s.replay('chat',hs[-1].run_id,after=2)['truncated'])
        self.assertLessEqual(sum(r['event_count'] for r in s.runs('chat')),5)
    def test_parallel_emission_and_allowlist_at_storage_boundary(self):
        s=self.store(run_limit=1000);h=TraceHub('assistant',capacity=1000,store=s)
        threads=[threading.Thread(target=lambda:[h.emit('model.ready','backend') for _ in range(50)]) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        s.flush();self.assertEqual(len(s.replay('assistant',h.run_id)['events']),200)
        row=h.snapshot('assistant')[-1];row['seq']+=1;row['event_id']='a'*32;row['prompt']='private';row['source_component']='API_KEY';row['status']='SECRET'
        s.append(row);s.flush();last=s.replay('assistant',h.run_id,200)['events'][0]
        self.assertNotIn('prompt',last);self.assertEqual(last['source_component'],'other_component');self.assertEqual(last['status'],'unverified')
    def test_private_modes_never_create_trace_store_and_generation_is_reused(self):
        main=Mock(generation=1,workspace='secret');main.preferences.path=self.path.parent/'prefs.sqlite3'
        main._trace_generation=None;main._trace_store=None
        first=start_trace(main,'secret');self.assertIsNone(main._trace_store);self.assertEqual(first.snapshot('secret'),[])
        a=start_trace(main,'assistant');self.stores.append(main._trace_store)
        self.assertIs(start_trace(main,'assistant'),a);self.assertEqual(len(a.snapshot('assistant')),1)
        main.generation+=1;self.assertNotEqual(start_trace(main,'assistant').run_id,a.run_id)
    def test_disk_failure_and_shutdown_are_reported_without_crashing(self):
        self.path.write_text('not a sqlite database');s=self.store();s.ready.wait(2)
        TraceHub('chat',store=s).emit('run.started','room_host');self.assertTrue(s.flush())
        self.assertTrue(s.health()['error']);self.assertGreater(s.health()['dropped'],0)
        s.close();self.assertTrue(s.health()['closed']);self.assertFalse(s.worker.is_alive())
    def test_untrusted_ids_and_private_replay(self):
        s=self.store()
        for run,after in (('../../secrets',0),('a'*32,-1),('a'*32,True)):
            with self.assertRaises(ValueError):s.replay('assistant',run,after)
        self.assertEqual(s.runs('secret'),[]);self.assertEqual(s.replay('secret','bad')['events'],[])
    def test_queue_pressure_does_not_block_and_reports_loss(self):
        gate=threading.Event();entered=threading.Event();original=TraceStore._prune
        def delayed(store,conn):entered.set();gate.wait(2);return original(store,conn)
        with patch.object(TraceStore,'_prune',delayed):
            s=self.store(queue_size=1);self.assertTrue(entered.wait(2))
            try:
                h=TraceHub('chat',store=s);h.emit('run.started','room_host');h.emit('run.completed','room_host')
                self.assertEqual(s.health()['dropped'],1)
            finally:gate.set()
            self.assertTrue(s.flush());s.close()
    def test_old_events_are_removed_without_touching_current_run(self):
        from datetime import datetime,timedelta,timezone
        s=self.store();h=TraceHub('chat');old=h.emit('run.started','room_host')
        old['timestamp_utc']=(datetime.now(timezone.utc)-timedelta(days=9)).isoformat()
        s.append(old);s.append(h.emit('run.completed','room_host'));s.flush()
        replay=s.replay('chat',h.run_id)
        self.assertEqual([r['seq'] for r in replay['events']],[2]);self.assertTrue(replay['truncated'])

class TraceHTTPTests(unittest.TestCase):
    setUp=StoreTests.setUp
    store=StoreTests.store
    # Separate actual HTTP round trips; no agent/model invocation.
    def test_authenticated_replay_scope_and_static_module(self):
        from web_bridge import WebBridge
        from web_store import WebStore
        s=self.store();h=TraceHub('chat',store=s);h.emit('run.started','room_host');s.flush()
        ledger=WebStore(Path(self.folder.name)/'web.sqlite3');self.addCleanup(ledger.close)
        bridge=WebBridge(Mock(),port=0,store=ledger);bridge.trace_store=s;bridge.update({'workspace':'chat'});bridge.start();self.addCleanup(bridge.stop)
        def get(path,auth=True):
            headers={'Origin':bridge.origin}
            if auth:headers['Cookie']='leva_session='+bridge.cookie
            return urllib.request.urlopen(urllib.request.Request(bridge.origin+path,headers=headers),timeout=3)
        with get('/api/trace') as r:self.assertEqual(json.load(r)['runs'][0]['run_id'],h.run_id)
        with get('/api/trace?run_id='+h.run_id) as r:self.assertEqual(json.load(r)['events'][0]['event_id'],h.snapshot('chat')[0]['event_id'])
        with self.assertRaises(urllib.error.HTTPError):get('/api/trace',False)
        with get('/trace.js') as r:self.assertIn(b'TraceReplay',r.read())
        bridge.update({'workspace':'assistant'})
        with get('/api/trace?run_id='+h.run_id) as r:self.assertEqual(json.load(r)['events'],[])
        for mode in ('secret','companion_avatar'):
            bridge.update({'workspace':mode})
            with get('/api/trace?run_id='+h.run_id) as r:self.assertEqual(json.load(r)['events'],[])
