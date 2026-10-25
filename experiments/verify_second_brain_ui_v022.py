"""Real Tk widgets + real fixture reader; no personal vault or external action."""
import json,sys,tempfile,time,tkinter as tk
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from preferences import Preferences
from second_brain import SecondBrain
from second_brain_window import SecondBrainPanel

OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/second-brain-v022');OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    base=Path(folder);vault=base/'vault';vault.mkdir();(vault/'GPU.md').write_text('# GPU\nRTX 4050 + RTX 5070\n[[Links]]\n',encoding='utf8')
    (vault/'Links.md').write_text('# Links\n[[GPU]]\n',encoding='utf8')
    prefs=Preferences(base/'preferences.db');prefs.set('obsidian_vault',str(vault))
    main=Mock();main.busy=False;main.preferences=prefs;main.desktop.tools.second_brain=SecondBrain(prefs,base/'index')
    main.button=lambda parent,text,command,**kwargs:tk.Button(parent,text=text,command=command)
    root=tk.Tk();root.withdraw();root.geometry('1000x780');errors=[];root.report_callback_exception=lambda *args:errors.append(str(args))
    parent=tk.Frame(root);parent.pack(fill='both',expand=True);panel=SecondBrainPanel(parent,main)
    def settle():
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and panel.busy:root.update();time.sleep(.02)
        root.update();assert not panel.busy and not errors,(panel.busy,errors)
    try:
        settle();assert len(panel.rows.get_children())==2
        panel.query.set('RTX');panel.search();settle();assert len(panel.rows.get_children())==1
        panel.rows.selection_set(panel.rows.get_children()[0]);panel.read();settle()
        assert 'RTX 4050' in panel.output.get('1.0','end')
        panel.related();settle();assert 'Links.md' in panel.output.get('1.0','end')
        panel.ask();main.send.assert_called_once();assert 'Obsidian' in main.send.call_args.args[0]
        with patch('second_brain_window.os.startfile') as open_folder:panel.open_folder();open_folder.assert_called_once_with(str(vault))
        parent.destroy();root.update()
        proof={'video_id':'VIDEO_001','real_tk_widgets':True,'fixture_only':True,'list_search_read_related':True,'agent_dispatch':True,
            'callbacks_errors':errors,'external_folder_opened':False,'personal_vault_used':False,'closed_cleanly':True}
    finally:root.destroy();prefs.close()
(OUT/'ui-check.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
