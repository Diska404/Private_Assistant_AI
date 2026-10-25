"""Inspect target versus actual voice; synthesize/play only after user activation."""
import os
import tkinter as tk
from tkinter import ttk

from gui import BG, PANEL, CARD, INK, MUTED, ACCENT
from paths import DATA
from voice_pack_service import VoicePackService
from voice_packs import PACK_IDS, catalog, resolve_pack, voice_error_notice


class VoicePackWindow:
    def __init__(self, main):
        self.main = main
        self.window = tk.Toplevel(main.root)
        self.window.title("Leva — Voice Pack Manager")
        self.window.geometry("990x860")
        self.window.minsize(920, 730)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.service = VoicePackService()
        self.closed = False
        self.packs = catalog()
        self.selected = tk.StringVar(value=main.preferences.get("target_voice_pack"))
        self.summary = tk.StringVar()
        self.detail = tk.StringVar()
        self.notice = tk.StringVar(value="Preview tidak membuka mikrofon. Pilih pack, lalu buat sampel. Putar audio melalui tombol terpisah.")
        main.label(self.window, "Voice Pack Manager", bg=BG, font=("Segoe UI", 23, "bold")).pack(anchor="w", padx=24, pady=(20, 8))
        main.label(self.window, "Kandidat Leva A · Indonesia / Jepang · mesin suara modular", bg=BG, fg=ACCENT).pack(anchor="w", padx=24)
        content = tk.Frame(self.window, bg=PANEL, padx=20, pady=16)
        content.pack(fill="both", expand=True, padx=24, pady=16)
        self.names={self.packs[ident]['name']:ident for ident in PACK_IDS}
        self.pack_label=tk.StringVar(value=self.packs[self.selected.get()]['name'])
        chooser=ttk.Combobox(content,textvariable=self.pack_label,values=list(self.names),state='readonly',width=78)
        chooser.pack(fill='x',pady=4)
        chooser.bind('<<ComboboxSelected>>',lambda *_:(self.selected.set(self.names[self.pack_label.get()]),self.refresh()))
        from speech_style import LABELS
        self.style_labels=LABELS
        self.style=tk.StringVar(value=LABELS[main.preferences.get('speech_style')] if main.preferences.get('speech_style') in LABELS else LABELS['auto'])
        ttk.Combobox(content,textvariable=self.style,values=list(LABELS.values()),state='readonly',width=40).pack(anchor='w',pady=4)
        main.label(content, "", textvariable=self.summary, fg=ACCENT, justify="left", wraplength=860,
                   font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(14, 8))
        main.label(content, "", textvariable=self.detail, fg=MUTED, justify="left", wraplength=860).pack(anchor="w")
        actions = tk.Frame(content, bg=PANEL)
        actions.pack(fill="x", pady=12)
        main.button(actions, "Simpan target suara", self.save).pack(side="left", padx=(0, 8))
        main.button(actions, "Sampel Shiroko terdahulu", self.open_history).pack(side="left")
        self.language=tk.StringVar(value='日本語' if main.preferences.get('speech_language')=='ja' else 'Indonesia')
        self.language.trace_add('write',lambda *_:self.refresh())
        ttk.Combobox(content,textvariable=self.language,values=('Indonesia','日本語'),state='readonly',width=15).pack(anchor='w',pady=4)
        main.label(content, "Tulis teks langsung dalam bahasa pilihan · maksimal 600 karakter", fg=MUTED).pack(anchor="w", pady=(8, 5))
        self.text = tk.Text(content, height=4, bg=CARD, fg=INK, insertbackground=ACCENT, wrap="word", bd=0,
                            font=("Segoe UI", 11), padx=12, pady=10)
        self.text.insert("1.0", "こんにちは、レヴァです。いつでもお手伝いします。今日は何をしましょうか。" if self.language.get()=='日本語' else "Halo, aku Leva. Aku siap menemanimu. Apa yang ingin kita kerjakan hari ini?")
        self.text.pack(fill="x")
        row = tk.Frame(content, bg=PANEL)
        row.pack(fill="x", pady=12)
        self.generate_button = main.button(row, "Buat sampel", self.generate, primary=True)
        self.generate_button.pack(side="left", padx=(0, 8))
        self.play_button = main.button(row, "Putar sampel", self.play, state="disabled")
        self.play_button.pack(side="left", padx=(0, 8))
        main.button(row, "Hentikan & lepas resource", self.stop).pack(side="left")
        main.label(content, "", textvariable=self.notice, fg=ACCENT, justify="left", wraplength=860).pack(anchor="w", pady=8)
        main.label(content, "Sintesis berkas lokal, belum percakapan mikrofon atau streaming. Keluaran memakai perangkat default Windows.\n"
                   "Model dimuat saat membuat sampel dan dilepas setelahnya. Sampel sementara dibersihkan saat dihentikan/ditutup.\n"
                   "Pemilihan pack ini tidak mengubah suara Google Live.", fg=MUTED, justify="left", wraplength=860).pack(anchor="w", pady=8)
        self.refresh()
        self.window.after(80, self.poll)

    def refresh(self):
        ident = self.selected.get()
        row = self.packs[ident]
        resolved = resolve_pack(ident)
        japanese=hasattr(self,'language') and self.language.get()=='日本語'
        base='Kokoro Jepang' if japanese else 'Piper Indonesia'
        self.summary.set("Dipilih: " + row["name"] + "\nYang dapat dijalankan: " +
                         (row['name'] if row['engine']=='audio_cpp' and resolved['available'] else 'Kandidat Leva A · '+base+' → Seed-VC' if resolved['actual']=='leva_gfl2' else base+' netral' if resolved["available"] else "belum tersedia"))
        self.detail.set(row["description"] + "\n" + row["rights"] + "\n" + (resolved['reason'] if row['engine']=='audio_cpp' else base+' lokal · referensi A jika kandidat dipilih.' if japanese else resolved["reason"]))

    def save(self):
        self.main.save_preference("target_voice_pack", self.selected.get())
        self.main.save_preference('speech_style',next(k for k,v in self.style_labels.items() if v==self.style.get()))
        self.notice.set("Target suara disimpan. Ketersediaan engine tetap diperiksa sebelum digunakan.")

    def open_history(self):
        path = DATA / "verification/shiroko-voice-proof/comparison.html"
        if path.is_file():
            os.startfile(str(path))
        else:
            self.notice.set("Halaman sampel historis belum ditemukan pada D.")

    def generate(self):
        from pipeline_routing import route_spec
        from speech_resources import pipeline_gpu
        spec=route_spec(self.main.mode.get(),self.main.dual.get())
        if spec['mode']=='commands':self.notice.set('Tanpa AI: sintesis dinonaktifkan. Pilih rute GPU dahulu.');return
        self.service.gpu_preference=pipeline_gpu(spec,'tts')
        self.main.stop_reply_voice()
        if self.main.busy:
            self.notice.set('Tunggu jawaban chat selesai sebelum membuat preview suara.');return
        self.main.cancel_inference()
        if self.main.desktop.paused or self.main.desktop.sleeping:
            self.notice.set("Aktifkan sistem Leva terlebih dahulu.")
            return
        try:
            live = getattr(self.main, "voice_window", None)
            if live and live.service.active:
                live.stop()
            style=next(k for k,v in self.style_labels.items() if v==self.style.get())
            result = self.service.generate(self.selected.get(), self.text.get("1.0", "end-1c"),language='ja' if self.language.get()=='日本語' else 'id',style='assistant' if style=='auto' else style)
            self.generate_button.configure(state="disabled")
            self.play_button.configure(state="disabled")
            self.notice.set("Membuat ucapan baru · " + result["reason"] + " Preview tidak membuka mikrofon.")
        except Exception:
            self.notice.set("Sampel belum dapat dibuat. Periksa runtime/model suara dan teks uji (1–600 karakter).")

    def play(self):
        self.main.stop_reply_voice()
        if self.main.desktop.paused or self.main.desktop.sleeping:
            self.notice.set("Aktifkan sistem Leva terlebih dahulu.")
            return
        live = getattr(self.main, "voice_window", None)
        if live and live.service.active:
            live.stop()
        try:
            self.service.play()
        except Exception:
            self.notice.set("Sampel tidak tersedia; buat ulang sebelum diputar.")

    def stop(self):
        self.service.stop()
        self.generate_button.configure(state="normal")
        self.play_button.configure(state="disabled")
        self.notice.set("Dihentikan · model dan audio dilepas · preview tidak membuka mikrofon")

    def poll(self):
        if self.closed:
            return
        if self.service.check_timeout():
            self.generate_button.configure(state="normal")
            self.notice.set("Batas waktu sintesis tercapai; worker dihentikan.")
        while not self.service.events.empty():
            event = self.service.events.get_nowait()
            kind = event.get("kind")
            if kind == "generated":
                try:
                    self.service.accept_generated(event)
                    self.play_button.configure(state="normal")
                    self.notice.set('Sampel siap · '+self.packs[event['actual_pack']]['name']+' · '+"%.2f dtk audio / %.2f dtk sintesis / %.2f dtk total.\n"
                                    "Belum diputar. Tekan Putar sampel untuk mendengarkan." %
                                    (event["duration_seconds"], event["synthesis_seconds"], event["total_seconds"]))
                except (ValueError, OSError, KeyError):
                    self.stop()
                    self.notice.set("Hasil worker tidak valid; buat sampel ulang.")
            elif kind == "stopped":
                self.generate_button.configure(state="normal")
            elif kind == "playback_started":
                self.service.state = "speaking"
                self.notice.set('Memutar '+self.packs[self.service.actual_pack]['name']+' · preview tidak membuka mikrofon')
            elif kind == "playback_finished":
                self.play_button.configure(state="normal" if self.service.generated else "disabled")
            elif kind == "error":
                self.stop()
                self.notice.set(voice_error_notice(event.get('code','local_tts_failed')))
        self.window.after(80, self.poll)

    def close(self):
        self.stop()
        self.closed = True
        self.window.destroy()
        self.main.voice_pack_window = None
