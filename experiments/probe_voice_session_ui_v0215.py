"""Real Tk widgets with injected PCM telemetry; no microphone/model is opened."""
import json,sys,tempfile,time,tkinter as tk
import faulthandler
faulthandler.dump_traceback_later(6,repeat=False)
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
    m.chat=Mock();m.frontend=Mock();m.retry_local_mic=Mock();m.arm_local_mic=Mock();m.open_speech_log=Mock();m.toggle_dictation=Mock();m._layout()
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
            m.root.geometry(f'{width}x{height}');m.root.after(200,m.root.quit);m.root.mainloop();m.root.update_idletasks()
            card=indicator.frame
            top=card.winfo_rooty()-m.root.winfo_rooty();bottom=top+card.winfo_height()
            assert top>=0 and bottom<height,(height,top,bottom)
            assert m.history.winfo_height()>=100,(m.history.winfo_height(),m.root.winfo_geometry(),m.hud.tabs.select(),m.hud.tabs.tabs(),card.winfo_geometry(),m.history.master.winfo_geometry())
            assert card.winfo_width()>=400,card.winfo_width()
            assert indicator.canvas.winfo_height()>=120,indicator.canvas.winfo_height()
            assert indicator.canvas.winfo_width()>=90,indicator.canvas.winfo_width()
            proof['layouts'].append({'window':[width,height],'indicator_bottom':bottom,'chat_height':m.history.winfo_height(),'indicator_width':card.winfo_width()})
        # Both vertical bars are siblings beside the orb, above the Jam button row.
        canvas=indicator.canvas
        track=canvas.coords('mic_track');leva_track=canvas.coords('leva_track')
        assert track[3]-track[1]>4*(track[2]-track[0]),track
        assert canvas.winfo_rootx()>m.hud.orb.winfo_rootx()+m.hud.orb.winfo_width()
        assert canvas.winfo_rootx()+canvas.winfo_width()<=m.history.winfo_rootx()
        proof['vertical_bars_beside_orb']=True
        indicator.retry_button.invoke();m.retry_local_mic.assert_called_once()
        proof['manual_retry_button_wired']=True
        indicator.arm_button.invoke();m.arm_local_mic.assert_called_once()
        indicator.history_button.invoke();m.open_speech_log.assert_called_once()
        proof['manual_arm_and_history_buttons_wired']=True
        indicator.dictate_button.invoke();m.toggle_dictation.assert_called_once()
        proof['dictation_button_wired']=True
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons=[w for w in descendants(m.root) if isinstance(w,tk.Button)]
        jam=next(w for w in buttons if w.cget('text')=='Jam')
        microphone=next(w for w in buttons if w.cget('text')=='Mikrofon ↗')
        assert canvas.winfo_rooty()>=microphone.winfo_rooty()+microphone.winfo_height()
        assert canvas.winfo_rooty()+canvas.winfo_height()<=jam.winfo_rooty()
        proof['meters_between_microphone_and_jam']=True
        proof['meter_dimensions']=[canvas.winfo_width(),canvas.winfo_height()]
        mic_snapshot=state.snapshot(now=state.last_meter);indicator.update(mic_snapshot)
        before=canvas.coords('mic_fill')
        indicator.update(mic_snapshot,output={'state':'playing','rms_db':-12,'peak_db':-6})
        mic_fill=canvas.coords('mic_fill');leva_fill=canvas.coords('leva_fill')
        assert leva_fill[1]<leva_track[3] and mic_fill==before
        proof['independent_leva_output_bar']=True
        indicator.update(state.snapshot(),output={'state':'off','rms_db':-80,'peak_db':-80})
        assert canvas.coords('leva_fill')[1]==leva_track[3]
        proof['output_returns_to_zero']=True
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
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-session-v0215');out.mkdir(parents=True,exist_ok=True)
(out/'ui-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
faulthandler.cancel_dump_traceback_later()
print(json.dumps(proof))
