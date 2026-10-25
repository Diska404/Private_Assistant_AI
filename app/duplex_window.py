"""Visible, opt-in text laboratory. This window never opens microphone or speaker."""
import time
import tkinter as tk
from tkinter import ttk

from duplex_core import DuplexCoordinator,TranscriptDelta,SpeechGate,replay_scenarios
from duplex_service import DuplexService
from gui import BG,PANEL,CARD,INK,MUTED,ACCENT


class DuplexWindow:
    def __init__(self,main):
        self.main=main
        self.window=tk.Toplevel(main.root)
        self.window.title("Leva — Duplex Lab")
        self.window.geometry("1080x860")
        self.window.minsize(950,800)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW",self.close)
        self.service=DuplexService()
        self.core=DuplexCoordinator()
        self.speech=SpeechGate()
        self.ready=False
        self.closed=False
        self.ticks={}
        self.notice=tk.StringVar(value="Belum ada model dimuat. Mikrofon dan speaker tidak digunakan di lab ini.")
        self.stats=tk.StringVar(value="Target tick 600 ms · belum ada pengukuran")
        main.label(self.window,"Duplex Lab",bg=BG,font=("Segoe UI",23,"bold")).pack(anchor="w",padx=24,pady=(22,6))
        main.label(self.window,"Eksperimen fragmen teks · tanpa mikrofon atau suara",bg=BG,fg=ACCENT).pack(anchor="w",padx=24)
        main.label(self.window,"Pilih Qwen 4B / Saluki 27B tanpa LoRA, atau Qwen 35B + MicroTurn LoRA dari video (bahasa Inggris).\n"
            "Lab menguji fragmen teks dan waktu respons; belum percakapan full-duplex melalui mikrofon.",
            bg=BG,fg=MUTED,justify="left").pack(anchor="w",padx=24,pady=(8,12))
        backendrow=tk.Frame(self.window,bg=BG)
        backendrow.pack(fill='x',padx=24,pady=(0,10))
        main.label(backendrow,'Mesin lab',bg=BG,fg=MUTED).pack(side='left',padx=(0,10))
        self.backend=tk.StringVar(value='Qwen 35B + LoRA · profil GPU + RAM')
        self.backend_choice=ttk.Combobox(backendrow,textvariable=self.backend,state='readonly',width=47,
            values=('Qwen 35B + LoRA · profil GPU + RAM','Qwen 4B · prompt saja · RTX 4050','Saluki 27B · prompt saja · RTX 5070'))
        self.backend_choice.pack(side='left')
        self.manual_replay=tk.BooleanVar(value=True)
        self.replay_choice=tk.Checkbutton(self.window,text='Replay manual · hasil >600 ms tetap dicatat sebagai riwayat teks',
            variable=self.manual_replay,bg=BG,fg=MUTED,selectcolor=CARD,activebackground=BG,
            activeforeground=INK)
        self.replay_choice.pack(anchor='w',padx=24,pady=(0,8))
        controls=tk.Frame(self.window,bg=BG)
        controls.pack(fill="x",padx=24)
        main.button(controls,"Replay sintetis",self.replay).pack(side="left",padx=(0,8))
        main.button(controls,"Muat mesin pilihan",self.start,primary=True).pack(side="left",padx=(0,8))
        main.button(controls,"Hentikan model",self.stop).pack(side="left")
        main.button(controls,"Sela / batalkan tick",self.interrupt).pack(side="right")
        entryrow=tk.Frame(self.window,bg=PANEL,padx=14,pady=14)
        entryrow.pack(fill="x",padx=24,pady=16)
        main.label(entryrow,"Fragmen baru; kosong = <no voice>. Kirim manual setelah model siap.",fg=MUTED).pack(anchor="w",pady=(0,8))
        self.entry=tk.Entry(entryrow,bg=CARD,fg=INK,insertbackground=ACCENT,relief="flat",font=("Segoe UI",12))
        self.entry.pack(side="left",fill="x",expand=True,ipady=11,padx=(0,10))
        self.entry.bind("<Return>",lambda _:self.send())
        main.button(entryrow,"Kirim tick",self.send).pack(side="right")
        frame=tk.Frame(self.window,bg=PANEL)
        frame.pack(fill="both",expand=True,padx=24)
        style=ttk.Style()
        style.configure("Duplex.Treeview",background=PANEL,fieldbackground=PANEL,foreground=INK,rowheight=28,borderwidth=0)
        style.map("Duplex.Treeview",background=[("selected","#284b54")])
        self.table=ttk.Treeview(frame,columns=("tick","heard","said","time","status"),show="headings",height=6,style="Duplex.Treeview")
        for column,title,width in [("tick","Tick",55),("heard","Fragmen masuk",245),("said","Keluaran kebijakan",245),("time","Waktu / ms",110),("status","Hasil",190)]:
            self.table.heading(column,text=title)
            self.table.column(column,width=width,minwidth=40,stretch=column in {"heard","said","status"})
        self.table.pack(side="left",fill="both",expand=True)
        scroll=ttk.Scrollbar(frame,orient="vertical",command=self.table.yview)
        scroll.pack(side="right",fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        tk.Label(self.window,textvariable=self.stats,bg=BG,fg=ACCENT,anchor="w").pack(fill="x",padx=24,pady=(12,4))
        tk.Label(self.window,textvariable=self.notice,bg=BG,fg=MUTED,wraplength=1000,anchor="w",justify="left").pack(fill="x",padx=24,pady=(0,20))
        self.window.after(80,self.poll)

    def row(self,tick,heard,said,elapsed,status):
        children=self.table.get_children()
        if len(children)>=128:self.table.delete(children[0])
        self.table.insert("","end",values=(tick,heard,said,elapsed,status))
        self.table.yview_moveto(1)

    def replay(self):
        self.stop()
        self.table.delete(*self.table.get_children())
        proof=replay_scenarios()
        for row in proof["rows"]:
            self.row(row["tick"],row["heard"],row["policy_output"],"simulasi","fixture · "+row["kind"])
        self.stats.set("Replay selesai · flush antrean lulus · audio lama ditolak oleh ticket")
        self.notice.set("Ini data dan keputusan buatan dengan jam virtual. Tidak ada AI, mikrofon atau TTS yang dijalankan.")

    def start(self):
        if self.service.active:return
        self.main.stop_reply_voice()
        voice=self.main.voice_window
        if self.main.busy or (voice and voice.service.active) or self.main.desktop.paused or self.main.desktop.sleeping:
            self.notice.set("Selesaikan chat/hentikan sesi suara dan aktifkan Leva sebelum memulai lab lokal.")
            return
        self.main.chat.cancel()
        self.core=DuplexCoordinator(enforce_deadline=not self.manual_replay.get())
        self.speech=SpeechGate()
        self.ticks.clear()
        self.table.delete(*self.table.get_children())
        self.ready=False
        backend='microturn' if self.backend.get().startswith('Qwen 35B') else 'saluki' if self.backend.get().startswith('Saluki') else 'baseline'
        self.stats.set(("Replay manual" if self.manual_replay.get() else "Batas ketat")+" · target tick 600 ms · belum ada pengukuran sesi ini")
        try:
            self.backend_choice.configure(state='disabled')
            self.replay_choice.configure(state='disabled')
            if backend=='saluki':self.service.start_lab(backend,acceleration=self.main.preferences.get('saluki_acceleration'))
            else:self.service.start_lab(backend)
            self.notice.set(('Memeriksa hash dan memuat Qwen 35B + LoRA memakai profil GPU + RAM yang diuji. ' if backend=='microturn'
                else 'Memuat Saluki pada RTX 5070. ' if backend=='saluki' else 'Memuat Qwen 4B pada RTX 4050. ')+ 'Model tetap dimuat selama lab aktif; idle 3 menit melepasnya.')
        except Exception:
            self.service.stop()
            self.backend_choice.configure(state='readonly')
            self.replay_choice.configure(state='normal')
            self.notice.set("Worker lab tidak dapat dimulai. Periksa runtime/model lokal.")

    def send(self):
        if not self.ready or not self.service.active:
            self.notice.set("Muat mesin pilihan terlebih dahulu; lab tidak mengirim permintaan online.")
            return
        if self.core.inflight is not None:
            self.notice.set("Satu tick masih berjalan. Anda tetap dapat menghentikan model atau membatalkan hasilnya.")
            return
        text=self.entry.get().strip()
        if len(text)>600:
            self.notice.set("Batasi fragmen hingga 600 karakter.")
            return
        try:
            if text:self.core.add(TranscriptDelta(text))
        except BufferError:
            self.stop()
            self.notice.set("Fragmen menumpuk atau terlalu panjang. Lab dihentikan; mulai sesi baru dengan potongan pendek.")
            return
        tick=self.core.begin(time.monotonic())
        if tick is None:
            self.notice.set("Tunggu sampai interval tick berikutnya. Fragmen sudah diantrekan sekali.")
            self.entry.delete(0,"end")
            return
        self.entry.delete(0,"end")
        self.ticks[tick.id]=tick
        self.service.send({"kind":"tick","id":tick.id,"heard":tick.heard,"history":list(tick.history)})
        self.notice.set("Memproses tick teks. Hasil >600 ms ditandai terlambat; mode replay mempertahankan riwayat tanpa memutar suara.")

    def interrupt(self):
        # Terminate the owned backend as well: a request already executing must not
        # overlap a second inference after cancellation.
        self.stop()
        self.notice.set("Tick/model dibatalkan, antrean dibersihkan. Muat kembali untuk sesi baru; mikrofon tetap mati.")

    def stop(self):
        self.core.pause()
        self.speech.cancel()
        self.service.stop()
        self.ready=False
        self.backend_choice.configure(state='readonly')
        self.replay_choice.configure(state='normal')
        self.ticks.clear()
        self.notice.set("Lab berhenti · model dilepas · mikrofon dan speaker tidak digunakan")

    def poll(self):
        if self.closed:return
        while not self.service.events.empty():
            event=self.service.events.get_nowait()
            kind=event.get("kind")
            if kind=="ready":
                self.ready=True
                self.notice.set(f"{event['backend']} siap · load {event['load_seconds']:.2f} s · GPU {', '.join(event['devices'])}. Kirim fragmen manual.")
            elif kind=="result":
                tick=self.ticks.pop(event["id"],None)
                if tick:
                    result=self.core.finish(tick,event["text"],time.monotonic())
                    status=result.get("kind") if result["accepted"] else result["reason"]
                    if result.get('late') and result.get('manual_replay'):status+=' · replay >600 ms'
                    if result.get("kind")=="speak" and not result.get('manual_replay'):
                        self.speech.enqueue(result["text"])
                        self.speech.coalesce()  # Text-only preview, deliberately no synthesis.
                    elapsed=result.get("processing_ms",event["backend_ms"])
                    self.row(tick.id,tick.heard,event["text"],f"{elapsed:.1f}",status)
                    summary=self.core.summary()
                    self.stats.set(f"Target 600 ms · p50 {summary['tick_processing_p50_ms']} ms · p95 {summary['tick_processing_p95_ms']} ms · lewat batas {summary['deadline_misses']}")
                    probability=event.get('listen_probability')
                    extra=f" · P(listen) {probability:.3f}" if probability is not None else ''
                    self.notice.set(f"Backend {event['backend_ms']:.1f} ms{extra}; tabel mengukur sampai UI menerima hasil. Tidak ada suara yang diputar.")
            elif kind=="error":
                code=event.get("code","lab_error")
                self.stop()
                self.notice.set("Lab berhenti: "+code+". Mode utama Leva tetap tersedia.")
            elif kind=="notice":
                self.notice.set("Batas idle lab tercapai; model dilepas. Muat ulang bila diperlukan.")
            elif kind=="stopped":
                self.ready=False
                self.backend_choice.configure(state='readonly')
                self.replay_choice.configure(state='normal')
        self.window.after(80,self.poll)

    def close(self):
        self.stop()
        self.closed=True
        self.window.destroy()
        self.main.duplex_window=None
