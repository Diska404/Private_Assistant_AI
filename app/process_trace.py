"""Bounded operational evidence only. No raw prompts, paths, tool arguments or reasoning."""
from collections import deque
from datetime import datetime,timezone
import threading
import time
import uuid

PUBLIC={'assistant','chat'}
FIELDS={'load_seconds','ttft_ms','total_ms','prompt_tokens','completion_tokens','exit_code','count','tokens_per_second'}
class TraceHub:
    def __init__(self,mode,capacity=200,store=None):
        self.mode=mode;self.run_id=uuid.uuid4().hex;self.session_id=uuid.uuid4().hex
        self.rows=deque(maxlen=capacity);self.lock=threading.Lock();self.started=time.monotonic();self.seq=0
        self.store=store;self.root_span=uuid.uuid4().hex;self.active_tool_span=None;self.model_span=None
    def emit(self,event_type,component,metrics=None,status='progress'):
        if self.mode not in PUBLIC:return None
        if event_type not in {'run.started','run.completed','run.failed','run.cancelled','run.waiting','model.selected','model.ready','model.prompt_started','model.response_started','model.completed','voice.deferred','tool.started','tool.completed','tool.failed','tool.unverified'}:raise ValueError('invalid_trace_event')
        safe={k:v for k,v in (metrics or {}).items() if k in FIELDS and type(v) in (int,float) and __import__('math').isfinite(v)}
        with self.lock:
            span=self.root_span;parent=None
            if event_type.startswith('model.'):
                if not self.model_span:self.model_span=uuid.uuid4().hex
                span=self.model_span;parent=self.root_span
            elif event_type.startswith('tool.'):
                if event_type=='tool.started' or not self.active_tool_span:self.active_tool_span=uuid.uuid4().hex
                span=self.active_tool_span;parent=self.root_span
                if event_type!='tool.started':self.active_tool_span=None
            self.seq+=1;row={'schema_version':2,'event_id':uuid.uuid4().hex,'run_id':self.run_id,'session_id':self.session_id,'seq':self.seq,'span_id':span,'parent_span_id':parent,
                'timestamp_utc':datetime.now(timezone.utc).isoformat(),'elapsed_ms':round((time.monotonic()-self.started)*1000,2),
                'mode':self.mode,'event_type':event_type,'source_component':component,'provenance':'observed','status':status,'metrics':safe}
            from trace_store import safe_event
            row=safe_event(row)
            self.rows.append(row)
            if self.store:self.store.append(row)
            return {**row,'metrics':dict(row['metrics'])}
    def snapshot(self,mode,after=0):
        if mode!=self.mode or mode not in PUBLIC:return []
        with self.lock:return [{**r,'metrics':dict(r['metrics'])} for r in self.rows if r['seq']>after]
