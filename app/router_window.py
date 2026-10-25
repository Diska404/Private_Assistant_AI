"""User-controlled model, gateway key and capability checks for 9Router."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from hybrid_engine import OnlineUnavailable
from router_provider import RouterClient,base_url,save_key,KEY_FILE


class RouterWindow:
    def __init__(self,main):
        self.main=main;self.window=tk.Toplevel(main.root);self.window.title('Leva — 9Router');self.window.geometry('940x750');self.window.configure(bg='#0b1120')
        self.window.protocol('WM_DELETE_WINDOW',self.close);self.events=queue.Queue();self.running=False
        main.label(self.window,'9Router · pilihan model online',font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=(22,12))
        main.label(self.window,'Provider dan status gratis mengikuti akun/layanan di dashboard. Daftar model tidak menjamin biaya nol.\nTeks percakapan dan riwayat dikirim ke provider pilihan; ASR/TTS tetap lokal, agent tugas terpisah.',wraplength=880,justify='left').pack(anchor='w',padx=24,pady=8)
        body=ttk.Frame(self.window);body.pack(fill='both',expand=True,padx=24,pady=14)
        self.url=tk.StringVar(value=main.preferences.get('router_url'));self.model=tk.StringVar(value=main.preferences.get('router_model'));self.local=tk.StringVar(value=main.preferences.get('agent_local_model'))
        for title,variable in [('Endpoint lokal',self.url)]:
            ttk.Label(body,text=title).pack(anchor='w',pady=6);ttk.Entry(body,textvariable=variable,width=85).pack(fill='x')
        ttk.Label(body,text='Model / combo dari dashboard 9Router').pack(anchor='w',pady=(14,6))
        self.models=ttk.Combobox(body,textvariable=self.model,width=85);self.models.pack(fill='x')
        ttk.Label(body,text='API key gateway 9Router · kolom kosong mempertahankan key yang tersimpan').pack(anchor='w',pady=(14,6))
        self.key=ttk.Entry(body,show='●',width=85);self.key.pack(fill='x')
        ttk.Label(body,text='Agent tugas lokal terpisah · fallback percakapan memakai MiniCPM5 2B').pack(anchor='w',pady=(14,6))
        ttk.Combobox(body,textvariable=self.local,values=('saluki','qwen4b'),state='readonly',width=24).pack(anchor='w')
        row=ttk.Frame(body);row.pack(fill='x',pady=(18,8))
        main.button(row,'Simpan konfigurasi',self.save,primary=True).pack(side='left',padx=(0,8))
        main.button(row,'Muat daftar model',self.models_request).pack(side='left',padx=8)
        main.button(row,'Uji tool calling',self.check_request).pack(side='left',padx=8)
        row2=ttk.Frame(body);row2.pack(fill='x',pady=8)
        main.button(row2,'Mulai gateway lokal',self.start_gateway).pack(side='left',padx=(0,8))
        main.button(row2,'Buka dashboard',self.dashboard).pack(side='left',padx=8)
        main.button(row2,'Gunakan 9Router → Lokal',self.activate).pack(side='left',padx=8)
        main.button(row2,'Google → 9Router → Lokal',self.activate_chain).pack(side='left',padx=8)
        self.notice=tk.StringVar(value='Key tersimpan terenkripsi Windows DPAPI.' if KEY_FILE.is_file() else 'Key belum tersimpan. Masuk ke dashboard lokal, sambungkan provider gratis dan buat key gateway.')
        main.label(body,'',textvariable=self.notice,wraplength=870,justify='left').pack(anchor='w',pady=16)
        main.label(body,'9Router → Lokal menghemat Google sejak awal; Google → 9Router → Lokal memakai Google dahulu.\nGateway decolua/9router 0.5.104 milik Leva berhenti saat Jeda/Lepaskan AI/keluar; proses terpisah tetap berjalan.\nUji tool calling hanya memeriksa format jawaban model, tanpa menjalankan kendali komputer.',wraplength=870,justify='left').pack(anchor='w',pady=10)
        main.apply_theme();self.window.after(120,self.poll)
    def close(self):self.main.router_window=None;self.window.destroy()
    def save(self):
        if self.main.busy or self.running:self.notice.set('Tunggu permintaan aktif selesai sebelum mengganti konfigurasi.');return False
        try:
            changes={'router_url':base_url(self.url.get().strip()),'router_model':self.model.get().strip(),'agent_local_model':self.local.get(),'router_local_model':self.local.get()}
            from preferences import validate_setting
            for k,v in changes.items():validate_setting(k,v)
            key=self.key.get()
            if key:save_key(key);self.key.delete(0,'end')
            self.main.preferences.set_many(changes);self.notice.set('Konfigurasi tersimpan. Key tidak ditampilkan dan tidak dimasukkan ke memori percakapan.');return True
        except (ValueError,OSError):self.notice.set('Konfigurasi belum tersimpan. Periksa endpoint loopback, model, dan penyimpanan key.');return False
    def work(self,kind,fn):
        if self.main.busy or self.running:self.notice.set('Tunggu permintaan aktif selesai.');return
        self.running=True;self.notice.set('Memeriksa gateway…')
        def run():
            try:self.events.put((kind,fn(),None))
            except OnlineUnavailable as error:self.events.put((kind,None,error.reason))
            except Exception:self.events.put((kind,None,'router_check_failed'))
        threading.Thread(target=run,daemon=True).start()
    def client(self):return RouterClient(self.main.preferences.get('router_url'),self.main.preferences.get('router_model'))
    def models_request(self):
        if self.save():self.work('models',lambda:self.client().models())
    def check_request(self):
        if not self.save():return
        def check():
            from assistant_tools import REGISTRY,validate_call
            chosen=self.client().propose_tool([{'role':'user','content':'Panggil get_time tanpa argumen. Ini uji format; host tidak menjalankan tindakan.'}],'Pilih function get_time tepat satu kali.',[REGISTRY['get_time'].declaration()])
            validate_call(chosen['action'],chosen['args'])
            if chosen!={'action':'get_time','args':{}}:raise OnlineUnavailable('router_capability_check_failed')
            return 'Model berhasil mengeluarkan native function call get_time. Kendali komputer tidak dijalankan oleh uji ini.'
        self.work('check',check)
    def start_gateway(self):
        if self.save():self.work('gateway',lambda:self.main.router_gateway.start(self.main.preferences.get('router_url')))
    def dashboard(self):
        import webbrowser
        try:webbrowser.open(base_url(self.url.get().strip()).removesuffix('/v1')+'/dashboard')
        except ValueError:self.notice.set('Gunakan endpoint loopback yang valid.')
    def activate(self):
        if self.save():
            if not self.model.get().strip():self.notice.set('Pilih model atau combo dahulu.');return
            from pipeline_routing import visible_route
            gpu='RTX 5070' if self.main.last_single_gpu=='rtx5070' else 'RTX 4050'
            self.main.mode.set(visible_route('9Router → '+gpu,self.main.dual.get(),self.main.last_single_gpu))
            self.notice.set('Rute percakapan memakai 9Router lalu GPU lokal yang dipilih. Agent tugas tetap terpisah.')
    def activate_chain(self):
        if self.save():
            if not self.model.get().strip():self.notice.set('Pilih model atau combo dahulu untuk cadangan Google.');return
            from pipeline_routing import visible_route
            gpu='RTX 5070' if self.main.last_single_gpu=='rtx5070' else 'RTX 4050'
            self.main.mode.set(visible_route('Google → 9Router → '+gpu,self.main.dual.get(),self.main.last_single_gpu))
            self.notice.set('Google digunakan dahulu; ketika gagal/limit, coba 9Router lalu model lokal. Kuota Google yang sudah limit tidak dicoba berulang selama sesi.')
    def poll(self):
        if not self.window.winfo_exists():return
        while not self.events.empty():
            kind,value,error=self.events.get_nowait();self.running=False
            if error:
                explanations={'router_authentication':'Gateway meminta API key. Password dashboard berbeda dari API key gateway. Simpan key dari dashboard pada kolom di atas.','router_unreachable':'Gateway belum terjangkau. Mulai gateway lokal dahulu.','router_tool_call_unsupported':'Model tidak mengembalikan native tool call; pilih model lain untuk kendali Leva.','router_rate_limit':'Kuota/rate limit tercapai; chat Leva dapat memakai fallback lokal.'}
                self.notice.set(explanations.get(error,'Pemeriksaan belum berhasil: '+error));continue
            if kind=='models':self.models.configure(values=value);self.notice.set(str(len(value))+' ID model tersedia. Pilih yang berstatus gratis di dashboard; harga tidak diverifikasi oleh daftar ini.')
            else:self.notice.set(str(value))
        self.window.after(120,self.poll)
