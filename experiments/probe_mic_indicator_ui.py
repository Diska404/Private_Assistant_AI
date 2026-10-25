"""Real Tk widgets with injected PCM telemetry; no microphone/model is opened."""
import json,sys,tempfile,time,tkinter as tk
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from gui import LevaWindow
from preferences import Preferences
from mic_indicator import MicTelemetry

proof={'real_microphone_opened':False,'model_loaded':False,'layouts':[]}
with tempfile.TemporaryDirectory() as folder:
    m=LevaWindow.__new__(LevaWindow);m.root=tk.Tk();m.root.title('Leva · uji indikator mic')
    m.preferences=Preferences(Path(folder)/'preferences.db');m.mode=tk.StringVar(value='Dual GPU');m.dual=tk.BooleanVar(value=True)
    m.spoken_replies=tk.BooleanVar(value=False);m.speech_language=tk.StringVar(value='日本語')
    m.status=tk.StringVar();m.activity=tk.StringVar();m.busy=False;m.closed=False;m.profile_rows=[]
    m.desktop=Mock(paused=False,sleeping=False);m.voice_window=m.voice_pack_window=m.duplex_window=None
    m.reply_voice=Mock(active=False);m.hardware=None;m.local_partial='';m.local_notice='Pendengar lokal'
    m.local_mic=Mock(active=True,state='listening',input_level=.24);m.local_mic.telemetry=MicTelemetry()
    m.chat=Mock();m.frontend=Mock();m._layout()
    indicator=m.hud.mic_indicator;state=m.local_mic.telemetry
    errors=[];m.root.report_callback_exception=lambda *args:errors.append(str(args))
    try:
        state.apply({'kind':'local_status','microphone_open':True,'device_name':'Headset · Synthetic UI'})
        state.apply({'kind':'local_meter','rms':.03,'peak':.2,'voiced':True,'threshold':.009})
        raw='Ay, lipa. Tolong jangan buka Chrome sebelum jam 19:00.'
        state.apply({'kind':'local_heard','text':raw,'reason':'awaiting_wake','asr_ms':1234})
        m.hud.sync();m.root.update_idletasks()
        assert indicator.heard.get('1.0','end-1c')==raw
        assert 'Belum diteruskan' in indicator.decision.cget('text')
        assert 'dBFS' in indicator.level.cget('text')
        assert indicator.heard.cget('state')=='disabled'
        proof.update(raw_unaccepted_transcript_visible=True,transcript_readonly=True,threshold_dbfs_visible=True)
        for width,height in ((1340,860),(1140,760)):
            m.root.geometry(f'{width}x{height}');m.root.update();m.root.update_idletasks()
            card=indicator.frame
            top=card.winfo_rooty()-m.root.winfo_rooty();bottom=top+card.winfo_height()
            assert top>=0 and bottom<height,(height,top,bottom)
            assert m.history.winfo_height()>=100,(m.history.winfo_height(),m.root.winfo_geometry(),m.hud.tabs.select(),m.hud.tabs.tabs(),card.winfo_geometry(),m.history.master.winfo_geometry())
            assert card.winfo_width()>=400,card.winfo_width()
            proof['layouts'].append({'window':[width,height],'indicator_bottom':bottom,'chat_height':m.history.winfo_height(),'indicator_width':card.winfo_width()})
        state.apply({'kind':'local_meter','rms':.4,'peak':1,'clipped':True})
        indicator.update(state.snapshot());assert 'Terlalu keras' in indicator.state.cget('text')
        proof['clipping_warning_visible']=True
        indicator.update(state.snapshot(active=False));assert 'tidak aktif' in indicator.state.cget('text')
        proof['disabled_capture_not_shown_as_listening']=True
        indicator.update(state.snapshot(active=False),google={'level':.4,'text':'Halo Leva.'})
        assert 'relatif' in indicator.level.cget('text');assert indicator.heard.get('1.0','end-1c')=='Halo Leva.'
        proof['google_relative_meter_and_transcript']=True
        assert not errors,errors
        proof['tk_callback_errors']=errors
    finally:m.preferences.close();m.root.destroy()
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/mic-indicator-v0211');out.mkdir(parents=True,exist_ok=True)
(out/'ui-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
print(json.dumps(proof))
