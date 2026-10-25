"""Actual trace store, Tk progress view and authenticated WebBridge; synthetic events only."""
import copy,json,queue,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\pending-stage1-20261025')
import paths
paths.DATA=OUT/'fixture-data';paths.DATA.mkdir(exist_ok=True)
from process_trace import TraceHub
from trace_store import TraceStore
DB=paths.DATA/'process-traces.sqlite3'
if '--produce' in sys.argv:
 s=TraceStore(DB);h=TraceHub('assistant',store=s)
 h.emit('run.started','request_host',status='started');h.emit('model.ready','local_model_backend',{'load_seconds':.01})
 h.emit('tool.started','tool_executor',status='started');h.emit('tool.completed','tool_executor',{'exit_code':0},status='done');h.emit('run.completed','request_host',status='completed')
 s.close();(OUT/'restart-events-before.json').write_text(json.dumps(h.snapshot('assistant'),indent=2));raise SystemExit
subprocess.run([sys.executable,__file__,'--produce'],check=True,creationflags=0x08000000)
store=TraceStore(DB);store.ready.wait(2)
before=json.loads((OUT/'restart-events-before.json').read_text());after=store.replay('assistant',before[0]['run_id'])['events']
assert before==after
(OUT/'restart-proof.json').write_text(json.dumps({'separate_process_restart':True,'same_event_ids_order_spans':before==after,'event_count':len(after),'run_id':before[0]['run_id'],'production_data_used':False},indent=2))
from web_bridge import WebBridge
from web_store import WebStore
reader=Mock();reader.graph.return_value={'nodes':[],'edges':[]}
bridge=WebBridge(reader,port=20288,store=WebStore(paths.DATA/'web.sqlite3'));bridge.trace_store=store
from preview_companion_fixture import state as template
state=copy.deepcopy(template);state['workspace']='assistant';state['activity']='UJI TERISOLASI · event contoh, bukan pekerjaan agent';state['trace_events']=after
state['task_progress']=[];state['avatar']['asset']='placeholder'
state['rooms']={room:{'model':'fixture','gpu':'fixture','models':{'fixture':'Uji UI tanpa inferensi'},'gpus':{'fixture':'Tidak memuat model'}} for room in ('assistant','chat','secret','companion_avatar')}
bridge.update(state);bridge.log('Leva · Uji','Riwayat contoh telah dimuat setelah proses terpisah ditutup. Tidak ada mikrofon atau model AI yang dinyalakan.')
url=bridge.start();(OUT/'fixture-url.txt').write_text(url)
import tkinter as tk
root=tk.Tk();root.title('Leva · Kontrol uji trace terisolasi');root.geometry('450x100')
main=SimpleNamespace(root=root,workspace='assistant',preferences=SimpleNamespace(path=paths.DATA/'prefs.sqlite3'),_trace_store=store,process_trace=None)
def switch(mode):
 main.workspace=mode;state['workspace']=mode;state['trace_events']=after if mode=='assistant' else [];bridge.update(state)
for mode in ('assistant','chat','secret','companion_avatar'):tk.Button(root,text=mode,command=lambda m=mode:switch(m)).pack(side='left')
from task_progress import show_progress
show_progress(main)
def tick():
 while not bridge.controls.empty():
  job=bridge.controls.get_nowait()
  if job['kind']=='workspace':switch(job['value'])
  bridge.finish(job,'completed','Fixture UI; tidak menjalankan alat.')
 root.after(100,tick)
def stop():bridge.stop();bridge.store.close();store.close();root.destroy()
root.protocol('WM_DELETE_WINDOW',stop);tick();print('Trace fixture ready on loopback port '+str(bridge.server.server_port),flush=True);root.mainloop()
