"""Inspectable autonomy settings, automatic memories, agenda, watches and plugins."""
from datetime import datetime
import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk,messagebox,filedialog

from command_resolution import WIB

class AdvancedWindow:
    def __init__(self,main):
        self.main=main;self.window=tk.Toplevel(main.root);self.window.title('Leva — Pusat kendali');self.window.geometry('1000x780');self.window.configure(bg='#0b1120')
        main.label(self.window,'Pusat kendali Leva',font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=20)
        self.notice=tk.StringVar(value='Data percakapan di D. Audio mikrofon tidak disimpan; layar/kamera hanya diambil saat diminta.')
        main.label(self.window,'',textvariable=self.notice,wraplength=940,justify='left').pack(anchor='w',padx=24)
        self.tabs=ttk.Notebook(self.window);self.tabs.pack(fill='both',expand=True,padx=24,pady=20)
        knowledge=ttk.Frame(self.tabs);self.tabs.add(knowledge,text='Second Brain / Obsidian')
        from second_brain_window import SecondBrainPanel
        self.second_brain_panel=SecondBrainPanel(knowledge,main)
        settings=ttk.Frame(self.tabs);self.tabs.add(settings,text='Sistem & suara lokal')
        self.values={}
        labels={'always_listen':'Pendengar lokal · ucapkan Leva; percakapan lanjutan 45 detik','auto_memory':'Simpan dan rangkum percakapan otomatis di D','autostart':'Mulai Leva diminimalkan saat login Windows','briefing':'Tampilkan briefing satu kali per hari ketika aplikasi aktif','proactive':'Pantau topik yang saya daftarkan · perubahan saja','use_device_location':'Gunakan lokasi Windows untuk cuaca jika tersedia; cadangan Cikarang'}
        for key,label in labels.items():
            variable=tk.BooleanVar(value=main.preferences.get(key));self.values[key]=variable
            ttk.Checkbutton(settings,text=label,variable=variable).pack(anchor='w',padx=20,pady=12)
        city=ttk.Frame(settings);city.pack(fill='x',padx=20,pady=12);ttk.Label(city,text='Kota cuaca:').pack(side='left')
        self.city=tk.StringVar(value=main.preferences.get('weather_city'));ttk.Entry(city,textvariable=self.city,width=30).pack(side='left',padx=12)
        ttk.Label(city,text='Tema:').pack(side='left');self.theme=tk.StringVar(value=main.preferences.get('theme'))
        ttk.Combobox(city,textvariable=self.theme,values=('cyan','gold','violet'),state='readonly',width=12).pack(side='left',padx=12)
        main.button(settings,'Terapkan',self.apply,primary=True).pack(anchor='w',padx=20,pady=16)
        web=ttk.Frame(settings);web.pack(fill='x',padx=20,pady=6)
        ttk.Label(web,text='Port Versi Web (0 = otomatis; berlaku saat server berikutnya):').pack(side='left')
        self.web_port=tk.StringVar(value=main.preferences.get('web_port'));ttk.Entry(web,textvariable=self.web_port,width=8).pack(side='left',padx=8)
        main.button(web,'Simpan port',lambda:main.save_preference('web_port',self.web_port.get())).pack(side='left')
        main.button(settings,'Hubungkan Android · akses pribadi',main.open_remote).pack(anchor='w',padx=20,pady=8)
        main.button(settings,'Buat briefing sekarang',lambda:main.send('Buat briefing: jam saat ini, agenda lokal, cuaca kota pengaturan dan berita terbaru.')).pack(anchor='w',padx=20)
        main.button(settings,'Lokasi perangkat · izin Windows',self.location).pack(anchor='w',padx=20,pady=8)
        main.button(settings,'9Router · model online & fallback',main.open_router).pack(anchor='w',padx=20,pady=8)
        audio=ttk.Frame(self.tabs);self.tabs.add(audio,text='Input & output audio')
        ttk.Label(audio,text='Pilih perangkat secara terpisah. Default mengikuti perangkat Windows; headset dan speaker dapat diganti kapan saja.').pack(anchor='w',padx=20,pady=20)
        self.input_choice=tk.StringVar(value='Default Windows');self.output_choice=tk.StringVar(value='Default Windows')
        ttk.Label(audio,text='Mikrofon / input').pack(anchor='w',padx=20)
        self.input_combo=ttk.Combobox(audio,textvariable=self.input_choice,state='readonly',width=95);self.input_combo.pack(fill='x',padx=20,pady=12)
        ttk.Label(audio,text='Speaker / output jawaban suara').pack(anchor='w',padx=20)
        self.output_combo=ttk.Combobox(audio,textvariable=self.output_choice,state='readonly',width=95);self.output_combo.pack(fill='x',padx=20,pady=12)
        self.device_rows={};self.audio_events=queue.Queue()
        main.button(audio,'Segarkan perangkat',self.load_audio).pack(anchor='w',padx=20,pady=12)
        main.button(audio,'Terapkan perangkat audio',self.apply_audio,primary=True).pack(anchor='w',padx=20,pady=12)
        memory=ttk.Frame(self.tabs);self.tabs.add(memory,text='Memori otomatis')
        bar=ttk.Frame(memory);bar.pack(fill='x',padx=12,pady=12)
        self.query=tk.StringVar();ttk.Entry(bar,textvariable=self.query,width=55).pack(side='left')
        main.button(bar,'Cari',self.search_memory).pack(side='left',padx=8)
        self.memory_text=tk.Text(memory,wrap='word',bg='#111b2d',fg='#e7edf8',font=('Segoe UI',10));self.memory_text.pack(fill='both',expand=True,padx=12,pady=8)
        main.button(memory,'Hapus riwayat otomatis',self.clear_memory).pack(anchor='e',padx=12,pady=8)
        agenda=ttk.Frame(self.tabs);self.tabs.add(agenda,text='Agenda lokal')
        self.agenda_rows=ttk.Treeview(agenda,columns=('title','when'),show='headings');self.agenda_rows.heading('title',text='Agenda');self.agenda_rows.heading('when',text='Waktu');self.agenda_rows.pack(fill='both',expand=True,padx=12,pady=12)
        self.title=tk.StringVar();self.when=tk.StringVar(value=datetime.now(WIB).replace(second=0,microsecond=0).isoformat())
        ttk.Entry(agenda,textvariable=self.title).pack(fill='x',padx=12,pady=6);ttk.Entry(agenda,textvariable=self.when).pack(fill='x',padx=12,pady=6)
        main.button(agenda,'Tambah agenda',self.add_agenda).pack(anchor='w',padx=12,pady=8)
        scheduled=ttk.Frame(self.tabs);self.tabs.add(scheduled,text='Pengingat & tindakan')
        ttk.Label(scheduled,text='Buat melalui chat: ingatkan belajar besok jam 19:00 lalu buka Chrome Diska untuk ChatGPT dan buka Edge untuk EdLink.',wraplength=880).pack(anchor='w',padx=12,pady=12)
        self.schedule_rows=ttk.Treeview(scheduled,columns=('when','title','status'),show='headings',selectmode='browse')
        for key,label in (('when','Waktu WIB'),('title','Pengingat / tindakan'),('status','Status')):self.schedule_rows.heading(key,text=label)
        self.schedule_rows.column('when',width=200);self.schedule_rows.column('title',width=450);self.schedule_rows.column('status',width=110)
        self.schedule_rows.pack(fill='both',expand=True,padx=12,pady=12)
        main.button(scheduled,'Segarkan',self.refresh_schedules).pack(side='left',padx=12,pady=12)
        main.button(scheduled,'Batalkan pengingat pilihan',self.cancel_schedule).pack(side='left',padx=12,pady=12)
        self.refresh_schedules()
        plugins=ttk.Frame(self.tabs);self.tabs.add(plugins,text='Pantauan & plugin')
        self.watch_query=tk.StringVar();ttk.Entry(plugins,textvariable=self.watch_query).pack(fill='x',padx=16,pady=12)
        main.button(plugins,'Pantau topik',self.add_watch).pack(anchor='w',padx=16)
        self.plugins_text=tk.Text(plugins,wrap='word',bg='#111b2d',fg='#e7edf8');self.plugins_text.pack(fill='both',expand=True,padx=16,pady=12)
        main.button(plugins,'Buka folder plugin',lambda:os.startfile(str(main.desktop.tools.plugins.folder))).pack(side='left',padx=16,pady=12)
        main.button(plugins,'Muat ulang plugin',self.reload_plugins).pack(side='left',padx=8,pady=12)
        metrics=ttk.Frame(self.tabs);self.tabs.add(metrics,text='Perangkat & latensi')
        self.metrics_text=tk.Text(metrics,wrap='word',bg='#111b2d',fg='#e7edf8',font=('Consolas',11));self.metrics_text.pack(fill='both',expand=True,padx=16,pady=16)
        workspace=ttk.Frame(self.tabs);self.tabs.add(workspace,text='Proyek, proses & tugas')
        self.workspace_root=tk.StringVar(value=str(main.desktop.tools.project_root()))
        ttk.Label(workspace,textvariable=self.workspace_root,wraplength=900).pack(anchor='w',padx=12,pady=8)
        main.button(workspace,'Pilih workspace proyek',self.select_workspace).pack(anchor='w',padx=12,pady=6)
        self.process_rows=ttk.Treeview(workspace,columns=('shell','state','exit'),show='tree headings',height=5)
        for key,label in (('#0','Process ID'),('shell','Shell'),('state','Status'),('exit','Exit code')):self.process_rows.heading(key,text=label)
        self.process_rows.pack(fill='x',padx=12,pady=8)
        main.button(workspace,'Hentikan proses pilihan',self.stop_process).pack(anchor='w',padx=12,pady=6)
        self.task_rows=ttk.Treeview(workspace,columns=('goal','state'),show='tree headings',height=6)
        for key,label in (('#0','Task ID'),('goal','Tujuan'),('state','Status')):self.task_rows.heading(key,text=label)
        self.task_rows.pack(fill='both',expand=True,padx=12,pady=8)
        main.button(workspace,'Lanjutkan tugas pilihan',self.resume_selected_task).pack(anchor='w',padx=12,pady=6)
        self.refresh_workspace()
        comfy=ttk.Frame(self.tabs);self.tabs.add(comfy,text='ComfyUI')
        self.comfy_root=tk.StringVar(value=main.preferences.get('comfy_root'));self.comfy_url=tk.StringVar(value=main.preferences.get('comfy_url'))
        ttk.Label(comfy,text='Folder instalasi ComfyUI portable atau source dengan .venv').pack(anchor='w',padx=16,pady=(14,4))
        ttk.Entry(comfy,textvariable=self.comfy_root,width=110).pack(fill='x',padx=16)
        main.button(comfy,'Pilih folder ComfyUI',self.select_comfy).pack(anchor='w',padx=16,pady=8)
        ttk.Label(comfy,text='API lokal (loopback)').pack(anchor='w',padx=16)
        ttk.Entry(comfy,textvariable=self.comfy_url,width=60).pack(fill='x',padx=16,pady=6)
        main.button(comfy,'Simpan konektor',self.save_comfy).pack(anchor='w',padx=16,pady=6)
        row=ttk.Frame(comfy);row.pack(fill='x',padx=16,pady=8)
        for title,action in (('Mulai ComfyUI','start'),('Periksa status','status'),('Lihat model','catalog'),('Workflow tersimpan','list'),('Hentikan server Leva','stop_server')):
            main.button(row,title,lambda a=action:self.comfy_command(a)).pack(side='left',padx=3)
        ttk.Label(comfy,text='Perintah chat: buka ComfyUI, susun workflow dengan checkpoint dan LoRA yang saya pilih. Penyusunan peta tidak menjalankan generation.',wraplength=900).pack(anchor='w',padx=16,pady=6)
        self.comfy_text=tk.Text(comfy,wrap='word',bg='#111b2d',fg='#e7edf8');self.comfy_text.pack(fill='both',expand=True,padx=16,pady=12)
        self.comfy_events=queue.Queue();self.comfy_busy=False;self.poll_comfy()
        foo=ttk.Frame(self.tabs);self.tabs.add(foo,text='Fooocus')
        self.foo_root=tk.StringVar(value=main.preferences.get('fooocus_root'));self.foo_url=tk.StringVar(value=main.preferences.get('fooocus_url'))
        ttk.Label(foo,text='Folder Fooocus portable').pack(anchor='w',padx=16,pady=(14,4))
        ttk.Entry(foo,textvariable=self.foo_root,width=110).pack(fill='x',padx=16)
        main.button(foo,'Pilih folder',self.select_fooocus).pack(anchor='w',padx=16,pady=6)
        ttk.Entry(foo,textvariable=self.foo_url).pack(fill='x',padx=16,pady=6)
        ttk.Label(foo,text='Folder checkpoint tambahan, satu path per baris').pack(anchor='w',padx=16)
        self.foo_models=tk.Text(foo,height=3);self.foo_models.pack(fill='x',padx=16,pady=6)
        self.foo_models.insert('1.0','\n'.join(json.loads(main.preferences.get('image_model_roots'))))
        main.button(foo,'Simpan konektor',self.save_fooocus).pack(anchor='w',padx=16,pady=6)
        row=ttk.Frame(foo);row.pack(fill='x',padx=16,pady=6)
        for title,action in (('Mulai Fooocus','start'),('Status','status'),('Buka UI','open'),('Model','catalog'),('Job','list'),('Hentikan','stop_server')):
            main.button(row,title,lambda a=action:self.fooocus_command(a)).pack(side='left',padx=3)
        self.foo_text=tk.Text(foo,wrap='word',bg='#111b2d',fg='#e7edf8');self.foo_text.pack(fill='both',expand=True,padx=16,pady=12)
        self.foo_events=queue.Queue();self.foo_busy=False;self.poll_fooocus()
        self.search_memory();self.refresh_agenda();self.reload_plugins();self.refresh_metrics();self.load_audio();self.poll_audio();main.apply_theme()
    def load_audio(self):
        def run():self.audio_events.put(self.main.desktop.tools.bridge.run('audio_devices',{}))
        threading.Thread(target=run,daemon=True).start()
    def poll_audio(self):
        if not self.window.winfo_exists():return
        while not self.audio_events.empty():
            result=self.audio_events.get_nowait();self.device_rows={f"{r['id']} · {r['name']} [{r['hostapi']}]":r for r in result.get('devices',[])}
            self.input_combo.configure(values=['Default Windows',*[label for label,row in self.device_rows.items() if row['input']]])
            self.output_combo.configure(values=['Default Windows',*[label for label,row in self.device_rows.items() if row['output']]])
            for variable,kind in ((self.input_choice,'input'),(self.output_choice,'output')):
                name=self.main.preferences.get(kind+'_device_name');host=self.main.preferences.get(kind+'_hostapi')
                variable.set(next((label for label,row in self.device_rows.items() if row[kind] and row['name']==name and (not host or row['hostapi']==host)),'Default Windows'))
        self.window.after(200,self.poll_audio)
    def apply_audio(self):
        changes={}
        for variable,kind in ((self.input_choice,'input'),(self.output_choice,'output')):
            row=self.device_rows.get(variable.get(),{})
            changes[kind+'_device_name']=row.get('name','');changes[kind+'_hostapi']=row.get('hostapi','')
        self.main.stop_reply_voice();self.main.preferences.set_many(changes);self.main.apply_autonomy_settings();self.notice.set('Input dan output tersimpan; pendengar lokal dimulai ulang memakai pilihan baru.')
    def location(self):
        from feature_bridge import PYTHON,resource
        subprocess.Popen([str(PYTHON),str(resource('location_helper.py'))],creationflags=0x08000000)
    def apply(self):
        try:
            self.main.preferences.set_many({**{key:var.get() for key,var in self.values.items()},'weather_city':self.city.get().strip(),'theme':self.theme.get()})
            self.main.apply_autonomy_settings();self.notice.set('Pengaturan diterapkan dan tersimpan. Jeda menghentikan mikrofon serta worker AI.')
        except Exception as error:self.notice.set('Pengaturan belum lengkap diterapkan: '+type(error).__name__)
    def search_memory(self):
        store=self.main.desktop.tools.conversations
        rows=store.recall(self.query.get(),10) if self.query.get().strip() else store.overview()
        self.memory_text.delete('1.0','end');self.memory_text.insert('end',json.dumps(rows,indent=2,ensure_ascii=False))
    def clear_memory(self):
        if messagebox.askyesno('Hapus riwayat','Hapus seluruh percakapan dan ringkasan otomatis lokal? Catatan eksplisit tetap disimpan.',parent=self.window):
            self.main.desktop.tools.conversations.clear();self.main.chat.history=[];self.search_memory()
    def refresh_agenda(self):
        for row in self.agenda_rows.get_children():self.agenda_rows.delete(row)
        for row in self.main.desktop.tools.conversations.agenda():self.agenda_rows.insert('','end',values=(row['title'],row['when']))
    def add_agenda(self):
        try:self.main.desktop.tools.conversations.add_agenda(self.title.get(),self.when.get());self.title.set('');self.refresh_agenda()
        except ValueError:self.notice.set('Isi judul dan waktu ISO dengan zona, contoh 2026-10-20T09:00:00+07:00.')
    def refresh_schedules(self):
        for ident in self.schedule_rows.get_children():self.schedule_rows.delete(ident)
        for row in self.main.desktop.schedules.recent():
            self.schedule_rows.insert('','end',iid=row['id'],values=(row['when'],row['title']+(' → '+row['goal'] if row['goal'] else ''),row['status']))
    def cancel_schedule(self):
        selected=self.schedule_rows.selection()
        if selected:
            done=self.main.desktop.schedules.cancel(selected[0]);self.refresh_schedules()
            self.notice.set('Pengingat dibatalkan.' if done else 'Tugas sudah berjalan atau selesai; tidak diulang.')
    def add_watch(self):
        try:self.main.desktop.tools.conversations.watch(self.watch_query.get());self.watch_query.set('');self.reload_plugins()
        except ValueError:self.notice.set('Gunakan topik 2–200 karakter.')
    def reload_plugins(self):
        manager=self.main.desktop.tools.plugins;manager.reload()
        data={'pantauan':self.main.desktop.tools.conversations.watches(),'plugins':manager.public(),'errors':manager.errors,'folder':str(manager.folder),'format':'JSON deklaratif yang memanggil skill baca bawaan; tidak menjalankan file Python unduhan otomatis.'}
        data['curated_workflows']=self.main.desktop.tools.workflows.public()
        data['capability_sources']=__import__('capability_catalog').catalog()['sources']
        self.plugins_text.delete('1.0','end');self.plugins_text.insert('end',json.dumps(data,indent=2,ensure_ascii=False))
    def refresh_metrics(self):
        if not self.window.winfo_exists():return
        data={**self.main.hardware.value,'last_chat_ms':getattr(self.main,'last_chat_ms',None),'last_asr_ms':self.main.local_mic.last_asr_ms,'microphone':self.main.local_mic.state}
        self.metrics_text.delete('1.0','end');self.metrics_text.insert('end',json.dumps(data,indent=2,ensure_ascii=False));self.window.after(2000,self.refresh_metrics)

    def select_workspace(self):
        folder=filedialog.askdirectory(parent=self.window,title='Pilih folder proyek untuk Leva')
        if folder:
            try:
                path=self.main.desktop.tools.projects.root(folder);self.main.preferences.set('workspace_root',str(path));self.workspace_root.set(str(path))
                self.notice.set('Workspace tersimpan. Terminal berjalan dengan hak user Windows, bukan sandbox filesystem atau administrator otomatis.')
            except (ValueError,OSError):self.notice.set('Folder proyek belum dapat digunakan.')

    def refresh_workspace(self):
        if not self.window.winfo_exists():return
        for ident in self.process_rows.get_children():self.process_rows.delete(ident)
        service=self.main.desktop.tools._terminal
        if service:
            for row in service.recent()['processes']:self.process_rows.insert('','end',iid=row['id'],text=row['id'],values=(row['shell'],row['state'],row['exit_code']))
        from task_journal import TaskJournal
        for ident in self.task_rows.get_children():self.task_rows.delete(ident)
        for row in TaskJournal().recent():self.task_rows.insert('','end',iid=row['id'],text=row['id'],values=(row['goal'],row['status']))
        self.window.after(5000,self.refresh_workspace)

    def stop_process(self):
        selected=self.process_rows.selection();service=self.main.desktop.tools._terminal
        if selected and service:
            service.stop(selected[0]);self.notice.set('Permintaan berhenti hanya dikirim ke proses milik Leva.')

    def resume_selected_task(self):
        selected=self.task_rows.selection()
        if selected:self.main.send('lanjut tugas '+selected[0])

    def select_comfy(self):
        folder=filedialog.askdirectory(parent=self.window,title='Pilih instalasi ComfyUI')
        if folder:self.comfy_root.set(folder)

    def save_comfy(self):
        try:
            service=getattr(self.main.desktop.tools,'_comfy',None)
            if service and service.process and service.process.poll() is None:
                self.notice.set('Hentikan server milik Leva sebelum mengganti konfigurasi konektornya.');return
            self.main.preferences.set_many({'comfy_root':self.comfy_root.get().strip(),'comfy_url':self.comfy_url.get().strip()})
            self.main.desktop.tools._comfy=None;self.notice.set('Konfigurasi ComfyUI tersimpan; tidak ada model diunduh atau generation dijalankan.')
        except (OSError,ValueError):self.notice.set('Periksa folder ComfyUI dan alamat API loopback.')

    def comfy_command(self,action):
        if self.comfy_busy:return
        self.comfy_busy=True
        def run():
            try:result=self.main.desktop.tools.execute('comfy_action',{'action':action},'Buka ComfyUI dan lihat model serta workflow tersimpan; hentikan hanya server milik Leva jika diminta.')
            except Exception as error:result={'status':'failed','code':type(error).__name__}
            self.comfy_events.put(result)
        threading.Thread(target=run,daemon=True).start()

    def poll_comfy(self):
        if not self.window.winfo_exists():return
        while not self.comfy_events.empty():
            result=self.comfy_events.get_nowait();self.comfy_busy=False
            self.comfy_text.delete('1.0','end');self.comfy_text.insert('end',json.dumps(result,ensure_ascii=False,indent=2))
        self.window.after(200,self.poll_comfy)

    def select_fooocus(self):
        folder=filedialog.askdirectory(parent=self.window,title='Pilih folder Fooocus portable')
        if folder:self.foo_root.set(folder)

    def save_fooocus(self):
        try:
            service=getattr(self.main.desktop.tools,'_fooocus',None)
            if service and service.process and service.process.poll() is None:
                self.notice.set('Hentikan server Fooocus milik Leva sebelum mengganti konfigurasi.');return
            roots=[line.strip() for line in self.foo_models.get('1.0','end').splitlines() if line.strip()]
            self.main.preferences.set_many({'fooocus_root':self.foo_root.get().strip(),'fooocus_url':self.foo_url.get().strip(),'image_model_roots':json.dumps(roots)})
            self.main.desktop.tools._fooocus=None;self.notice.set('Konektor Fooocus tersimpan. Konfigurasi asli dan bobot model tetap di lokasi asal.')
        except (OSError,ValueError):self.notice.set('Periksa folder instalasi, URL loopback dan folder model tambahan.')

    def fooocus_command(self,action):
        if self.foo_busy:return
        self.foo_busy=True
        def run():
            try:result=self.main.desktop.tools.execute('image_action',{'engine':'fooocus','action':action},'Buka Fooocus dan lihat model; hentikan server milik Leva bila diminta.')
            except Exception as error:result={'status':'failed','code':type(error).__name__}
            self.foo_events.put(result)
        threading.Thread(target=run,daemon=True).start()

    def poll_fooocus(self):
        if not self.window.winfo_exists():return
        while not self.foo_events.empty():
            result=self.foo_events.get_nowait();self.foo_busy=False;self.foo_text.delete('1.0','end');self.foo_text.insert('end',json.dumps(result,ensure_ascii=False,indent=2))
        self.window.after(200,self.poll_fooocus)
