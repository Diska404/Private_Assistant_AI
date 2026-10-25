"""User-facing settings and inspectable local habit memory."""
import tkinter as tk
from tkinter import ttk
import sqlite3
from datetime import datetime, timezone

from hybrid_engine import DEFAULT_MODEL, DEFAULT_SERVER
from preferences import MODES
from command_resolution import WIB
from gui import BG, PANEL, CARD, INK, MUTED, ACCENT


class SettingsWindow:
    def __init__(self, main):
        self.main = main
        self.window = tk.Toplevel(main.root)
        self.window.title("Leva — Pengaturan & Memori")
        self.window.geometry("940x900")
        self.window.minsize(860, 800)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.notice = tk.StringVar(value="Pengaturan dan hitungan kebiasaan disimpan lokal di D.")
        self.provider = tk.StringVar(value=main.preferences.get("provider"))
        self.dual = tk.BooleanVar(value=main.preferences.get("dual_gpu"))
        self.learn = tk.BooleanVar(value=main.preferences.get("learn_habits"))
        self.animation = tk.StringVar(value=main.preferences.get("animation"))
        self.acceleration=tk.StringVar(value=main.preferences.get('saluki_acceleration'))
        self.warm=tk.BooleanVar(value=main.preferences.get('keep_models_warm'))
        main.label(self.window, "Pengaturan & Memori", bg=BG, font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=24, pady=(20,12))
        main.button(self.window,'Hubungkan Android',main.open_remote).place(relx=1,x=-24,y=18,anchor='ne')
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=24)
        general = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        memory = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        diagnostics = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        notebook.add(general, text="Umum")
        notebook.add(memory, text="Profil & Kebiasaan")
        notebook.add(diagnostics, text="Status sistem")
        streaming=tk.Frame(notebook,bg=PANEL,padx=22,pady=18);notebook.add(streaming,text='Streaming percakapan')
        self.streaming_text=tk.BooleanVar(value=main.preferences.get('streaming_text'))
        self.realtime_speech=tk.BooleanVar(value=main.preferences.get('realtime_speech'))
        self.native_voice_stream=tk.BooleanVar(value=main.preferences.get('native_voice_stream'))
        self.check(streaming,'Tampilkan teks model lokal secara bertahap',self.streaming_text)
        self.check(streaming,'Suara per frasa sambil menyiapkan frasa berikutnya · eksperimen Higgs',self.realtime_speech)
        self.check(streaming,'PCM awal dari engine Higgs · eksperimen tambahan',self.native_voice_stream)
        self.caption(streaming,'Identitas voice pack dan bahasa tetap mengikuti pilihan Anda. Suara eksperimen memerlukan RTX 5070 dengan VRAM cukup; tidak memindahkan model secara diam-diam. Terjemahan Jepang dapat menunggu model percakapan selesai. PCM awal belum terbukti lebih cepat pada profil GPU saat ini.',muted=True)
        def save_streaming():
            if main.busy:self.notice.set('Tunggu jawaban selesai sebelum mengubah streaming.');return
            main.stop_reply_voice();main.cancel_inference()
            main.preferences.set_many({'streaming_text':self.streaming_text.get(),'realtime_speech':self.realtime_speech.get(),'native_voice_stream':self.native_voice_stream.get()})
            self.notice.set('Opsi streaming tersimpan untuk app, web, dan HP. Suara lama tetap tersedia dengan mematikan dua opsi eksperimen.')
        main.button(streaming,'Simpan opsi streaming',save_streaming,primary=True).pack(anchor='w',pady=16)
        persona=tk.Frame(notebook,bg=PANEL,padx=22,pady=18);notebook.add(persona,text='Persona & Siaga')
        from presence_companion import settings,apply_settings
        value=settings(main)
        self.companion_idle=tk.BooleanVar(value=value['companion_idle']);self.companion_playful=tk.BooleanVar(value=value['companion_playful']);self.companion_delay=tk.StringVar(value=value['companion_idle_delay'])
        self.caption(persona,'Sapaan khusus Asisten, Chat dan Secret')
        self.check(persona,'Sapaan ringan ketika diam di Leva',self.companion_idle)
        self.check(persona,'Gaya playful: ~, desu, gurauan ringan dan 💗 sesekali',self.companion_playful)
        self.caption(persona,'Jeda awal (detik; diacak ±25%)')
        ttk.Combobox(persona,textvariable=self.companion_delay,values=('120','300','600'),state='readonly',width=14).pack(anchor='w',pady=8)
        self.caption(persona,'Maksimal 2 sapaan tanpa balasan, jeda lanjutan 10–15 menit, maksimal 4 per jam. Hanya ketika jendela/halaman Leva aktif; ditahan saat ada tugas, draf, rekaman, suara, atau jeda. Saat AFK suara hanya memakai klip yang sudah tersimpan, tanpa memuat model GPU baru.',muted=True)
        self.caption(persona,'Asisten boleh memeriksa daftar jendela secara read-only untuk menawarkan bantuan. Chat dan Secret tidak memeriksa aplikasi. Sapaan tidak membuka aplikasi atau mengirim perintah sendiri.',muted=True)
        def save_persona():
            try:
                apply_settings(main,{'companion_idle':self.companion_idle.get(),'companion_playful':self.companion_playful.get(),'companion_idle_delay':self.companion_delay.get()})
                self.notice.set('Pengaturan sapaan tersimpan untuk desktop, web dan HP.')
            except (OSError,sqlite3.Error,ValueError):self.notice.set('Pengaturan sapaan belum tersimpan.')
        main.button(persona,'Simpan sapaan & siaga',save_persona,primary=True).pack(anchor='w',pady=16)

        self.caption(general, "Rute percakapan — pilihan GPU terpisah dari model agent")
        from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,visible_route
        self.route_picker=ttk.Combobox(general, textvariable=self.provider, values=DUAL_CHOICES if self.dual.get() else SINGLE_CHOICES, state="readonly", width=38)
        self.route_picker.pack(anchor="w", pady=(6,14))
        self.check(general, "Dua GPU untuk fallback percakapan lokal", self.dual)
        def changed(*_):
            self.route_picker.configure(values=DUAL_CHOICES if self.dual.get() else SINGLE_CHOICES)
            self.provider.set(visible_route(self.provider.get(),self.dual.get(),main.last_single_gpu))
        self.dual.trace_add('write',changed)
        main.button(general,'Model suara & agent pelaksana',main.open_speech_pipeline).pack(anchor='w',pady=6)
        self.check(general,'Siaga cepat 2 menit · menyimpan model di VRAM; Jeda/Lepaskan AI langsung melepasnya',self.warm)
        self.caption(general,'Akselerasi agent Saluki · GPU agent diatur terpisah; auto memakai hasil benchmark')
        ttk.Combobox(general,textvariable=self.acceleration,values=('auto','plain','mtp','dflash'),state='readonly',width=18).pack(anchor='w',pady=5)
        self.check(general, "Pelajari pilihan profil dari permintaan yang berhasil dikirim", self.learn)
        self.caption(general, "Setelah minimal 3 penggunaan dengan pilihan dominan, Leva menawarkan profil dan menunggu jawaban.\nHanya jenis tugas, ID profil dan hitungan yang dicatat; tidak menyimpan isi chat atau audio.", muted=True)
        self.caption(general, "Animasi HUD dan Neural Voice")
        ttk.Combobox(general, textvariable=self.animation, values=("normal","hemat"), state="readonly", width=18).pack(anchor="w", pady=(7,14))
        self.caption(general, "Hemat membatasi graf HUD sekitar 2,5 fps dan orb aktif sekitar 10 fps.\nPendengar lokal dan perangkat audio mengikuti pengaturan Pusat.\nGoogle Live adalah panel lama opsional (Tidak Direkomendasikan); input utama memakai ASR lokal.", muted=True)
        main.button(general, "Simpan pengaturan", self.save, primary=True).pack(anchor="w", pady=16)
        main.button(general, "Percakapan baru", self.new_conversation).pack(anchor="w")
        self.caption(general, "Percakapan baru membersihkan konteks sesi teks/suara; catatan kebiasaan tetap ada.", muted=True)
        main.button(general, "Voice Pack Manager", main.open_voice_packs).pack(anchor="w", pady=8)

        self.caption(memory, "Alias profil yang Anda tetapkan")
        profile_labels = {p["name"] + " · " + p["id"]: p["id"] for p in main.desktop.profiles.values()}
        self.profile_labels = profile_labels
        self.profile = tk.StringVar(value=next(iter(profile_labels), ""))
        ttk.Combobox(memory, textvariable=self.profile, values=list(profile_labels), state="readonly", width=70).pack(fill="x", pady=(6,8))
        row=tk.Frame(memory,bg=PANEL)
        row.pack(fill="x")
        self.alias=tk.Entry(row,bg=CARD,fg=INK,insertbackground=ACCENT,relief="flat",font=("Segoe UI",11))
        self.alias.pack(side="left",fill="x",expand=True,ipady=10,padx=(0,10))
        main.button(row,"Tambahkan alias",self.add_alias).pack(side="right")
        self.aliases=tk.Listbox(memory,bg=CARD,fg=INK,selectbackground="#284b54",height=4,bd=0,highlightthickness=0,exportselection=False)
        self.aliases.pack(fill="x",pady=8)
        main.button(memory,"Hapus alias terpilih",self.remove_alias).pack(anchor="w",pady=(0,10))
        self.caption(memory,"Catatan penggunaan · permintaan terkirim dengan jendela baru terdeteksi")
        self.records=tk.Listbox(memory,bg=CARD,fg=INK,height=6,bd=0,highlightthickness=0)
        self.records.pack(fill="both",expand=True,pady=8)
        tools=tk.Frame(memory,bg=PANEL)
        tools.pack(fill="x")
        main.button(tools,"Segarkan catatan",self.refresh).pack(side="left")
        main.button(tools,"Hapus semua kebiasaan",self.forget).pack(side="right")

        self.status_text=tk.Label(diagnostics,text="",bg=PANEL,fg=INK,justify="left",anchor="nw",wraplength=820,font=("Segoe UI",11))
        self.status_text.pack(fill="both",expand=True)
        main.button(diagnostics,"Periksa status",self.refresh_status).pack(anchor="w",pady=12)
        tk.Label(self.window,textvariable=self.notice,bg=BG,fg=ACCENT,wraplength=880,anchor="w",justify="left").pack(fill="x",padx=24,pady=14)
        self.refresh()
        self.refresh_status()

    def caption(self,parent,text,muted=False):
        tk.Label(parent,text=text,bg=PANEL,fg=MUTED if muted else INK,justify="left",anchor="w",wraplength=820).pack(anchor="w",pady=(5,8))

    def check(self,parent,text,var):
        tk.Checkbutton(parent,text=text,variable=var,bg=PANEL,fg=INK,selectcolor=CARD,activebackground=PANEL,activeforeground=INK,bd=0).pack(anchor="w",pady=5)

    def save(self):
        if self.main.busy:self.notice.set('Tunggu tugas selesai sebelum mengganti pengaturan.');return
        try:
            changed_warm=self.main.preferences.get('keep_models_warm')!=self.warm.get()
            if changed_warm and self.main.busy:
                self.notice.set('Tunggu chat selesai sebelum mengganti kebijakan siaga.');return
            self.main.preferences.set_many({"provider":self.provider.get(),"dual_gpu":self.dual.get(),"learn_habits":self.learn.get(),"animation":self.animation.get(),'saluki_acceleration':self.acceleration.get(),'keep_models_warm':self.warm.get()})
            if changed_warm:self.main.apply_warm_policy()
            self.main.mode.set(self.provider.get())
            self.main.dual.set(self.dual.get())
            if self.main.voice_window:
                self.main.voice_window.orb.economy=self.animation.get()=="hemat"
            self.notice.set("Pengaturan disimpan. Permintaan yang sedang berjalan memakai pilihan sebelumnya." if self.main.preferences.persistent else self.main.preferences.warning)
        except (OSError,sqlite3.Error,ValueError):
            self.notice.set("Pengaturan belum tersimpan. Periksa ketersediaan folder data di D.")

    def refresh(self):
        try:
            self._refresh()
        except (OSError,sqlite3.Error):
            self.notice.set("Catatan lokal belum dapat dibaca. Periksa ketersediaan folder data di D.")

    def _refresh(self):
        self.alias_rows=list(self.main.preferences.aliases().items())
        self.aliases.delete(0,"end")
        profiles=self.main.desktop.profiles
        for alias,pid in self.alias_rows:
            self.aliases.insert("end",alias+" → "+profiles.get(pid,{}).get("name",pid))
        self.records.delete(0,"end")
        for record in self.main.preferences.habits():
            stamp=datetime.fromisoformat(record["last_used"]).replace(tzinfo=timezone.utc).astimezone(WIB).strftime("%d-%m %H.%M WIB")
            self.records.insert("end",f"{record['action']} · {profiles.get(record['profile_id'],{}).get('name',record['profile_id'])} · {record['uses']} kali · {stamp}")
        if not self.records.size():
            self.records.insert("end","Belum ada kebiasaan. Leva akan bertanya sampai ada pilihan yang cukup konsisten.")

    def add_alias(self):
        if self.main.busy:
            self.notice.set("Tunggu permintaan selesai sebelum mengubah alias.")
            return
        try:
            self.main.desktop.add_alias(self.alias.get(),self.profile_labels.get(self.profile.get()))
            self.alias.delete(0,"end")
            self.refresh()
            self.notice.set("Alias disimpan dan dapat langsung dipakai pada perintah Chrome/YouTube.")
        except (ValueError,OSError,sqlite3.Error):
            self.notice.set("Alias belum disimpan. Gunakan 2–48 huruf/angka/spasi tanpa kata perintah atau benturan nama profil.")

    def remove_alias(self):
        if self.main.busy:
            self.notice.set("Tunggu permintaan selesai sebelum mengubah alias.")
            return
        selected=self.aliases.curselection()
        if selected:
            try:
                self.main.preferences.remove_alias(self.alias_rows[selected[0]][0])
                self.main.desktop.sync_preferences()
                self.refresh()
                self.notice.set("Alias terpilih dihapus.")
            except (OSError,sqlite3.Error):
                self.notice.set("Alias belum dapat dihapus. Periksa folder data di D.")

    def forget(self):
        if self.main.busy:
            self.notice.set("Tunggu permintaan selesai sebelum menghapus kebiasaan.")
            return
        try:
            self.main.preferences.clear_habits()
            self.main.desktop.controller.pending=None
            self.main.desktop.sync_preferences()
            self.refresh()
            self.notice.set("Catatan kebiasaan dihapus. Alias profil tetap tersimpan.")
        except (OSError,sqlite3.Error):
            self.notice.set("Catatan belum dapat dihapus. Periksa folder data di D.")

    def refresh_status(self):
        voice=self.main.voice_window
        from saluki_backend import MODEL_ROOT,MODEL_NAME,SERVER,chosen_acceleration
        try:acceleration=chosen_acceleration(self.main.preferences.get('saluki_acceleration'))
        except Exception:acceleration='menunggu benchmark'
        reply=getattr(self.main,'reply_voice',None)
        self.status_text.configure(text="Leva Desktop 0.14.1\n\n"
            +"Penyimpanan: "+("tersimpan di disk" if self.main.preferences.persistent else "hanya sesi sementara")
            +"\n"+str(self.main.preferences.path)
            +"\n\nMode chat: "+self.main.mode.get()
            +"\nFallback Qwen 4B: "+("tersedia" if DEFAULT_MODEL.is_file() else "belum ditemukan")
            +"\nSaluki 27B: "+('berkas tersedia' if (MODEL_ROOT/MODEL_NAME).is_file() and SERVER.is_file() else 'belum ditemukan')
            +' · akselerasi '+acceleration
            +"\nRuntime llama.cpp: "+("tersedia" if DEFAULT_SERVER.is_file() else "belum ditemukan")
            +"\nProfil Chrome terdeteksi: "+str(len(self.main.desktop.profiles))
            +"\nWorker chat: "+("aktif" if self.main.chat.process and self.main.chat.process.poll() is None else "tidak dimuat")
            +"\nWorker suara: "+("aktif" if voice and voice.service.active else "mati")
            +'\nJawaban suara lokal: '+('aktif' if reply and reply.active else 'siaga di memori' if reply and reply.service.loaded else 'tidak dimuat')
            +' · bahasa '+self.main.preferences.get('speech_language')
            +"\nWorker Duplex Lab: "+("aktif" if self.main.duplex_window and self.main.duplex_window.service.active else "mati")
            +"\nMikrofon: "+("aktif pada sesi Google Live" if voice and voice.mic_open else "pendengar lokal · "+self.main.local_mic.state if getattr(self.main,'local_mic',None) and self.main.local_mic.active else "mati")
            +"\n\nIni pemeriksaan file dan proses lokal, bukan tes jaringan atau pengukuran VRAM.\nAPI key tidak ditampilkan. Audio dan isi chat tidak masuk catatan kebiasaan.")

    def new_conversation(self):
        if self.main.new_conversation():
            self.notice.set("Konteks sesi sudah dibersihkan. Mulai suara kembali untuk sesi suara baru.")
        else:
            self.notice.set("Tunggu permintaan selesai atau hentikan AI terlebih dahulu.")

    def close(self):
        self.main.settings_window=None
        self.window.destroy()
