"""Interactive desktop HUD, sharing the existing Leva services and command entry."""
from datetime import datetime
import math
import time
import tkinter as tk
from tkinter import ttk

from command_resolution import WIB
from hud_core import REPORTS, assistant_state, coordinates, filtered, inventory, project, shortest_path
from neural_orb import NeuralOrb
from paths import ROOT
from preferences import MODES

BG, PANEL, CARD = "#060c13", "#0e1925", "#182b3a"
INK, MUTED, ACCENT = "#e2ecee", "#8b9da6", "#6bdce6"
COLORS = {"core": "#f7c66d", "module": "#70e3b7", "profile": "#79acfa", "document": "#c29bf3"}
LABELS = {"idle": "SIAP · mikrofon tidak aktif", "thinking": "MEMPROSES", "sleeping": "SISTEM DIJEDA",
          "connecting": "MENGHUBUNGKAN SUARA", "listening": "MENDENGARKAN", "speaking": "BERBICARA",
          "clarifying": "MEMERLUKAN ARAHAN", "interrupted": "TERINTERUPSI", "error": "SUARA BERMASALAH"}


class WorkspaceHUD:
    def __init__(self, main):
        self.main, self.root = main, main.root
        self.nodes, self.edges, self.points = [], [], {}
        self.selected, self.hover, self.path = "leva", None, []
        self.zoom, self.yaw, self.tilt = 1., 0., .12
        self.pan = (0., 0.)
        self.last_frame = time.monotonic()
        self.drag_origin = None
        self.dragged = False
        self.positions = {}
        self.query = tk.StringVar()
        self.flat = tk.BooleanVar(value=False)
        self.rotate = tk.BooleanVar(value=True)
        self.motion = tk.BooleanVar(value=main.preferences.get("animation") != "hemat")
        self.stars = tk.BooleanVar(value=True)
        self.log_rows = []
        self.report_window = None
        self.frame_ms = []
        self.last_voice_description='Suara lokal · kandidat Leva A'
        self.metrics_at=0
        self.layout()
        self.query.trace_add("write", lambda *_: self.search())
        self.root.bind("<Control-k>", lambda _: self.show_workspace())
        self.root.bind("<Control-l>", lambda _: main.entry.focus_set())
        self.after_id = self.root.after(80, self.animate)

    def text(self, parent, text="", **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", PANEL), fg=kw.pop("fg", INK),
                        font=kw.pop("font", ("Segoe UI", 10)), **kw)

    def button(self, parent, text, action, primary=False):
        return tk.Button(parent, text=text, command=action, bg=ACCENT if primary else CARD,
                         fg=BG if primary else INK, activebackground="#284239", activeforeground=INK,
                         bd=0, padx=10, pady=8, cursor="hand2", relief="flat")

    def check(self, parent, text, var):
        return tk.Checkbutton(parent, text=text, variable=var, bg=PANEL, fg=MUTED, selectcolor=CARD,
                              activebackground=PANEL, activeforeground=INK, bd=0)

    def layout(self):
        m = self.main
        style=ttk.Style()
        style.configure('TNotebook',background=BG,borderwidth=0,bordercolor='#203847',lightcolor='#203847',darkcolor='#203847')
        style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(16,9))
        style.map('TNotebook.Tab',background=[('selected',CARD)],foreground=[('selected',ACCENT)])
        self.root.configure(bg=BG)
        self.root.geometry("1340x860")
        self.root.minsize(980, 680)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        header_shell=tk.Frame(self.root,bg=BG,padx=22,pady=12)
        header_shell.grid(row=0,column=0,sticky='ew')
        header=tk.Frame(header_shell,bg=BG);header.pack(fill='x')
        menu_bar=tk.Frame(header_shell,bg=BG);menu_bar.pack(fill='x',pady=(12,0))
        self.text(header, "L E V A", bg=BG, fg=ACCENT, font=("Segoe UI", 24, "bold")).pack(side="left")
        self.text(header, "  /  PERSONAL ASSISTANT", bg=BG, fg=MUTED, font=("Consolas", 10)).pack(side="left", padx=12)
        self.clock = self.text(header, bg=BG, fg=MUTED, font=("Consolas", 10))
        self.clock.pack(side="right", padx=(18, 0))
        m.pause_button = self.button(header, "Jeda", m.toggle_pause)
        m.pause_button.pack(side="right", padx=6)
        self.button(menu_bar, "Pengaturan", m.open_settings).pack(side="right", padx=6)
        self.button(menu_bar, "Voice Packs", m.open_voice_packs).pack(side="right", padx=6)
        self.button(menu_bar, "Memori", m.open_memory).pack(side='right',padx=6)
        self.button(menu_bar, "Skill", m.open_skills).pack(side='right',padx=6)
        self.button(menu_bar, "Pusat", m.open_advanced).pack(side='right',padx=6)
        from task_progress import show_progress
        self.process_button=self.button(menu_bar, 'Proses',lambda:show_progress(m));self.process_button.pack(side='right',padx=4)
        self.button(menu_bar, "Versi Web", m.open_web).pack(side='right',padx=6)
        self.button(menu_bar, "VTuber ↗", lambda:m.open_companion()).pack(side='right',padx=6)

        tabs=ttk.Notebook(self.root)
        self.tabs=tabs
        tabs.grid(row=1,column=0,sticky='nsew',padx=16)
        assistant=tk.Frame(tabs,bg=BG)
        assistant.grid_rowconfigure(0,weight=1)
        assistant.grid_columnconfigure(0,weight=3)
        assistant.grid_columnconfigure(1,weight=7)
        self.assistant_split=ttk.Panedwindow(assistant,orient='horizontal');self.assistant_split.grid(row=0,column=0,columnspan=2,sticky='nsew')
        tabs.add(assistant,text='  Asisten  ')
        body = tk.Frame(tabs, bg=BG)
        tabs.add(body,text='  Ruang kerja & modul  ')
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        left = tk.Frame(body, bg=PANEL, width=224, padx=14, pady=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.pack_propagate(False)
        self.text(left, "EXPLORER", fg=MUTED, font=("Consolas", 10)).pack(anchor="w")
        self.search_entry = tk.Entry(left, textvariable=self.query, bg=CARD, fg=INK, insertbackground=ACCENT,
                                     relief="flat", highlightthickness=1, highlightbackground="#28403f")
        self.search_entry.pack(fill="x", ipady=9, pady=(10, 3))
        self.search_entry.bind("<Return>", lambda _: self.first_match())
        self.text(left, "Cari simpul · Ctrl+K", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self.text(left, "INSPECTOR", fg=MUTED, font=("Consolas", 10)).pack(anchor="w", pady=(18, 8))
        self.selected_label = self.text(left, "Leva", fg=ACCENT, font=("Segoe UI", 13, "bold"), wraplength=190, justify="left")
        self.selected_label.pack(anchor="w")
        self.detail = self.text(left, wraplength=190, justify="left", anchor="nw", fg=MUTED, height=6)
        self.detail.pack(fill="x", pady=8)
        self.action_button = self.button(left, "Tulis perintah", self.invoke, True)
        self.action_button.pack(fill="x")
        self.text(left, "PROFIL CHROME", fg=MUTED, font=("Consolas", 10)).pack(anchor="w", pady=(18, 8))
        profile_frame = tk.Frame(left, bg=PANEL)
        profile_frame.pack(fill="both", expand=True)
        m.listbox = tk.Listbox(profile_frame, bg=PANEL, fg=INK, selectbackground="#26453f", selectforeground=ACCENT,
                              highlightthickness=0, bd=0, exportselection=False, height=5, activestyle="none")
        m.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(profile_frame, command=m.listbox.yview, width=10)
        scrollbar.pack(side="right", fill="y")
        m.listbox.configure(yscrollcommand=scrollbar.set)
        m.listbox.bind("<<ListboxSelect>>", self.profile_selection)
        actions = tk.Frame(left, bg=PANEL)
        actions.pack(fill="x", pady=(8, 4))
        m.open_chrome = self.button(actions, "Chrome", lambda: m.open_profile(False))
        m.open_chrome.pack(side="left", expand=True, fill="x", padx=(0, 4))
        m.open_youtube = self.button(actions, "YouTube", lambda: m.open_profile(True))
        m.open_youtube.pack(side="left", expand=True, fill="x")
        m.refresh_button = self.button(left, "Segarkan profil", m.refresh)
        m.refresh_button.pack(fill="x")

        center = tk.Frame(body, bg=BG)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(1, weight=1)
        map_header = tk.Frame(center, bg=PANEL, padx=14, pady=12)
        map_header.grid(row=0, column=0, sticky="ew")
        self.text(map_header, "PETA RUANG KERJA", fg=ACCENT, font=("Consolas", 10, "bold")).pack(anchor="w")
        self.counts = self.text(map_header, fg=MUTED, font=("Segoe UI", 9))
        self.counts.pack(anchor="w", pady=(4, 0))
        self.canvas = tk.Canvas(center, bg=BG, highlightthickness=1, highlightbackground="#1c2c31", takefocus=True)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.click)
        self.canvas.bind("<Motion>", self.hover_at)
        self.canvas.bind("<Leave>", lambda _: setattr(self, "hover", None))
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Left>", lambda _: self.cycle(-1))
        self.canvas.bind("<Right>", lambda _: self.cycle(1))
        self.canvas.bind("<Return>", lambda _: self.invoke())
        self.canvas.bind("<Home>", lambda _: self.fit())
        controls = tk.Frame(center, bg=PANEL, padx=8, pady=6)
        controls.grid(row=2, column=0, sticky="ew")
        self.check(controls, "2D", self.flat).pack(side="left")
        self.check(controls, "Orbit", self.rotate).pack(side="left")
        self.check(controls, "Bintang", self.stars).pack(side="left")
        self.button(controls, "Fit", self.fit).pack(side="right")
        self.button(controls, "Layar penuh",lambda:self.full_visual('knowledge')).pack(side='right')
        self.text(center, "Klik: detail  ·  Shift+klik: jalur  ·  Tarik: orbit  ·  Roda: zoom",
                  bg=BG, fg=MUTED, font=("Segoe UI", 8)).grid(row=3, column=0, sticky="w", pady=(6, 8))
        events = tk.Frame(center, bg=PANEL, padx=14, pady=12)
        events.grid(row=4, column=0, sticky="ew")
        self.task_title = self.text(events, "AKTIVITAS SESI", fg=ACCENT, font=("Consolas", 10, "bold"))
        self.task_title.pack(anchor="w")
        self.task = self.text(events, "Belum ada permintaan berjalan.", fg=INK, anchor="w", wraplength=400, justify="left")
        self.task.pack(fill="x", pady=(7, 0))
        self.log = tk.Text(events, bg=PANEL, fg=MUTED, height=3, wrap="word", bd=0, highlightthickness=0,
                           state="disabled", font=("Consolas", 9))
        self.log.pack(fill="x", pady=(8, 0))

        voice_panel=tk.Frame(assistant,bg=PANEL,padx=20,pady=20,width=480)
        self.assistant_split.add(voice_panel,weight=3)
        voice_panel.pack_propagate(False)
        top = tk.Frame(voice_panel, bg=PANEL)
        top.pack(fill="x")
        self.text(top, "NEURAL INTERFACE", fg=ACCENT, font=("Consolas", 10)).pack(side="left")
        self.button(top, "Mikrofon lokal ↗", m.open_speech_pipeline).pack(side="right")
        self.button(top, "⛶",lambda:self.full_visual('neural')).pack(side='right',padx=4)
        visual_row=tk.Frame(voice_panel,bg=PANEL)
        visual_row.pack(fill='both',expand=True,pady=(8,0))
        visual_row.grid_columnconfigure(0,weight=1);visual_row.grid_rowconfigure(0,weight=1)
        visual_core=tk.Frame(visual_row,bg=PANEL);visual_core.grid(row=0,column=0,sticky='nsew')
        meter_slot=tk.Frame(visual_row,bg=PANEL,width=112);meter_slot.grid(row=0,column=1,sticky='ns',padx=(8,0))
        meter_slot.grid_propagate(False);meter_slot.pack_propagate(False)
        self.orb = NeuralOrb(visual_core, height=230)
        self.orb.pack(fill="both",expand=True,pady=(8, 0))
        self.voice_status = self.text(visual_core, "SIAP · mikrofon tidak aktif", fg=ACCENT, font=("Consolas", 11))
        self.voice_status.pack(pady=(3, 10))
        self.live_text = self.text(visual_core, "Kandidat Leva A · pilih bahasa suara di bawah", fg=MUTED,
                                   wraplength=300, justify="center", anchor="center", font=("Segoe UI", 10))
        self.live_text.pack(fill="x", pady=(0, 10))
        quick=tk.Frame(voice_panel,bg=PANEL);quick.pack(fill='x',pady=(2,12))
        for label,command in [('ChatGPT','buka Chrome untuk ChatGPT'),('Discord','bukakan Discord'),('Jam','jam berapa sekarang')]:
            self.button(quick,label,lambda value=command:m.send(value)).pack(side='left',expand=True,fill='x',padx=3)
        self.dashboard_task=self.text(voice_panel,'Siap menerima arahan.',fg=INK,wraplength=420,justify='left',anchor='nw',height=2)
        self.dashboard_task.pack(fill='x',pady=(0,6))
        self.metrics=self.text(voice_panel,'',fg=MUTED,font=('Consolas',9),anchor='w')
        self.metrics.pack(fill='x',pady=(2,4))
        self.text(voice_panel,'Suara modular: identitas dan gaya terpisah · GPU dipilih sesuai VRAM',fg=MUTED,wraplength=420,justify='left',font=('Segoe UI',9)).pack(anchor='w')
        right = tk.Frame(assistant, bg=PANEL, padx=20, pady=18)
        self.assistant_split.add(right,weight=7)
        chat_top=tk.Frame(right,bg=PANEL);chat_top.pack(fill='x',pady=(0,12))
        self.text(chat_top,'ASISTEN',fg=ACCENT,font=('Segoe UI',17,'bold')).pack(side='left')
        self.button(chat_top,'Percakapan baru',m.new_conversation).pack(side='right')
        from conversation_export import copy_conversation,save_conversation
        actions=tk.Frame(right,bg=PANEL);actions.pack(fill='x',pady=(0,10))
        self.button(actions,'Salin semua',lambda:copy_conversation(m)).pack(side='left',padx=4)
        self.button(actions,'Simpan laporan',lambda:save_conversation(m)).pack(side='left')
        self.translation_visible=tk.BooleanVar(value=m.preferences.get('show_japanese'))
        self.check(actions,'Teks 日本語',self.translation_visible).pack(side='right')
        self.translation_visible.trace_add('write',lambda *_:self.toggle_translations())
        self.profile_button=self.button(chat_top,'Foto Leva',self.choose_profile)
        self.profile_button.pack(side='right',padx=6)
        from mic_indicator import MicIndicator
        self.mic_indicator=MicIndicator(right,PANEL,INK,MUTED,ACCENT,meter_parent=meter_slot,retry=m.retry_local_mic,
                                        arm=m.arm_local_mic,history=m.open_speech_log,dictate=m.toggle_dictation)
        self.mic_indicator.frame.pack_forget()
        def toggle_mic_detail():
            if self.mic_indicator.frame.winfo_manager():self.mic_indicator.frame.pack_forget()
            else:self.mic_indicator.frame.pack(fill='x',pady=(0,7),before=history_frame)
        self.button(actions,'Mikrofon & transkrip',toggle_mic_detail).pack(side='left',padx=6)
        history_frame = tk.Frame(right, bg=PANEL)
        history_frame.pack(fill="both", expand=True)
        m.history = tk.Text(history_frame, wrap="word", bg=PANEL, fg=INK, relief="flat", padx=4, pady=4,
                            state="disabled", highlightthickness=0, selectbackground="#35556b", font=("Segoe UI", 11))
        m.history.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(history_frame, command=m.history.yview, width=10)
        scroll.pack(side="right", fill="y")
        m.history.configure(yscrollcommand=scroll.set)
        for tag, col in [("Leva", ACCENT), ("Anda", "#a6c5ff"), ("Info", MUTED), ("AI", "#cdbbff")]:
            m.history.tag_configure(tag, foreground=col, font=("Segoe UI", 10, "bold"), spacing1=8, spacing3=4)
        m.history.tag_configure("body", spacing3=20)
        m.history.tag_configure('assistant_align',justify='right',lmargin1=65,lmargin2=65,rmargin=16,background='#132c2c')
        m.history.tag_configure('user_align',justify='left',lmargin1=16,lmargin2=16,rmargin=65,background='#142634')
        from conversation_export import install_menu
        install_menu(m,m.history)
        self.profile_revision=None;self.profile_photo=None
        self.refresh_profile()

        bottom = tk.Frame(self.root, bg=BG, padx=16, pady=12)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        composer = tk.Frame(bottom, bg=CARD, padx=12, pady=6)
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(1, weight=1)
        self.text(composer, "›", bg=CARD, fg=ACCENT, font=("Consolas", 22)).grid(row=0, column=0, padx=(0, 10))
        m.entry = tk.Entry(composer, bg=CARD, fg=INK, insertbackground=ACCENT, relief="flat",
                           disabledbackground=CARD, disabledforeground=MUTED, font=("Segoe UI", 12))
        m.entry.grid(row=0, column=1, sticky="ew", ipady=9)
        m.entry.bind("<Return>", lambda _: m.send())
        from room_ui import attach_file
        self.button(composer,'＋',lambda:attach_file(m)).grid(row=0,column=2,padx=8)
        m.attachment_label=tk.StringVar(value='')
        self.text(bottom,'',bg=BG,fg=MUTED,textvariable=m.attachment_label).grid(row=4,column=0,sticky='w')
        m.send_button = self.button(composer, "Kirim ↗", m.send, True)
        m.send_button.grid(row=0, column=3, padx=(10, 0))
        routebar = tk.Frame(bottom,bg=BG)
        routebar.grid(row=1,column=0,sticky='ew',pady=(8,0))
        toolbar = tk.Frame(bottom, bg=BG)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        from pipeline_routing import VOICE_SINGLE as SINGLE_CHOICES,VOICE_DUAL as DUAL_CHOICES
        self.text(routebar,'Rute suara',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='left',padx=(0,5))
        m.provider = ttk.Combobox(routebar, textvariable=m.mode, values=DUAL_CHOICES if m.dual.get() else SINGLE_CHOICES, state="readonly", width=31)
        m.provider.pack(side="left", padx=(0, 10))
        m.dual_check = tk.Checkbutton(routebar, text="Dua GPU suara", variable=m.dual, bg=BG, fg=MUTED, selectcolor=CARD,
                                      activebackground=BG, activeforeground=INK, bd=0)
        m.dual_check.pack(side="left")
        self.button(routebar,'Suara & agent',m.open_speech_pipeline).pack(side='left',padx=5)
        self.pipeline_summary=self.text(routebar,'',bg=BG,fg=MUTED,font=('Segoe UI',9))
        self.pipeline_summary.pack(side='left',padx=8)
        self.button(toolbar, "Lepaskan AI", m.release).pack(side="left", padx=8)
        self.button(toolbar, "Ulangi rute agent", m.retry_online).pack(side="left")
        # Experimental lab remains available through the workspace, outside the daily route selector.
        self.check(toolbar,'Jawaban suara',m.spoken_replies).pack(side='left')
        self.button(toolbar,'Stop suara',m.stop_reply_voice).pack(side='left',padx=6)
        self.text(toolbar,'Suara',bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(side='left',padx=(5,4))
        m.language_picker=ttk.Combobox(toolbar,textvariable=m.speech_language,values=('Indonesia','日本語'),state='readonly',width=10)
        m.language_picker.pack(side='left')
        self.check(toolbar, "Animasi", self.motion).pack(side="right")
        status = tk.Frame(bottom, bg=BG)
        status.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        tk.Label(status, textvariable=m.status, bg=BG, fg=ACCENT, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(status, textvariable=m.activity, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

        from room_ui import add_room_tabs
        add_room_tabs(self,tabs)

    def toggle_translations(self):
        visible=self.translation_visible.get();self.main.preferences.set('show_japanese',visible)
        for view in getattr(self.main,'room_views',{'assistant':self.main.history}).values():view.tag_configure('spoken_translation',elide=not visible)

    def choose_profile(self):
        from tkinter import filedialog,messagebox
        from profile_avatar import ProfileAvatar,MAX_UPLOAD
        from pathlib import Path
        name=filedialog.askopenfilename(parent=self.root,title='Foto profil Leva · tersinkron ke web dan HP',filetypes=[('Foto','*.png *.jpg *.jpeg *.webp')])
        if not name:return
        try:
            if Path(name).stat().st_size>MAX_UPLOAD:raise ValueError('Foto maksimal 5 MB.')
            from avatar_editor import edit_avatar
            edit_avatar(self.root,Path(name).read_bytes(),self.refresh_profile)
        except (OSError,ValueError) as error:messagebox.showerror('Foto Leva',str(error),parent=self.root)

    def refresh_profile(self):
        from profile_avatar import ProfileAvatar
        from PIL import Image,ImageTk
        import io
        store=ProfileAvatar();revision=store.metadata()['revision']
        if revision==getattr(self,'profile_revision',None):return
        self.profile_revision=revision
        raw=store.read()
        try:
            if raw:image=Image.open(io.BytesIO(raw)).resize((28,28))
            else:
                from PIL import ImageDraw
                image=Image.new('RGBA',(28,28),'#143c40');ImageDraw.Draw(image).text((11,7),'L',fill='#b9f1df')
            if self.profile_photo:self.profile_photo.paste(image)
            else:self.profile_photo=ImageTk.PhotoImage(image,master=self.root)
            self.profile_button.configure(image=self.profile_photo,compound='left',text=' Foto Leva')
        except (OSError,ValueError):pass

    def full_visual(self,mode):
        if getattr(self,'visual_window',None) and self.visual_window.winfo_exists():
            self.visual_window.lift();return
        win=tk.Toplevel(self.root);self.visual_window=win;win.title('Leva · '+('Neural' if mode=='neural' else 'Pengetahuan'));win.configure(bg=BG)
        win.attributes('-fullscreen',True)
        bar=tk.Frame(win,bg=PANEL,padx=14,pady=10);bar.pack(fill='x')
        self.text(bar,'LEVA / '+mode.upper()+' · Tarik: rotasi · Roda: zoom · Esc: kembali').pack(side='left')
        previous=self.canvas;timer=None
        def close(event=None):
            nonlocal timer
            if timer:
                try:win.after_cancel(timer)
                except tk.TclError:pass
            if mode=='knowledge':self.canvas=previous;self.drag_origin=None
            win.destroy();self.visual_window=None
        self.button(bar,'Kembali ×',close).pack(side='right');win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',close)
        if mode=='neural':
            orb=NeuralOrb(win);orb.pack(fill='both',expand=True)
            def sync():
                nonlocal timer
                if not win.winfo_exists():return
                for name in ('mode','input_level','output_level','motion_enabled','economy'):setattr(orb,name,getattr(self.orb,name))
                timer=win.after(100,sync)
            sync()
        else:
            self.flat.set(False);self.canvas=tk.Canvas(win,bg=BG,highlightthickness=0);self.canvas.pack(fill='both',expand=True)
            for event,fn in [('<ButtonPress-1>',self.press),('<B1-Motion>',self.drag),('<ButtonRelease-1>',self.click),('<Motion>',self.hover_at),('<MouseWheel>',self.wheel)]:self.canvas.bind(event,fn)
        win.focus_set()

    def update_inventory(self):
        self.nodes, self.edges = inventory(self.main.profile_rows)
        self.points = coordinates(self.nodes)
        if not any(n.id == self.selected for n in self.nodes):
            self.selected = "leva"
        self.path = []
        self.search()
        self.select(self.selected)

    def show_workspace(self):
        self.tabs.select(3)
        self.search_entry.focus_set()

    def search(self):
        self.visible, self.visible_edges = filtered(self.nodes, self.edges, self.query.get())
        self.counts.configure(text=f"{len(self.visible)} / {len(self.nodes)} simpul · {len(self.visible_edges)} relasi modul / profil")

    def first_match(self):
        if self.visible:
            self.select(self.visible[0].id)
        self.canvas.focus_set()

    def select(self, ident, trace=False):
        if trace:
            self.path = shortest_path(self.edges, self.selected, ident)
        else:
            self.path = []
        self.selected = ident
        node = next((n for n in self.nodes if n.id == ident), None)
        if not node:
            return
        self.selected_label.configure(text=node.label, fg=COLORS[node.group])
        self.detail.configure(text=node.detail)
        self.action_button.configure(text={"chat": "Tulis perintah", "profiles": "Pilih profil", "profile": "Buka profil",
                                           "voice": "Buka panel suara", "duplex": "Buka Duplex Lab", "settings": "Buka pengaturan",
                                           "report": "Baca dokumen"}[node.action])
        if node.group == "profile":
            for index, profile in enumerate(self.main.profile_rows):
                if profile["id"] == node.target:
                    self.main.listbox.selection_clear(0, "end")
                    self.main.listbox.selection_set(index)
                    self.main.listbox.see(index)
                    break

    def profile_selection(self, _):
        selected = self.main.listbox.curselection()
        if selected:
            self.select("profile:" + self.main.profile_rows[selected[0]]["id"])

    def invoke(self):
        node = next((n for n in self.nodes if n.id == self.selected), None)
        if not node:
            return
        m = self.main
        if node.action == "chat":
            m.entry.focus_set()
        elif node.action == "profiles":
            m.listbox.focus_set()
        elif node.action == "profile":
            m.send("buka Chrome profil " + node.target, display="buka Chrome profil " + node.label)
        elif node.action == "voice":
            m.open_voice()
        elif node.action == "duplex":
            m.open_duplex()
        elif node.action == "settings":
            m.open_settings()
        elif node.action == "report":
            self.open_report(node.target)

    def open_report(self, ident):
        if ident not in REPORTS:
            return
        label, filename = REPORTS[ident]
        try:
            content = (ROOT / filename).read_text(encoding="utf-8-sig")[:120000]
        except (OSError, UnicodeError):
            self.main.add("Info", "Dokumen belum tersedia: " + filename)
            return
        if self.report_window and self.report_window.winfo_exists():
            self.report_window.destroy()
        window = self.report_window = tk.Toplevel(self.root)
        window.title("Leva — " + label)
        window.geometry("850x680")
        window.configure(bg=PANEL)
        self.text(window, label, fg=ACCENT, font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=22, pady=(20, 5))
        self.text(window, "Sumber lokal: " + filename, fg=MUTED).pack(anchor="w", padx=22)
        pane = tk.Frame(window, bg=PANEL)
        pane.pack(fill="both", expand=True, padx=22, pady=18)
        text = tk.Text(pane, bg=BG, fg=INK, wrap="word", padx=20, pady=18, bd=0, font=("Segoe UI", 11))
        text.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(pane, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", content)
        text.configure(state="disabled")
        self.button(window, "Tutup dokumen", window.destroy).pack(anchor="e", padx=22, pady=(0, 16))

    def note(self, speaker, text):
        if speaker in {"Anda", "Info"} or speaker.startswith("Leva"):
            row = datetime.now(WIB).strftime("%H:%M:%S") + "  " + speaker + " · " + " ".join(text.split())[:130]
            self.log_rows.append(row)
            self.log_rows = self.log_rows[-24:]
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("end", "\n".join(self.log_rows))
            self.log.configure(state="disabled")
            self.log.see("end")

    def task_state(self, text, state):
        self.task_title.configure(text="PERMINTAAN / " + state, fg="#f7c66d" if state == "BERJALAN" else ACCENT)
        self.task.configure(text=" ".join(text.split())[:130])
        if hasattr(self,'dashboard_task'):self.dashboard_task.configure(text=' · '+state+'\n'+ ' '.join(text.split())[:160])

    def tool_result(self,name,status,reply):
        label={'done':'TERVERIFIKASI','unverified':'BELUM TERKONFIRMASI','failed':'GAGAL','needs_input':'MENUNGGU PILIHAN'}.get(status,status.upper())
        self.dashboard_task.configure(text=name+' · '+label+'\n'+reply[:160])
        self.note('Info',name+' · '+label+' · '+reply)

    def sync(self):
        from room_ui import sync_room_controls
        sync_room_controls(self.main)
        self.refresh_profile()
        m = self.main
        voice = m.voice_window
        active = bool(voice and not voice.closed and voice.service.active)
        source = voice.orb if active else None
        state = assistant_state(m.desktop.paused or m.desktop.sleeping, m.busy, active,
                                source.mode if source else "idle", source.preview if source else False)
        pack = getattr(m, "voice_pack_window", None)
        pack_active = bool(pack and pack.service.active)
        reply=getattr(m,'reply_voice',None)
        from conversation_stream import voice_active,output_service
        reply_active=bool(reply and reply.active) or voice_active(m)
        local=getattr(m,'local_mic',None)
        local_active=bool(local and local.active)
        from mic_indicator import MicTelemetry
        meter=local.telemetry.snapshot(active=local_active) if local and hasattr(local,'telemetry') else MicTelemetry().snapshot(active=False)
        google={'level':source.input_level,'text':voice.last_text} if active and voice.mic_open else None
        output={'state':'off','rms_db':-80.,'peak_db':-80.}
        if active:
            output={'state':'relative','level':source.output_level,'rms_db':0,'peak_db':0}
        else:
            service=output_service(m) if reply_active else pack.service if pack_active else None
            if service and hasattr(service,'output_telemetry'):
                output=service.output_telemetry.snapshot(playing=service.playing)
        output['device']=m.preferences.get('output_device_name')
        self.mic_indicator.update(meter,notice=getattr(m,'local_notice',''),google=google,output=output)
        if local_active and not m.busy and not active and not reply_active:state='connecting' if local.state=='loading' else 'listening'
        if local_active and not m.busy and not active and not reply_active:
            if meter['phase'] in ('transcribing','collecting'):state='thinking'
            elif meter['reason'] in ('awaiting_wake','incomplete') and meter['text'] and not meter.get('awake'):state='clarifying'
        if pack_active and not active and not (m.desktop.paused or m.desktop.sleeping):
            state = pack.service.state
        if reply_active and not active and not (m.desktop.paused or m.desktop.sleeping):state=m.live_speech.progress()['state'] if voice_active(m) else reply.state
        self.orb.set_state(state)
        self.orb.input_level = source.input_level if source else local.input_level if local_active else 0
        self.orb.output_level = source.output_level if source else getattr(output_service(m),'output_level',0) if reply_active else getattr(pack.service,'output_level',0) if pack_active else 0
        self.orb.motion_enabled = self.motion.get()
        self.orb.economy = not self.motion.get() or m.preferences.get("animation") == "hemat"
        self.voice_status.configure(text=LABELS.get(state, state.upper()))
        if active:
            heard = voice.heard.cget("text")[-150:]
            said = voice.said.cget("text")[-150:]
            self.live_text.configure(text=heard + "\n" + said)
        elif reply_active or pack_active:
            actual=reply.actual if reply_active else pack.service.actual_pack
            self.live_text.configure(text=self.last_voice_description+('\nMikrofon lokal tetap mendengar · interupsi aktif' if local_active else '\nMikrofon mati · keluaran suara per potongan'))
        elif local_active:
            self.live_text.configure(text=(m.local_partial or m.local_notice)+'\nAudio lokal · sebut Leva atau tekan Terima perintah')
        else:
            from speech_resources import ASR_CHOICES
            from pipeline_routing import route_spec
            if route_spec(m.mode.get(),m.dual.get())['mode']=='commands':caption='Tanpa AI · ketik perintah langsung'
            else:
                pack=m.preferences.get('target_voice_pack')
                tts='Higgs' if pack.startswith('higgs_') else 'OmniVoice' if pack.startswith('omnivoice_') else 'Piper/Kokoro · kandidat lama'
                from speech_configuration import configuration_snapshot
                placement=configuration_snapshot(m.preferences,route_spec(m.mode.get(),m.dual.get()))
                caption=placement['summary']+' · keluaran '+tts
            self.live_text.configure(text=caption+'\nCtrl+L untuk menulis · pengaturan pada Suara & agent')
        from speech_configuration import configuration_snapshot
        from pipeline_routing import route_spec
        self.pipeline_summary.configure(text=configuration_snapshot(m.preferences,route_spec(m.mode.get(),m.dual.get()))['summary'])
        clients=getattr(m,'remote_clients',[])
        badge=' · HP' if getattr(m,'remote_control_active',False) else ' · Web' if clients else ''
        if getattr(m,'remote_control_active',False) and not reply_active and not active:
            self.live_text.configure(text='HP tersambung · mic laptop dijeda\nMic HP hanya saat tombol ditahan · transkrip diperiksa sebelum dikirim')
        self.clock.configure(text=datetime.now(WIB).strftime("%H:%M  WIB") + "  ·  v0.43.0"+badge)
        if time.monotonic()-self.metrics_at>2:
            data=getattr(m,'hardware',None)
            value=data.value if data else {}
            rows=[f"CPU {value.get('cpu_percent',0):.0f}% · RAM {value.get('ram_used_gib',0):.1f}/{value.get('ram_total_gib',0):.1f} GiB"]
            for gpu in value.get('gpus',[])[:2]:
                name='4050' if '4050' in gpu['name'] else '5070' if '5070' in gpu['name'] else gpu['name'][:12]
                rows.append(f"RTX {name} · {gpu['used_mib']}/{gpu['total_mib']} MiB · {gpu['temperature_c']}°C · {gpu.get('sm_clock_mhz','?')}MHz")
            reaction=getattr(m,'last_reaction_ms',None);text=getattr(m,'last_text_ms',None)
            if reaction is not None:rows.append(f"Reaksi {reaction:.0f} ms"+(f" · hasil teks {text/1000:.2f} s" if text is not None else ''))
            self.metrics.configure(text='\n'.join(rows))
            self.metrics_at=time.monotonic()

    def fit(self):
        self.zoom, self.yaw, self.tilt = 1., 0., .12
        self.pan = (0., 0.)

    def wheel(self, event):
        self.zoom = max(.5, min(2.6, self.zoom * (1.10 if event.delta > 0 else 1 / 1.10)))

    def press(self, event):
        self.canvas.focus_set()
        self.drag_origin = (event.x, event.y, self.yaw, self.tilt, self.pan)
        self.dragged = False

    def drag(self, event):
        if self.drag_origin:
            x, y, yaw, tilt, pan = self.drag_origin
            if abs(event.x - x) + abs(event.y - y) > 4:
                self.dragged = True
                if self.flat.get():
                    self.pan = (pan[0] + event.x - x, pan[1] + event.y - y)
                else:
                    self.yaw = yaw + (event.x - x) * .007
                    self.tilt = max(-1., min(1., tilt + (event.y - y) * .007))

    def nearest(self, x, y):
        found = [(math.hypot(x - px, y - py), ident) for ident, (px, py, _) in self.positions.items()]
        distance, ident = min(found, default=(1000, None))
        return ident if distance < 24 else None

    def hover_at(self, event):
        self.hover = self.nearest(event.x, event.y)
        self.canvas.configure(cursor="hand2" if self.hover else "fleur")

    def click(self, event):
        if not self.dragged:
            ident = self.nearest(event.x, event.y)
            if ident:
                self.select(ident, bool(event.state & 1))
        self.drag_origin = None

    def cycle(self, step):
        ids = [n.id for n in self.visible]
        if ids:
            index = ids.index(self.selected) if self.selected in ids else -1
            self.select(ids[(index + step) % len(ids)])
        return "break"

    def animate(self):
        if self.main.closed:
            return
        now = time.monotonic()
        delta = min(now - self.last_frame, .2)
        self.last_frame = now
        if self.root.state() != "iconic" and self.canvas.winfo_viewable():
            started = time.perf_counter()
            if self.motion.get() and self.rotate.get() and not self.drag_origin and not self.flat.get() and not self.main.desktop.sleeping and not self.main.desktop.paused:
                self.yaw += delta * .055
            self.draw()
            self.frame_ms.append((time.perf_counter() - started) * 1000)
            self.frame_ms = self.frame_ms[-120:]
        interval = 100 if self.motion.get() and self.main.preferences.get("animation") != "hemat" else 400
        if self.main.desktop.sleeping or self.main.desktop.paused or self.root.state() == "iconic":
            interval = 1000
        self.after_id = self.root.after(interval, self.animate)

    def draw(self):
        c = self.canvas
        width, height = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.delete("all")
        if self.stars.get():
            for i in range(320):
                angle=i*2.399963;u=1-2*((i*.61803398875)%1);r=((i*.754877666)%1)**(1/3)*1.5
                ring=math.sqrt(max(0,1-u*u));pos=(math.cos(angle)*ring*r,u*r,math.sin(angle)*ring*r)
                x,y,z=project(pos,self.yaw,self.tilt,self.zoom,width,height,self.flat.get())
                if 0<x<width and 0<y<height:
                    radius=.5+(z+1.5)*.22;c.create_oval(x,y,x+radius*2,y+radius*2,fill='#72909d' if i%7 else '#9b80ac',outline='')
        for ring in (.25, .42):
            radius = min(width, height) * ring
            c.create_oval(width / 2 - radius, height / 2 - radius, width / 2 + radius, height / 2 + radius, outline="#132028", dash=(2, 8))
        self.positions = {}
        for node in self.visible:
            x, y, z = project(self.points[node.id], self.yaw, self.tilt, self.zoom, width, height, self.flat.get())
            self.positions[node.id] = (x + self.pan[0], y + self.pan[1], z)
        traced = {frozenset(pair) for pair in zip(self.path, self.path[1:])}
        for a, b in self.visible_edges:
            x, y, _ = self.positions[a]
            x2, y2, _ = self.positions[b]
            active = self.selected in (a, b)
            color = "#f7c66d" if frozenset((a, b)) in traced else "#3e7665" if active else "#21353e"
            c.create_line(x, y, x2, y2, fill=color, width=2 if active else 1)
        for node in sorted(self.visible, key=lambda n: self.positions[n.id][2]):
            x, y, _ = self.positions[node.id]
            selected = node.id == self.selected
            radius = 13 if node.group == "core" else 8 if node.group == "module" else 5
            color = COLORS[node.group]
            if selected or node.id == self.hover:
                c.create_oval(x - radius - 6, y - radius - 6, x + radius + 6, y + radius + 6, outline=color)
            c.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=BG, width=2)
            if selected or node.id == self.hover or node.group in {"core", "module"} or self.query.get():
                c.create_text(x, y + radius + 13, text=node.label[:26], fill=INK if selected else MUTED, font=("Segoe UI", 9))
        if not self.visible:
            c.create_text(width / 2, height / 2, text="Tidak ada simpul yang cocok.\nUbah pencarian di Explorer.", fill=MUTED, justify="center")
        c.create_text(14, height - 18, anchor="w", text="LEVA  /  " + ("2D" if self.flat.get() else "SPATIAL") + "  /  MODUL & PROFIL LOKAL", fill="#536b77", font=("Consolas", 8))
