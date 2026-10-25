"""Local-only pairing and device revocation controls; pairing codes never enter chat logs."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from remote_gateway import RemoteGateway

class RemoteWindow:
    def __init__(self,main):
        self.main=main;self.window=tk.Toplevel(main.root);self.window.title('Leva — Hubungkan Android');self.window.geometry('740x610')
        self.events=queue.Queue();self.gateway=RemoteGateway()
        ttk.Label(self.window,text='Laptop sebagai mesin · Android sebagai kendali',font=('Segoe UI',16,'bold')).pack(anchor='w',padx=20,pady=18)
        self.status=tk.StringVar(value='Memeriksa koneksi pribadi…');ttk.Label(self.window,textvariable=self.status,wraplength=680).pack(anchor='w',padx=20,pady=8)
        self.url=tk.StringVar();ttk.Entry(self.window,textvariable=self.url,width=90,state='readonly').pack(fill='x',padx=20,pady=8)
        self.setup_url=tk.StringVar();self.setup_row=ttk.Frame(self.window)
        ttk.Entry(self.setup_row,textvariable=self.setup_url,width=65,state='readonly').pack(side='left',fill='x',expand=True)
        import webbrowser
        ttk.Button(self.setup_row,text='Pengaturan HTTPS',command=lambda:webbrowser.open(self.setup_url.get())).pack(side='left',padx=6)
        row=ttk.Frame(self.window);row.pack(fill='x',padx=20,pady=8)
        for label,fn in [('Periksa Tailscale',self.refresh),('Aktifkan akses HP',self.enable),('Putus akses HP',self.disable)]:ttk.Button(row,text=label,command=fn).pack(side='left',padx=(0,8))
        ttk.Label(self.window,text='Pasang Tailscale di Android, masuk dengan akun yang sama, lalu buka alamat HTTPS di atas. Di Chrome pilih Tambahkan ke layar utama.').pack(anchor='w',padx=20,pady=10)
        self.code=tk.StringVar(value='—');ttk.Label(self.window,textvariable=self.code,font=('Consolas',27,'bold')).pack(anchor='w',padx=20,pady=6)
        ttk.Button(self.window,text='Buat kode pemasangan · 5 menit · sekali pakai',command=self.pair).pack(anchor='w',padx=20,pady=8)
        ttk.Label(self.window,text='Perangkat tersambung (sesi 30 hari; dapat dicabut kapan saja)').pack(anchor='w',padx=20,pady=8)
        self.rows=ttk.Treeview(self.window,columns=('name','state'),show='headings',height=5);self.rows.heading('name',text='Nama perangkat');self.rows.heading('state',text='Status');self.rows.pack(fill='both',expand=True,padx=20,pady=8)
        ttk.Button(self.window,text='Cabut perangkat pilihan',command=self.revoke).pack(anchor='w',padx=20,pady=10)
        ttk.Label(self.window,text='Perintah teks dan hasil tugas melalui HP. Ketuk Aktifkan suara di web untuk mendengar voice pack laptop. Input mikrofon HP dan kendali layar langsung belum tersedia.',wraplength=680).pack(anchor='w',padx=20,pady=8)
        self.refresh();self.poll()
    @property
    def host(self):
        if not getattr(self.main,'_web_host',None):
            from web_host import DesktopWebHost
            self.main._web_host=DesktopWebHost(self.main)
        return self.main._web_host
    def job(self,fn):
        self.status.set('Memproses koneksi pribadi…')
        def run():
            try:self.events.put(fn())
            except Exception as error:self.events.put({'error':str(error),'setup_url':getattr(error,'setup_url','')})
        threading.Thread(target=run,daemon=True).start()
    def refresh(self):self.job(self.gateway.status);self.devices()
    def enable(self):
        host=self.host
        def run():
            host.bridge.start();value=self.gateway.enable(host.bridge.server.server_port)
            host.bridge.remote=value['origin'];self.main.preferences.set_many({'web_remote_enabled':True,'web_remote_origin':value['origin']})
            return {**value,'enabled':True}
        self.job(run)
    def disable(self):
        host=self.host;self.main.preferences.set_many({'web_remote_enabled':False,'web_remote_origin':''});host.bridge.remote=''
        self.job(lambda:(self.gateway.disable(host.bridge.server.server_port if host.bridge.server else int(self.main.preferences.get('web_port'))) or {'ready':False,'detail':'Akses HP dinonaktifkan. Desktop tetap dapat dipakai.'}))
    def pair(self):
        if not self.main.preferences.get('web_remote_enabled') or not self.host.bridge.remote:self.status.set('Aktifkan akses HP terlebih dahulu.');return
        code=self.host.bridge.pairing.begin();self.code.set(code);self.status.set('Ketik kode ini di Android. Berlaku 5 menit, sekali pakai, maksimum 5 percobaan.')
        self.window.after(300000,lambda:self.code.set('Kedaluwarsa') if self.window.winfo_exists() and self.code.get()==code else None)
    def devices(self):
        self.rows.delete(*self.rows.get_children())
        import time
        for row in self.host.bridge.store.devices():self.rows.insert('','end',iid=row['id'],values=(row['name'],'Dicabut' if row['revoked'] else 'Kedaluwarsa' if row['expires']<time.time() else 'Aktif'))
    def revoke(self):
        for ident in self.rows.selection():self.host.bridge.store.revoke(ident)
        self.host.bridge.revision+=1;self.devices();self.status.set('Sesi perangkat dicabut; permintaan yang belum mulai akan dibatalkan.')
    def poll(self):
        if not self.window.winfo_exists():return
        while not self.events.empty():
            value=self.events.get_nowait()
            if value.get('setup_url'):
                self.setup_url.set(value['setup_url']);self.setup_row.pack(fill='x',padx=20,pady=6)
            self.status.set(value.get('error') or ('Akses HP aktif. Buka alamat HTTPS di Android dan buat kode pemasangan.' if value.get('enabled') else 'Tailscale siap. Aktifkan akses HP untuk meneruskan ke Leva.' if value.get('ready') else value.get('detail','Belum tersambung.')))
            self.url.set(value.get('origin',''));self.devices()
        self.window.after(250,self.poll)
