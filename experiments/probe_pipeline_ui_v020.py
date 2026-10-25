"""Real Tk route widgets with isolated preferences; no mic, models or desktop actions."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import Mock
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from gui import LevaWindow
from preferences import Preferences
from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,route_spec
from speech_pipeline_window import SpeechPipelineWindow

proof={'microphone_opened':False,'model_loaded':False,'checks':[]}
with tempfile.TemporaryDirectory() as folder:
    m=LevaWindow.__new__(LevaWindow);m.root=tk.Tk();m.root.title('Leva · uji UI terisolasi')
    m.preferences=Preferences(Path(folder)/'p.db');m.mode=tk.StringVar(value='RTX 5070')
    m.dual=tk.BooleanVar(value=False);m.last_single_gpu='rtx5070';m.local_mic=Mock(active=False)
    m.chat=Mock();m.frontend=Mock()
    m.spoken_replies=tk.BooleanVar(value=False);m.speech_language=tk.StringVar(value='日本語')
    m.status=tk.StringVar();m.activity=tk.StringVar();m.busy=False;m.profile_rows=[]
    m._layout()
    m.mode.trace_add('write',lambda *_:m.route_changed());m.dual.trace_add('write',lambda *_:m.dual_changed())
    m.root.update_idletasks()
    try:
        for initial in SINGLE_CHOICES:
            m.mode.set(initial);m.dual.set(True)
            assert tuple(m.provider['values'])==DUAL_CHOICES
            assert m.mode.get() in DUAL_CHOICES
            spec=route_spec(m.mode.get(),m.dual.get())
            assert spec['mode']=='commands' or spec['local_mode']=='dual'
            m.dual.set(False)
            assert tuple(m.provider['values'])==SINGLE_CHOICES
            assert m.mode.get()==initial
            proof['checks'].append({'initial':initial,'dual_runtime':spec,'restored':m.mode.get()})
        panel=SpeechPipelineWindow(m);m.root.update_idletasks()
        assert 'asr_model' in panel.values and 'tts_gpu' in panel.values and 'agent_local_model' in panel.values and 'agent_gpu' in panel.values
        proof['settings_widgets']=True
        proof['route_picker_width']=m.provider.winfo_width()
        proof['window_size']=[m.root.winfo_width(),m.root.winfo_height()]
        panel.window.destroy()
    finally:
        m.preferences.close();m.root.destroy()
root=Path('D:/AI/AI Lokal Asisten/Leva/verification/responsive-v020');root.mkdir(parents=True,exist_ok=True)
(root/'ui-pipeline-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cases':len(proof['checks']),'settings_widgets':proof['settings_widgets']}))
