import queue
import re
import time
import tkinter as tk
from tkinter import ttk

from live_voice import LiveVoiceService, audio_devices
from neural_orb import NeuralOrb
from voice_core import STATES, VOICE_ERRORS, direct_command, preferred_device
from preferences import VOICES

LABELS={"idle":"Siap menemanimu", "connecting":"Menghubungkan suara…", "listening":"Aku mendengarkan",
        "thinking":"Menyiapkan jawaban", "speaking":"Leva berbicara", "clarifying":"Perlu penjelasan",
        "interrupted":"Baik, aku mendengarkan lagi", "sleeping":"Leva beristirahat", "error":"Suara belum tersedia"}


class VoiceWindow:
    def __init__(self, main):
        self.main=main
        self.window=tk.Toplevel(main.root)
        self.window.title("Leva — Neural Voice")
        self.window.geometry("1080x860")
        self.window.minsize(950,810)
        self.window.configure(bg="#070d19")
        self.window.protocol("WM_DELETE_WINDOW",self.close)
        self.service=LiveVoiceService()
        self.closed=False
        self.mic_open=False
        self.last_text=""
        self.final_text=""
        self.hold_until=0.0
        self.direct=tk.BooleanVar(value=False)
        self.last_dispatched=("",0.0)
        self.notice=tk.StringVar(value="Mikrofon mati · pratinjau visual")
        self.heading=tk.StringVar(value=LABELS["idle"])
        self.input_var=tk.StringVar()
        self.output_var=tk.StringVar()
        self.voice_var=tk.StringVar(value=main.preferences.get("voice"))
        self.demo_var=tk.StringVar(value="idle")
        self._layout()
        self.window.after(80,self.poll)
        self.window.after(30,self.load_devices)

    def button(self,parent,text,command,primary=False):
        return tk.Button(parent,text=text,command=command,bg="#efb759" if primary else "#1b2940",
                         fg="#0a1321" if primary else "#d8e4f2",bd=0,padx=15,pady=10,cursor="hand2")

    def _layout(self):
        tk.Label(self.window,text="L E V A  /  N E U R A L  V O I C E",bg="#070d19",fg="#efc77f",
                 font=("Segoe UI",18,"bold")).pack(anchor="w",padx=28,pady=(22,3))
        tk.Label(self.window,text="Suara dua arah · dengar dan bicara dalam satu sesi",bg="#070d19",fg="#7f95ac").pack(anchor="w",padx=28)
        body=tk.Frame(self.window,bg="#070d19")
        body.pack(fill="both",expand=True,padx=20,pady=12)
        body.grid_rowconfigure(0,weight=1)
        body.grid_columnconfigure(0,weight=1)
        left=tk.Frame(body,bg="#070d19")
        left.grid(row=0,column=0,sticky="nsew",padx=(0,20))
        self.orb=NeuralOrb(left)
        self.orb.economy=self.main.preferences.get("animation")=="hemat"
        self.orb.pack(fill="both",expand=True)
        tk.Label(left,textvariable=self.heading,bg="#070d19",fg="#edc98b",font=("Segoe UI",17,"bold")).pack(pady=(0,6))
        tk.Label(left,textvariable=self.notice,bg="#070d19",fg="#8da5bc",wraplength=600,justify="center").pack(pady=(0,12))
        self.meter=tk.Label(left,text="Mikrofon  ░░░░░░░░░░   Suara  ░░░░░░░░░░",bg="#070d19",fg="#6aa4aa",font=("Consolas",10))
        self.meter.pack(pady=(0,10))
        controls=tk.Frame(left,bg="#070d19")
        controls.pack()
        self.start=self.button(controls,"Mulai suara · Google",self.toggle,True)
        self.start.pack(side="left",padx=4)
        self.button(controls,"Sela / hentikan ucapan",self.interrupt).pack(side="left",padx=4)
        side=tk.Frame(body,bg="#101b2c",padx=18,pady=18,width=302)
        side.grid(row=0,column=1,sticky="ns")
        side.grid_propagate(False)
        def caption(text):
            tk.Label(side,text=text,bg="#101b2c",fg="#c3d1df",anchor="w").pack(fill="x",pady=(8,5))
        devices_header=tk.Frame(side,bg="#101b2c")
        devices_header.pack(fill="x",pady=(0,5))
        tk.Label(devices_header,text="MIKROFON",bg="#101b2c",fg="#c3d1df").pack(side="left")
        tk.Button(devices_header,text="Segarkan",command=self.load_devices,bg="#1b2940",fg="#d8e4f2",bd=0,padx=6,pady=4).pack(side="right")
        self.inputs=ttk.Combobox(side,textvariable=self.input_var,state="readonly",width=30)
        self.inputs.pack(fill="x")
        caption("KELUARAN AUDIO")
        self.outputs=ttk.Combobox(side,textvariable=self.output_var,state="readonly",width=30)
        self.outputs.pack(fill="x")
        caption("SUARA SEMENTARA")
        self.voices=ttk.Combobox(side,textvariable=self.voice_var,values=VOICES,state="readonly")
        self.voices.pack(fill="x")
        self.voices.bind("<<ComboboxSelected>>",lambda _: self.main.save_preference("voice",self.voice_var.get()))
        self.inputs.bind("<<ComboboxSelected>>",lambda _: self.save_device(True))
        self.outputs.bind("<<ComboboxSelected>>",lambda _: self.save_device(False))
        tk.Label(side,text="Gunakan headset agar suara Leva tidak masuk kembali ke mikrofon. AEC speaker belum terpasang.",
                 bg="#101b2c",fg="#d0ae75",wraplength=260,justify="left").pack(pady=(14,6),anchor="w")
        tk.Label(side,text="Saat Mulai suara ditekan, audio mikrofon dikirim ke Google Live. Sesi berhenti setelah 15 menit, saat dijeda, atau jendela ditutup.",
                 bg="#101b2c",fg="#8ca2b9",wraplength=260,justify="left").pack(pady=(4,8),anchor="w")
        caption("PRATINJAU POLA · MIKROFON MATI")
        self.demo=ttk.Combobox(side,textvariable=self.demo_var,values=list(STATES),state="readonly")
        self.demo.pack(fill="x")
        self.demo.bind("<<ComboboxSelected>>",self.preview)
        self.button(side,"Kembali ke teks lokal",self.local_text).pack(fill="x",pady=(12,0))
        transcript=tk.Frame(self.window,bg="#101b2c",padx=18,pady=12)
        transcript.pack(fill="x",padx=26,pady=(4,20))
        self.heard=tk.Label(transcript,text="Anda: —",bg="#101b2c",fg="#b7dce6",wraplength=960,anchor="w",justify="left")
        self.heard.pack(fill="x",pady=3)
        self.said=tk.Label(transcript,text="Leva: —",bg="#101b2c",fg="#e6c38b",wraplength=960,anchor="w",justify="left")
        self.said.pack(fill="x",pady=3)
        self.run_button=self.button(transcript,"Jalankan perintah dari transkrip",self.run_command)
        self.run_button.pack(anchor="w",pady=(8,0))
        self.run_button.configure(state="disabled")
        tk.Checkbutton(transcript,text="Perintah langsung dengan awalan ‘Leva’ (uji headset)",variable=self.direct,
                       bg="#101b2c",fg="#99afc1",selectcolor="#1b2940",activebackground="#101b2c",
                       activeforeground="#d8e4f2",bd=0).pack(anchor="w",pady=(7,0))
        self.app_result=tk.Label(transcript,text="",height=2,bg="#101b2c",fg="#9cb5bd",wraplength=950,anchor="w",justify="left")
        self.app_result.pack(fill="x",pady=(3,0))

    def load_devices(self):
        if self.service.active:
            self.notice.set("Hentikan sesi suara sebelum menyegarkan perangkat.")
            return
        try:
            self.devices=audio_devices()
            self.input_rows={f"{d['id']} · {d['name']}":d['id'] for d in self.devices["inputs"]}
            self.output_rows={f"{d['id']} · {d['name']}":d['id'] for d in self.devices["outputs"]}
            missing=False
            for box,var,rows,kind,default in [(self.inputs,self.input_var,self.input_rows,"input",self.devices["default_input"]),
                                          (self.outputs,self.output_var,self.output_rows,"output",self.devices["default_output"])]:
                box.configure(values=list(rows))
                selected=preferred_device(self.devices[kind+"s"],self.main.preferences.get(kind+"_device_name"),default)
                var.set(next((label for label,index in rows.items() if index==selected),""))
                missing = missing or selected is None
            self.start.configure(state="normal" if self.input_rows and self.output_rows else "disabled")
            self.notice.set("Perangkat tersimpan tidak ditemukan/ambigu. Pilih ulang mikrofon dan keluaran audio." if missing else "Perangkat siap · mikrofon tetap mati")
        except Exception:
            self.notice.set("Perangkat audio belum tersedia. Pratinjau animasi tetap bisa digunakan.")
            self.start.configure(state="disabled")

    def save_device(self,is_input):
        kind="input" if is_input else "output"
        rows=self.input_rows if is_input else self.output_rows
        label=self.input_var.get() if is_input else self.output_var.get()
        device=next((d for d in self.devices[kind+"s"] if d["id"]==rows.get(label)),None)
        if device:
            self.main.save_preference(kind+"_device_name",device["name"])

    def clear_command(self):
        self.final_text=""
        self.last_text=""
        self.last_dispatched=("",0.0)
        self.run_button.configure(state="disabled")

    def set_state(self,state):
        self.orb.set_state(state)
        self.heading.set(LABELS.get(state,LABELS["idle"]))

    def preview(self,_=None):
        if self.service.active:
            return
        self.orb.preview=True
        self.set_state(self.demo_var.get())
        self.notice.set("Pratinjau visual · mikrofon mati · gerak audio disimulasikan")

    def toggle(self):
        if self.service.active:
            self.stop()
            return
        if self.main.desktop.paused or self.main.desktop.sleeping:
            self.notice.set("Leva sedang jeda. Aktifkan dari jendela utama terlebih dahulu.")
            return
        if not self.input_var.get() or not self.output_var.get():
            self.notice.set("Pilih mikrofon dan perangkat keluaran terlebih dahulu.")
            return
        self.main.chat.cancel()
        self.clear_command()
        self.heard.configure(text="Anda: —")
        self.said.configure(text="Leva: —")
        self.app_result.configure(text="")
        self.save_device(True)
        self.save_device(False)
        self.orb.preview=False
        self.set_state("connecting")
        try:
            self.service.start(self.input_rows[self.input_var.get()],self.output_rows[self.output_var.get()],self.voice_var.get())
            self.start.configure(text="Hentikan suara")
            for box in [self.inputs,self.outputs,self.voices,self.demo]:
                box.configure(state="disabled")
            self.notice.set("Menghubungkan Google Live. Mikrofon dibuka setelah koneksi siap.")
        except Exception:
            self.service.stop()
            self.set_state("error")
            self.notice.set("Worker suara tidak dapat dimulai.")

    def interrupt(self):
        self.service.send({"kind":"interrupt"})
        if self.service.active:
            self.set_state("interrupted")

    def stop(self,sleeping=False):
        self.service.stop()
        self.clear_command()
        self.direct.set(False)
        self.mic_open=False
        self.orb.input_level=self.orb.output_level=0
        self.meter.configure(text="Mikrofon  ░░░░░░░░░░   Suara  ░░░░░░░░░░")
        self.orb.preview=False
        self.set_state("sleeping" if sleeping else "idle")
        self.notice.set("Mikrofon mati · audio tidak dikirim")
        self.start.configure(text="Mulai suara · Google")
        for box in [self.inputs,self.outputs,self.voices,self.demo]:
            box.configure(state="readonly")

    def poll(self):
        if self.closed:
            return
        while not self.service.events.empty():
            event=self.service.events.get_nowait()
            kind=event.get("kind")
            if kind=="state":
                self.mic_open=bool(event.get("microphone_open",self.mic_open))
                self.set_state(event["state"])
                if event["state"]=="interrupted":
                    self.hold_until=time.monotonic()+0.7
                if self.mic_open:
                    self.notice.set("Mikrofon aktif → Google Live · tetap mendengar saat Leva berbicara")
            elif kind=="meter":
                self.orb.input_level=event["input"]
                self.orb.output_level=event["output"]
                if time.monotonic()>=self.hold_until or event["output"]>0.02 or event["input"]>0.06:
                    self.set_state(event["state"])
                self.meter.configure(text="Mikrofon  "+self.bars(event["input"])+"   Suara  "+self.bars(event["output"]))
            elif kind=="input_text":
                self.last_text=event["text"]
                self.heard.configure(text="Anda: "+event["text"][-380:])
                if event.get("final"):
                    self.final_text=event["text"]
                    self.run_button.configure(state="normal")
                    if self.direct.get() and direct_command(self.final_text):
                        old,when=self.last_dispatched
                        if self.final_text!=old or time.monotonic()-when>3:
                            self.run_command()
                else:
                    self.final_text=""
                    self.run_button.configure(state="disabled")
            elif kind=="output_text":
                self.said.configure(text="Leva: "+event["text"][-380:])
            elif kind=="turn_finished":
                if re.search(r"maksud|perjelas|belum jelas|kurang jelas",event.get("text",""),re.I):
                    self.set_state("clarifying")
                    self.hold_until=time.monotonic()+4
            elif kind=="error":
                self.stop()
                self.set_state("error")
                self.notice.set(VOICE_ERRORS.get(event["code"],VOICE_ERRORS["live_connection_or_audio_error"]))
            elif kind=="notice":
                self.notice.set("Batas sesi suara tercapai. Mulai sesi baru jika diperlukan.")
            elif kind=="stopped":
                self.clear_command()
                self.direct.set(False)
                self.mic_open=False
                self.orb.input_level=self.orb.output_level=0
                self.meter.configure(text="Mikrofon  ░░░░░░░░░░   Suara  ░░░░░░░░░░")
                self.start.configure(text="Mulai suara · Google")
                for box in [self.inputs,self.outputs,self.voices,self.demo]:
                    box.configure(state="readonly")
                if self.orb.mode!="error":
                    self.set_state("idle")
                    self.notice.set("Sesi suara selesai · mikrofon mati")
        self.window.after(80,self.poll)

    @staticmethod
    def bars(value):
        size=min(10,int(value*10))
        return "█"*size+"░"*(10-size)

    def run_command(self):
        if self.main.busy:
            self.notice.set("Tunggu perintah desktop sebelumnya selesai.")
            return
        if self.final_text:
            text=self.final_text
            self.final_text=""
            self.main.send(text,commands_only=True)
            self.last_dispatched=(text,time.monotonic())
            self.run_button.configure(state="disabled")

    def desktop_result(self,text):
        self.app_result.configure(text="Aplikasi: "+text[:220]+("…" if len(text)>220 else ""))

    def local_text(self):
        self.stop()
        self.main.mode.set("Lokal · RTX 4050")
        self.main.root.lift()

    def close(self):
        self.stop()
        self.closed=True
        self.window.destroy()
        self.main.voice_window=None
