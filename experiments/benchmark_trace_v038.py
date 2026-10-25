"""Lightweight journal overhead benchmark, synthetic events and isolated data only."""
from pathlib import Path
import json,sys,time,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app')]
from trace_store import TraceStore
from process_trace import TraceHub
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\pending-stage1-20261025')
s=TraceStore(OUT/'fixture-data/benchmark-traces.sqlite3',run_limit=1000)
hub=TraceHub('chat',capacity=1000,store=s);durations=[];cpu=time.process_time();started=time.perf_counter()
for _ in range(1000):
 t=time.perf_counter();hub.emit('model.response_started','local_model_backend',{'ttft_ms':10});durations.append((time.perf_counter()-t)*1000)
flushed=s.flush(8);total=time.perf_counter()-started;health=s.health();runs=s.runs('chat');s.close()
ordered=sorted(durations)
report={'fixture':True,'events':1000,'flush_success':flushed,'health':health,'emit_ms':{'p50':statistics.median(ordered),'p95':ordered[949],'max':ordered[-1]},'total_seconds_including_flush':total,'process_cpu_seconds':time.process_time()-cpu,'retained_events_latest_run':next(r['event_count'] for r in runs if r['run_id']==hub.run_id),'database_bytes':s.path.stat().st_size,'gpu_or_model_loaded':False,'interpretation':'Journal overhead only; not voice, LLM or avatar performance.'}
(OUT/'trace-overhead.json').write_text(json.dumps(report,indent=2))
assert flushed and not health['dropped'] and not health['error']
print(json.dumps(report))
