"""Explicit ASR/TTS, conversation route and local executor configuration."""
import tkinter as tk
from tkinter import ttk
from speech_resources import GPU_CHOICES,ASR_CHOICES,AGENT_CHOICES,AGENT_GPU_CHOICES
from speech_configuration import INPUT_MODELS,LANGUAGES,AGENT_ROUTES,apply_pipeline_settings

class SpeechPipelineWindow:
    def __init__(self,main):
        from gui import BG,PANEL,INK,ACCENT
        self.main=main
        self.window=tk.Toplevel(main.root);self.window.title('Leva — Suara, rute & agent')
        self.window.geometry('920x900');self.window.configure(bg=BG)
        body=tk.Frame(self.window,bg=PANEL,padx=22,pady=20);body.pack(fill='both',expand=True,padx=18,pady=18)
        self.values={}
        def choose(key,title,choices):
            main.label(body,title,fg=INK).pack(anchor='w',pady=(10,3))
            value=tk.StringVar(value=choices.get(main.preferences.get(key),next(iter(choices.values()))))
            ttk.Combobox(body,textvariable=value,values=list(choices.values()),state='readonly',width=72).pack(anchor='w')
            self.values[key]=(value,choices)
        choose('asr_model','1 · Input suara — model pengenal ucapan',INPUT_MODELS)
        choose('asr_gpu','GPU input suara — default RTX 5070',GPU_CHOICES)
        choose('asr_language','Bahasa input — terpisah dari bahasa jawaban',LANGUAGES)
        main.button(body,'Pilih engine / identitas TTS',main.open_voice_packs).pack(anchor='w',pady=6)
        main.label(body,'3 · Suara: rute toolbar hanya lokal. Asisten memakai front-end MiniCPM5 2B.\n'
            '4 · Chat / Secret: model lokal masing-masing pada tab, tanpa alat laptop.\n'
            '5 · Tugas Asisten: agent terpisah; ringkasan tidak mengganti izin/perintah asli.\n'
            'Input suara dan agent mempunyai GPU masing-masing. Ikuti rute memakai GPU toolbar.\n'
            'Pilihan RTX tunggal tidak berpindah kartu secara diam-diam. Dual input membagi encoder/decoder.\n'
            'TTS Higgs/OmniVoice: hanya satu GPU, ditetapkan ke 5070 dalam pipeline Dual.\n'
            'Higgs Q8 memerlukan headroom 8 GB; mode 4050 akan melaporkan kekurangan VRAM.\n'
            'Tanpa AI: tidak memulai percakapan, mikrofon ASR atau jawaban TTS otomatis.',justify='left',wraplength=810).pack(anchor='w',pady=10)
        choose('agent_local_model','Agent pelaksana lokal — dipanggil saat pekerjaan memerlukan alat',AGENT_CHOICES)
        choose('agent_provider','Rute & GPU agent/LLM — terpisah dari rute suara pada toolbar',AGENT_ROUTES)
        main.button(body,'Siapkan balasan awal cepat (tanpa pemutaran)',main.prepare_task_reaction).pack(anchor='w',pady=6)
        self.notice=tk.StringVar(value='Qwen ASR memakai segmen ucapan; belum native streaming/AEC penuh. Model tidak dimuat hanya dengan membuka panel.')
        main.label(body,'',textvariable=self.notice,fg=ACCENT,wraplength=810,justify='left').pack(anchor='w',pady=10)
        main.button(body,'Simpan pipeline',self.save,primary=True).pack(anchor='w')

    def save(self):
        if self.main.busy:self.notice.set('Tunggu tugas selesai sebelum mengganti pipeline.');return
        try:
            result={k:next(key for key,label in choices.items() if label==value.get()) for k,(value,choices) in self.values.items()}
            apply_pipeline_settings(self.main,result)
            self.notice.set('Tersimpan. Input suara dan agent memakai model/GPU masing-masing. Pemuatan mengikuti pemakaian berikutnya.')
        except (ValueError,OSError) as error:self.notice.set(str(error))
