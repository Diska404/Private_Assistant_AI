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
        self.window.geometry("940x740")
        self.window.minsize(860, 680)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.notice = tk.StringVar(value="Pengaturan dan hitungan kebiasaan disimpan lokal di folder data.")
        self.provider = tk.StringVar(value=main.preferences.get("provider"))
        self.dual = tk.BooleanVar(value=main.preferences.get("dual_gpu"))
        self.learn = tk.BooleanVar(value=main.preferences.get("learn_habits"))
        self.animation = tk.StringVar(value=main.preferences.get("animation"))
        main.label(self.window, "Pengaturan & Memori", bg=BG, font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=24, pady=(20,12))
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=24)
        general = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        memory = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        diagnostics = tk.Frame(notebook, bg=PANEL, padx=22, pady=18)
        notebook.add(general, text="Umum")
        notebook.add(memory, text="Profil & Kebiasaan")
        notebook.add(diagnostics, text="Status sistem")
        self.caption(general, "Mesin percakapan teks")
        ttk.Combobox(general, textvariable=self.provider, values=MODES, state="readonly", width=34).pack(anchor="w", pady=(6,14))
        self.check(general, "Gunakan dua GPU untuk inferensi lokal (opsional)", self.dual)
        self.check(general, "Pelajari pilihan profil dari permintaan yang berhasil dikirim", self.learn)
        self.caption(general, "Setelah minimal 3 penggunaan dengan pilihan dominan, Leva menawarkan profil dan menunggu jawaban.\nHanya jenis tugas, ID profil dan hitungan yang dicatat; tidak menyimpan isi chat atau audio.", muted=True)
        self.caption(general, "Animasi Neural Voice")
        ttk.Combobox(general, textvariable=self.animation, values=("normal","hemat"), state="readonly", width=18).pack(anchor="w", pady=(7,14))
        self.caption(general, "Hemat menurunkan laju animasi saat aktif menjadi sekitar 10 fps.\nPilihan mikrofon, keluaran audio dan suara disimpan saat dipilih di Neural Voice.\nMikrofon selalu mati saat startup; perintah suara langsung diaktifkan per sesi.", muted=True)
        main.button(general, "Simpan pengaturan", self.save, primary=True).pack(anchor="w", pady=16)
        main.button(general, "Percakapan baru", self.new_conversation).pack(anchor="w")
        self.caption(general, "Percakapan baru membersihkan konteks sesi teks/suara; catatan kebiasaan tetap ada.", muted=True)

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
        try:
            self.main.preferences.set_many({"provider":self.provider.get(),"dual_gpu":self.dual.get(),"learn_habits":self.learn.get(),"animation":self.animation.get()})
            self.main.mode.set(self.provider.get())
            self.main.dual.set(self.dual.get())
            if self.main.voice_window:
                self.main.voice_window.orb.economy=self.animation.get()=="hemat"
            self.notice.set("Pengaturan disimpan. Permintaan yang sedang berjalan memakai pilihan sebelumnya." if self.main.preferences.persistent else self.main.preferences.warning)
        except (OSError,sqlite3.Error,ValueError):
            self.notice.set("Pengaturan belum tersimpan. Periksa ketersediaan folder data lokal.")

    def refresh(self):
        try:
            self._refresh()
        except (OSError,sqlite3.Error):
            self.notice.set("Catatan lokal belum dapat dibaca. Periksa ketersediaan folder data lokal.")

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
                self.notice.set("Alias belum dapat dihapus. Periksa folder data lokal.")

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
            self.notice.set("Catatan belum dapat dihapus. Periksa folder data lokal.")

    def refresh_status(self):
        voice=self.main.voice_window
        self.status_text.configure(text="Leva Desktop 0.3\n\n"
            +"Penyimpanan: "+("tersimpan di disk" if self.main.preferences.persistent else "hanya sesi sementara")
            +"\n"+str(self.main.preferences.path)
            +"\n\nModel lokal: "+("tersedia" if DEFAULT_MODEL.is_file() else "belum ditemukan")
            +"\nRuntime llama.cpp: "+("tersedia" if DEFAULT_SERVER.is_file() else "belum ditemukan")
            +"\nProfil Chrome terdeteksi: "+str(len(self.main.desktop.profiles))
            +"\nWorker chat: "+("aktif" if self.main.chat.process and self.main.chat.process.poll() is None else "tidak dimuat")
            +"\nWorker suara: "+("aktif" if voice and voice.service.active else "mati")
            +"\nMikrofon: "+("aktif pada sesi Google Live" if voice and voice.mic_open else "mati")
            +"\n\nIni pemeriksaan file dan proses lokal, bukan tes jaringan atau pengukuran VRAM.\nAPI key tidak ditampilkan. Audio dan isi chat tidak masuk catatan kebiasaan.")

    def new_conversation(self):
        if self.main.new_conversation():
            self.notice.set("Konteks sesi sudah dibersihkan. Mulai suara kembali untuk sesi suara baru.")
        else:
            self.notice.set("Tunggu permintaan selesai atau hentikan AI terlebih dahulu.")

    def close(self):
        self.main.settings_window=None
        self.window.destroy()
