"""Tkinter desktop shell. Only the UI thread touches widgets."""
from datetime import datetime
import json
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk

from chat_service import ChatService
from command_resolution import WIB
from desktop_service import DesktopService
from hybrid_engine import EngineError
from paths import DATA
from preferences import Preferences, MODES

BG, PANEL, CARD, INK, MUTED, ACCENT = "#0b1120", "#111b2d", "#1b2940", "#e7edf8", "#99abc5", "#7ce4ca"


class LevaWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Leva — Asisten Desktop")
        self.root.geometry("1120x780")
        self.root.minsize(960, 700)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.preferences = Preferences()
        self.desktop, self.chat = DesktopService(preferences=self.preferences), ChatService()
        self.voice_window = None
        self.settings_window = None
        self.events = queue.Queue()
        self.busy, self.closed, self.generation = False, False, 0
        self.mode = tk.StringVar(value=self.preferences.get("provider"))
        self.dual = tk.BooleanVar(value=self.preferences.get("dual_gpu"))
        self.status = tk.StringVar(value="Aktif · perintah lokal siap")
        self.activity = tk.StringVar(value="AI tidak dimuat")
        self._layout()
        self.mode.trace_add("write",lambda *_: self.save_preference("provider",self.mode.get()))
        self.dual.trace_add("write",lambda *_: self.save_preference("dual_gpu",self.dual.get()))
        self._profiles()
        self.add("Leva", "Aku siap. Pilih profil di sebelah kiri, atau ketik ‘buka Chrome’. "
                 "Kamu juga bisa mengobrol denganku. Perintah Chrome diproses lokal; obrolan AI pada mode Hybrid dikirim ke Google.")
        self.add("Info", "Versi 0.3 · Pengaturan dan catatan kebiasaan profil tersimpan lokal. Buka Pengaturan untuk melihat atau menghapusnya. "
                 "Neural Voice memakai Google Live; mikrofon hanya aktif setelah Mulai suara ditekan. Suara Shiroko, skip iklan, pemulihan tab, WhatsApp, dan autostart belum tersedia.")
        if self.preferences.warning:
            self.add("Info",self.preferences.warning)
        self.root.after(100, self.poll)
        self.root.after(1000, self.tick)
        self.entry.focus_set()

    def label(self, parent, text, **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", PANEL), fg=kwargs.pop("fg", INK), **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else CARD,
                         fg=BG if primary else INK, activebackground="#a4f4df" if primary else "#2a3f5e",
                         activeforeground=BG if primary else INK, bd=0, relief="flat", cursor="hand2",
                         padx=14, pady=10, **kwargs)

    def _layout(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=INK,
                        arrowcolor=ACCENT, borderwidth=0, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", INK)],
                  selectbackground=[("readonly", CARD)], selectforeground=[("readonly", INK)])
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        left = tk.Frame(self.root, bg=PANEL, width=250, padx=20, pady=24)
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 0), pady=16)
        left.grid_propagate(False)
        self.label(left, "L E V A", fg=ACCENT, font=("Segoe UI", 25, "bold")).pack(anchor="w")
        self.label(left, "Asisten desktop · pratinjau 0.3", fg=MUTED).pack(anchor="w", pady=(3, 24))
        self.label(left, "PROFIL CHROME", fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, bg=PANEL, fg=INK, selectbackground="#284b54", selectforeground=ACCENT,
                                 bd=0, highlightthickness=0, activestyle="none", height=12, exportselection=False,
                                 font=("Segoe UI", 10))
        self.listbox.pack(fill="both", expand=True, pady=(10, 12))
        self.open_chrome = self.button(left, "Buka Chrome", lambda: self.open_profile(False))
        self.open_chrome.pack(fill="x", pady=4)
        self.open_youtube = self.button(left, "Buka YouTube", lambda: self.open_profile(True), primary=True)
        self.open_youtube.pack(fill="x", pady=4)
        self.refresh_button = self.button(left, "Segarkan profil", self.refresh)
        self.refresh_button.pack(fill="x", pady=(4, 14))
        self.label(left, "Nama sama? Nomor profil membantu\nmembedakan pilihan.", fg=MUTED, justify="left", font=("Segoe UI", 9)).pack(anchor="w")

        content = tk.Frame(self.root, bg=BG, padx=20)
        content.grid(row=0, column=1, sticky="nsew", pady=16)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)
        header = tk.Frame(content, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(5, 16))
        self.label(header, "Ada yang bisa kubantu?", bg=BG, font=("Segoe UI", 21, "bold")).pack(side="left")
        self.pause_button = self.button(header, "Jeda", self.toggle_pause)
        self.pause_button.pack(side="right")
        options = tk.Frame(content, bg=PANEL, padx=14, pady=12)
        options.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.provider = ttk.Combobox(options, textvariable=self.mode,
                                    values=MODES,
                                    state="readonly", width=26)
        self.provider.grid(row=0, column=0, sticky="w")
        self.dual_check = tk.Checkbutton(options, text="Dua GPU (opsional)", variable=self.dual,
                                       bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=INK,
                                       selectcolor=CARD, bd=0)
        self.dual_check.grid(row=0, column=1, padx=(10, 0), sticky="w")
        self.label(options, "Obrolan Hybrid memakai Google. Perintah profil tetap lokal.", fg=MUTED,
                   font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        history_frame = tk.Frame(content, bg=PANEL)
        history_frame.grid(row=2, column=0, sticky="nsew")
        history_frame.grid_rowconfigure(0, weight=1)
        history_frame.grid_columnconfigure(0, weight=1)
        self.history = tk.Text(history_frame, wrap="word", bg=PANEL, fg=INK, insertbackground=ACCENT,
                               relief="flat", padx=20, pady=18, font=("Segoe UI", 11), state="disabled",
                               selectbackground="#35556b", highlightthickness=0, cursor="arrow")
        self.history.grid(row=0, column=0, sticky="nsew")
        scroll = tk.Scrollbar(history_frame, command=self.history.yview, bg=CARD, bd=0)
        scroll.grid(row=0, column=1, sticky="ns")
        self.history.configure(yscrollcommand=scroll.set)
        for tag, color in [("Leva", ACCENT), ("Anda", "#b6caff"), ("Info", MUTED), ("AI", "#cdbbff")]:
            self.history.tag_configure(tag, foreground=color, font=("Segoe UI", 10, "bold"), spacing1=12, spacing3=5)
        self.history.tag_configure("body", spacing3=14, lmargin1=0, lmargin2=0)
        input_frame = tk.Frame(content, bg=BG)
        input_frame.grid(row=3, column=0, sticky="ew", pady=(12, 8))
        input_frame.grid_columnconfigure(0, weight=1)
        self.entry = tk.Entry(input_frame, bg=CARD, fg=INK, insertbackground=ACCENT, relief="flat",
                              disabledbackground=CARD, disabledforeground=MUTED,
                              font=("Segoe UI", 12), highlightthickness=1, highlightbackground="#2a3d57",
                              highlightcolor=ACCENT)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=12, padx=(0, 8))
        self.entry.bind("<Return>", lambda _: self.send())
        self.send_button = self.button(input_frame, "Kirim", self.send, primary=True)
        self.send_button.grid(row=0, column=1)
        footer = tk.Frame(content, bg=BG)
        footer.grid(row=4, column=0, sticky="ew")
        tk.Label(footer, textvariable=self.status, bg=BG, fg=ACCENT, font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(footer, textvariable=self.activity, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 5))
        tools = tk.Frame(content, bg=BG)
        tools.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        self.button(tools, "Lepaskan AI", self.release).pack(side="left", padx=(0, 8))
        self.button(tools, "Coba online lagi", self.retry_online).pack(side="left")
        self.button(tools, "Pengaturan", self.open_settings).pack(side="left",padx=8)
        self.button(tools, "Neural Voice", self.open_voice).pack(side="right")

    def add(self, speaker, text):
        tag = "AI" if speaker.startswith("Leva ·") else speaker
        self.history.configure(state="normal")
        self.history.insert("end", speaker + "\n", tag)
        self.history.insert("end", text + "\n\n", "body")
        if int(self.history.index("end-1c").split(".")[0]) > 1000:
            self.history.delete("1.0","250.0")
        self.history.configure(state="disabled")
        self.history.see("end")

    def _profiles(self):
        self.profile_rows = list(self.desktop.profiles.values())
        self.listbox.delete(0, "end")
        for profile in self.profile_rows:
            suffix = profile["profile_directory"].replace("Profile ", "#")
            self.listbox.insert("end", profile["name"] + "   · " + suffix)
        if not self.profile_rows:
            self.add("Info", "Belum ada profil Chrome yang ditemukan. Periksa instalasi Chrome lalu segarkan profil.")

    def open_profile(self, youtube):
        selected = self.listbox.curselection()
        if not selected:
            self.send("buka YouTube" if youtube else "buka Chrome")
        else:
            profile = self.profile_rows[selected[0]]
            prefix = "buka YouTube di profil " if youtube else "buka Chrome profil "
            self.send(prefix + profile["id"], display=prefix + profile["name"])

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.entry, self.send_button, self.open_chrome, self.open_youtube, self.refresh_button, self.dual_check]:
            widget.configure(state="disabled" if busy else "normal")
        self.provider.configure(state="disabled" if busy else "readonly")
        if not busy:
            self.entry.focus_set()

    def send(self, supplied=None, display=None, commands_only=False):
        if self.busy:
            return
        text = supplied or self.entry.get().strip()
        if not text:
            return
        if len(text) > 3000:
            self.add("Info", "Pesannya terlalu panjang untuk versi awal ini. Batasi hingga 3.000 karakter.")
            return
        self.entry.delete(0, "end")
        self.add("Anda", display or text)
        self.set_busy(True)
        self.generation += 1
        generation = self.generation
        mode, dual = self.mode.get(), self.dual.get()
        self.activity.set("Memproses permintaan…")
        def run():
            try:
                result = self.desktop.handle(text)
                if result.get("cancel_ai"):
                    self.chat.cancel()
                if result["kind"] == "chat":
                    if commands_only:
                        result = {"reply": "Transkrip ini belum dikenali sebagai perintah desktop. Percakapan suara tetap ditangani Google Live."}
                    elif mode.startswith("Perintah"):
                        result = {"reply": "Mode perintah saja aktif. Pilih Hybrid atau Lokal untuk mengobrol dengan AI."}
                    else:
                        result = self.chat.ask(text, "local" if mode.startswith("Lokal") else "hybrid", "dual" if dual else "gpu4050")
                self.events.put((generation, result))
            except EngineError as error:
                self.events.put((generation, {"error": str(error)}))
            except Exception:
                self.events.put((generation, {"error": "desktop_or_runtime_failure"}))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        while not self.events.empty():
            generation, result = self.events.get_nowait()
            if generation != self.generation:
                continue
            self.set_busy(False)
            if result.get("cancel_ai") and self.voice_window:
                self.voice_window.stop(sleeping=self.desktop.paused or self.desktop.sleeping)
            if result.get("cancelled"):
                self.add("Info", "Permintaan AI dihentikan.")
            elif result.get("error"):
                error = result["error"]
                if error.startswith("online_"):
                    text = "Layanan Google belum merespons dengan benar. Periksa koneksi/key atau pilih mode Lokal."
                else:
                    text = "Permintaan belum berhasil. Periksa ketersediaan runtime/model dan coba lagi."
                self.add("Info", text + " Kode: " + error)
            else:
                provider = result.get("provider")
                speaker = "Leva · " + ("Google" if provider == "google" else "Lokal") if provider else "Leva"
                self.add(speaker, result.get("reply", result.get("response", "")))
                if result.get("detail"):
                    self.add("Info", result["detail"])
                if self.desktop.memory_notice:
                    self.add("Info",self.desktop.memory_notice)
                    self.desktop.memory_notice=""
                if result.get("kind")=="command" and self.voice_window:
                    self.voice_window.desktop_result(result.get("reply",""))
            self.activity.set("AI tidak dimuat · model lokal dilepas setelah jawaban")
        self.root.after(100, self.poll)

    def tick(self):
        if self.closed:
            return
        previous_sleeping = self.desktop.sleeping
        changed = self.desktop.tick()
        if self.desktop.sleeping and not previous_sleeping:
            self.chat.cancel()
        if self.desktop.sleeping and self.voice_window and self.voice_window.service.active:
            self.voice_window.stop(sleeping=True)
        machine = self.desktop.controller.sleep
        if self.desktop.paused:
            self.status.set("Dijeda · tekan Aktifkan untuk melanjutkan")
        elif machine.mode == "paused":
            self.status.set("Istirahat sampai " + machine.next_transition.strftime("%H.%M WIB"))
        elif machine.mode == "observing":
            self.status.set("Aktif · observasi aktivitas sampai " + machine.next_transition.strftime("%H.%M WIB"))
        else:
            self.status.set("Aktif · " + str(len(self.profile_rows)) + " profil Chrome tersedia")
        self.pause_button.configure(text="Aktifkan" if self.desktop.paused or machine.mode != "off" else "Jeda")
        if changed and machine.mode == "off":
            self.add("Info", "Ada aktivitas saat observasi. Mekanisme tidur dibatalkan; aku aktif kembali.")
        self.root.after(1000, self.tick)

    def release(self):
        self.chat.cancel()
        if self.voice_window:
            self.voice_window.stop()
        self.activity.set("Proses AI dihentikan · resource dilepas")
        self.add("Info", "Permintaan AI dihentikan dan worker lokal milik Leva dilepas.")

    def toggle_pause(self):
        self.chat.cancel()
        if self.voice_window:
            self.voice_window.stop(sleeping=True)
        if self.desktop.paused or self.desktop.controller.sleep.mode != "off":
            self.desktop.resume()
            if self.voice_window:
                self.voice_window.set_state("idle")
            self.add("Leva", "Aku aktif kembali. Jadwal jeda sebelumnya sudah dibatalkan.")
        else:
            self.desktop.pause()
            self.add("Leva", "Aku dijeda dan proses AI dilepas. Chrome tetap terbuka. Tekan Aktifkan untuk melanjutkan.")
        self.activity.set("AI tidak dimuat")

    def retry_online(self):
        self.chat.online_paused = False
        self.add("Info", "Permintaan Hybrid berikutnya akan mencoba Google kembali.")

    def refresh(self):
        if self.busy:
            return
        self.desktop.refresh_profiles()
        self._profiles()
        self.add("Info", "Daftar profil diperbarui. Pilihan tugas dan jadwal sebelumnya sudah dihapus.")

    def close(self):
        self.closed = True
        self.chat.cancel()
        if self.voice_window:
            self.voice_window.close()
        self.root.destroy()

    def open_voice(self):
        if self.voice_window and not self.voice_window.closed:
            self.voice_window.window.lift()
            return
        from voice_window import VoiceWindow
        self.voice_window = VoiceWindow(self)

    def save_preference(self,key,value):
        try:
            self.preferences.set(key,value)
        except (OSError,ValueError,sqlite3.Error):
            self.add("Info","Pengaturan belum tersimpan. Periksa folder data lokal.")

    def open_settings(self):
        if self.settings_window:
            self.settings_window.window.lift()
            return
        from settings_window import SettingsWindow
        self.settings_window=SettingsWindow(self)

    def new_conversation(self):
        if self.busy:
            return False
        if self.voice_window:
            self.voice_window.stop()
            self.voice_window.heard.configure(text="Anda: —")
            self.voice_window.said.configure(text="Leva: —")
            self.voice_window.app_result.configure(text="")
        self.chat.history=[]
        self.desktop.controller.pending=None
        self.history.configure(state="normal")
        self.history.delete("1.0","end")
        self.history.configure(state="disabled")
        self.add("Leva","Percakapan baru siap. Catatan kebiasaan dan pengaturan tetap tersimpan.")
        return True

    def run(self):
        self.root.mainloop()
