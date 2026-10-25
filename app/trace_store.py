"""Small asynchronous journal of operational events, never conversation contents."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from pathlib import Path
import queue
import re
import sqlite3
import threading
import weakref

_STORES=weakref.WeakSet()

def close_all():
    """Release journal handles at application/test-process shutdown."""
    for store in list(_STORES):store.close()

PUBLIC = {'assistant', 'chat'}
EVENTS = {'run.started','run.completed','run.failed','run.cancelled','run.waiting',
          'model.selected','model.ready','model.prompt_started','model.response_started',
          'model.completed','voice.deferred','tool.started','tool.completed','tool.failed','tool.unverified'}
COMPONENTS = {'request_host','room_host','local_model_backend','speech_resource_policy','tool_executor','backend'}
STATES = {'progress','started','completed','failed','cancelled','waiting','done','unverified','dispatched','needs_input'}
FIELDS = {'load_seconds','ttft_ms','total_ms','prompt_tokens','completion_tokens','exit_code','count','tokens_per_second'}
ID = re.compile(r'^[a-f0-9]{32}$')

def safe_event(row):
    """Reconstruct the allowlisted payload even when a caller submits extra keys."""
    import math
    if row.get('mode') not in PUBLIC or row.get('event_type') not in EVENTS:
        raise ValueError('invalid_trace_event')
    result = {}
    for key in ('event_id','run_id','session_id','span_id'):
        value = row.get(key)
        if not isinstance(value,str) or not ID.fullmatch(value):raise ValueError('invalid_trace_id')
        result[key] = value
    parent = row.get('parent_span_id')
    if parent is not None and (not isinstance(parent,str) or not ID.fullmatch(parent)):raise ValueError('invalid_trace_id')
    seq = row.get('seq'); elapsed = row.get('elapsed_ms')
    if type(seq) is not int or seq < 1 or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('invalid_trace_sequence')
    stamp = datetime.fromisoformat(row['timestamp_utc'])
    if stamp.tzinfo is None:raise ValueError('invalid_trace_timestamp')
    result.update(schema_version=2, mode=row['mode'], event_type=row['event_type'],
                  source_component=row.get('source_component') if row.get('source_component') in COMPONENTS else 'other_component',
                  provenance='observed',status=row.get('status') if row.get('status') in STATES else 'unverified',
                  parent_span_id=parent,seq=seq,elapsed_ms=elapsed,timestamp_utc=stamp.astimezone(timezone.utc).isoformat(),
                  metrics={k:v for k,v in row.get('metrics',{}).items() if k in FIELDS and type(v) in (int,float) and math.isfinite(v)})
    return result

class TraceStore:
    def __init__(self,path,*,max_runs=100,max_events=20000,run_limit=200,retention_days=7,queue_size=2048):
        self.path=Path(path);self.max_runs=max(1,int(max_runs));self.max_events=max(1,int(max_events));self.run_limit=max(1,int(run_limit));self.days=max(1,int(retention_days))
        self.queue=queue.Queue(maxsize=queue_size);self.lock=threading.Lock();self.closed=False;self.dropped=0;self.error='';self.ready=threading.Event()
        _STORES.add(self)
        self.worker=threading.Thread(target=self._write,name='LevaTraceWriter',daemon=True);self.worker.start()
    def append(self,row):
        row=safe_event(row)
        with self.lock:
            if self.closed:self.dropped+=1;return False
            try:self.queue.put_nowait(row);return True
            except queue.Full:self.dropped+=1;return False
    def health(self):
        with self.lock:return {'pending':self.queue.qsize(),'dropped':self.dropped,'error':self.error,'closed':self.closed,'ready':self.ready.is_set(),'max_runs':self.max_runs,'max_events':self.max_events,'events_per_run':self.run_limit,'retention_days':self.days}
    def _write(self):
        conn=None
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            conn=sqlite3.connect(str(self.path),timeout=1)
            conn.execute('PRAGMA journal_mode=WAL');conn.execute('PRAGMA journal_size_limit=1048576')
            conn.execute('CREATE TABLE IF NOT EXISTS trace_events (event_id TEXT PRIMARY KEY,run_id TEXT,mode TEXT,seq INTEGER,stamp TEXT,payload TEXT,UNIQUE(run_id,seq))')
            conn.execute('CREATE INDEX IF NOT EXISTS trace_scope ON trace_events(mode,run_id,seq)')
            conn.execute('CREATE INDEX IF NOT EXISTS trace_time ON trace_events(stamp)')
            self._prune(conn);conn.commit()
        except Exception as error:
            with self.lock:self.error=type(error).__name__
        finally:self.ready.set()
        while True:
            first=self.queue.get();batch=[first]
            while len(batch)<64:
                try:batch.append(self.queue.get_nowait())
                except queue.Empty:break
            stop=any(item is None for item in batch);events=[item for item in batch if item is not None]
            try:
                if conn is None:raise OSError('trace_unavailable')
                with conn:
                    conn.executemany('INSERT OR IGNORE INTO trace_events VALUES (?,?,?,?,?,?)',[(e['event_id'],e['run_id'],e['mode'],e['seq'],e['timestamp_utc'],json.dumps(e,separators=(',',':'))) for e in events])
                    for run in {e['run_id'] for e in events}:
                        conn.execute('DELETE FROM trace_events WHERE run_id=? AND seq NOT IN (SELECT seq FROM trace_events WHERE run_id=? ORDER BY seq DESC LIMIT ?)',(run,run,self.run_limit))
                    self._prune(conn)
            except Exception as error:
                with self.lock:self.error=type(error).__name__;self.dropped+=len(events)
            finally:
                for _ in batch:self.queue.task_done()
            if stop:break
        if conn:conn.close()
    def _prune(self,conn):
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.days)).isoformat()
        conn.execute('DELETE FROM trace_events WHERE stamp<?',(cutoff,))
        conn.execute('DELETE FROM trace_events WHERE run_id NOT IN (SELECT run_id FROM trace_events GROUP BY run_id ORDER BY MAX(rowid) DESC LIMIT ?)',(self.max_runs,))
        conn.execute('DELETE FROM trace_events WHERE event_id NOT IN (SELECT event_id FROM trace_events ORDER BY rowid DESC LIMIT ?)',(self.max_events,))
    def _read(self,query,args):
        if not self.path.is_file():return []
        # Read-only URI: a missing database never creates a stray file.
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.15)) as conn:return conn.execute(query,args).fetchall()
        except sqlite3.Error as error:
            with self.lock:self.error=type(error).__name__
            return []
    def runs(self,mode):
        if mode not in PUBLIC:return []
        rows=self._read('SELECT run_id,MIN(stamp),MAX(stamp),COUNT(*),MIN(seq),MAX(seq) FROM trace_events WHERE mode=? GROUP BY run_id ORDER BY MAX(stamp) DESC,MAX(rowid) DESC LIMIT 100',(mode,))
        return [dict(zip(('run_id','started_at','updated_at','event_count','first_seq','last_seq'),r)) for r in rows]
    def replay(self,mode,run_id,after=0):
        if mode not in PUBLIC:return {'events':[],'runs':[]}
        if not isinstance(run_id,str) or not ID.fullmatch(run_id):raise ValueError('invalid_trace_id')
        if type(after) is not int or after<0 or after>10**9:raise ValueError('invalid_trace_cursor')
        rows=self._read('SELECT payload FROM trace_events WHERE mode=? AND run_id=? AND seq>? ORDER BY seq LIMIT 200',(mode,run_id,after))
        bounds=self._read('SELECT MIN(seq),MAX(seq) FROM trace_events WHERE mode=? AND run_id=?',(mode,run_id))
        first,last=bounds[0] if bounds else (None,None)
        events=[json.loads(r[0]) for r in rows]
        expected=after+1
        gap=first is not None and first>expected
        for row in events:
            if row['seq']!=expected:gap=True
            expected=row['seq']+1
        return {'events':events,'run_id':run_id,'first_seq':first,'last_seq':last,'truncated':gap,'next_after':events[-1]['seq'] if events else after,'health':self.health()}
    def flush(self,timeout=3):
        import time
        deadline=time.monotonic()+timeout
        while self.queue.unfinished_tasks and time.monotonic()<deadline:time.sleep(.005)
        return not self.queue.unfinished_tasks
    def close(self,timeout=3):
        with self.lock:
            if self.closed:return
            self.closed=True
        try:self.queue.put(None,timeout=timeout)
        except queue.Full:return
        self.worker.join(timeout)

def store_for(main):
    value=getattr(main,'_trace_store',None)
    if not isinstance(value,TraceStore):
        prefs=getattr(getattr(main,'preferences',None),'path',None)
        from paths import DATA
        value=main._trace_store=TraceStore((prefs.parent if isinstance(prefs,Path) else DATA)/'process-traces.sqlite3')
    return value

def start_trace(main,mode):
    from process_trace import TraceHub
    key=(getattr(main,'generation',None),mode)
    if getattr(main,'_trace_generation',None)==key and isinstance(getattr(main,'process_trace',None),TraceHub):return main.process_trace
    main._trace_generation=key
    hub=main.process_trace=TraceHub(mode,store=store_for(main) if mode in PUBLIC else None)
    hub.emit('run.started','request_host',status='started')
    return hub

import atexit
atexit.register(close_all)
