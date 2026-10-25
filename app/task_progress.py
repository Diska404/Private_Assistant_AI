"""Observable host events, never private reasoning or invented tool activity."""
from datetime import datetime,timezone
import threading
import time

LABELS={'code_graph':'Graf kode','rea_analysis':'Analisis REA','capability_catalog':'Katalog kemampuan','file_action':'Berkas','project_action':'Proyek','terminal':'Terminal','terminal_action':'Terminal',
        'web_search':'Pencarian web','read_webpage':'Membaca halaman','browser_action':'Browser',
        'computer_action':'Kendali aplikasi','describe_screen':'Layar','obsidian_action':'Obsidian',
        'comfy_action':'ComfyUI','image_action':'Pembuatan gambar','list_windows':'Jendela',
        'open_browser':'Membuka browser','open_app':'Membuka aplikasi'}
STATES={'running':'berjalan','done':'selesai menurut hasil alat','failed':'gagal','dispatched':'input terkirim · perlu verifikasi',
        'unverified':'belum terverifikasi','needs_input':'memerlukan jawaban','cancelled':'dihentikan'}

class TaskProgress:
    def __init__(self):self.lock=threading.RLock();self.rows=[];self.started=time.monotonic();self.sequence=0;self.counter=0
    def begin(self,workspace):
        with self.lock:self.rows=[];self.started=time.monotonic();self.sequence+=1;self.counter=0
        self.add('request','Permintaan diterima · '+workspace)
    def add(self,stage,label,status='running',tool='',action=''):
        with self.lock:
            self.counter+=1
            row={'seq':self.counter,'request':self.sequence,'at':datetime.now(timezone.utc).isoformat(),
                 'elapsed_s':round(time.monotonic()-self.started,2),'stage':stage,'label':str(label)[:200],
                 'status':str(status)[:35],'tool':str(tool)[:80],'action':str(action)[:50]}
            self.rows.append(row);self.rows=self.rows[-100:];return row
    def tool(self,name,args,result=None):
        action=str(args.get('action',''))[:50] if isinstance(args,dict) else ''
        state='running' if result is None else str(result.get('status','unverified'))
        label=LABELS.get(name,name)+((' · '+action) if action else '')+' · '+STATES.get(state,state)
        return self.add('tool',label,state,name,action)
    def snapshot(self):
        with self.lock:return [dict(r) for r in self.rows]

def tracker(main):
    item=getattr(main,'task_progress',None)
    if not isinstance(item,TaskProgress):item=TaskProgress();main.task_progress=item
    return item

def begin_request(main,workspace):
    from trace_store import start_trace
    start_trace(main,getattr(main,'workspace','assistant'))
    main.task_progress=TaskProgress();main.task_progress.begin(workspace);return main.task_progress

def show_progress(main):
    if getattr(main,'workspace','assistant') not in ('assistant','chat'):return
    import tkinter as tk
    from tkinter import ttk
    window=tk.Toplevel(main.root);window.title('Leva · Proses pekerjaan');window.geometry('820x440')
    tk.Label(window,text='Tahap aktual dari host dan alat. Status input terkirim belum membuktikan keberhasilan.').pack(anchor='w',padx=12,pady=10)
    from trace_store import store_for
    store=store_for(main)
    toolbar=ttk.Frame(window);toolbar.pack(fill='x',padx=12)
    selected=tk.StringVar(value='Proses saat ini');picker=ttk.Combobox(toolbar,textvariable=selected,state='readonly',width=70)
    picker.pack(side='left',fill='x',expand=True)
    health=tk.StringVar();tk.Label(window,textvariable=health).pack(anchor='w',padx=12)
    tree=ttk.Treeview(window,columns=('time','step','state'),show='headings')
    for key,title,width in (('time','Detik',65),('step','Tahap',550),('state','Status',150)):
        tree.heading(key,text=title);tree.column(key,width=width,stretch=key=='step')
    tree.pack(fill='both',expand=True,padx=12,pady=8)
    prior=None;prior_mode=None;choices={};refreshed=0
    def refresh():
        nonlocal prior,prior_mode,choices,refreshed
        if not window.winfo_exists():return
        mode=getattr(main,'workspace','assistant')
        if mode not in ('assistant','chat'):
            tree.delete(*tree.get_children());picker['values']=();selected.set('Proses saat ini');choices={};prior=None;prior_mode=mode
            health.set('Proses tidak ditampilkan dalam ruang personal.');window.after(300,refresh);return
        if mode!=prior_mode:
            selected.set('Proses saat ini');prior_mode=mode;refreshed=0
        if time.monotonic()-refreshed>2:
            choices={r['updated_at'][:19]+' UTC · '+r['run_id'][:8]+' · '+str(r['event_count'])+' event':r['run_id'] for r in store.runs(mode)}
            picker['values']=('Proses saat ini',*choices);refreshed=time.monotonic()
        run=choices.get(selected.get())
        replay=store.replay(mode,run) if run else None
        rows=[] if run else tracker(main).snapshot()
        from process_trace import TraceHub
        hub=getattr(main,'process_trace',None)
        events=replay['events'] if replay else hub.snapshot(mode) if isinstance(hub,TraceHub) else []
        rows+=[{'elapsed_s':round(e['elapsed_ms']/1000,2),'label':e['event_type'],'status':e['provenance']+' · '+e['status']} for e in events]
        status=store.health()
        health.set(('Riwayat tersimpan · ' if run else 'Proses saat ini · ')+('Sebagian event tidak tersedia · ' if replay and replay['truncated'] else '')+str(status['pending'])+' menunggu simpan · '+str(status['dropped'])+' event gagal disimpan'+(' · '+status['error'] if status['error'] else ''))
        if rows!=prior:
            tree.delete(*tree.get_children())
            for r in rows:tree.insert('','end',values=(r['elapsed_s'],r['label'],r['status']))
            prior=rows
            children=tree.get_children()
            if children:tree.see(children[-1])
        window.after(300,refresh)
    refresh()
