"""Actual GUI poll/send/journal plumbing with synthetic ASR and a stub desktop.
No microphone, model, cloud, or external desktop action is used.
"""
import json,queue,sys,tempfile,time,tkinter as tk
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from gui import LevaWindow
from preferences import Preferences
from mic_indicator import MicTelemetry
from speech_turns import SpeechJournal
from speech_log_window import SpeechLogWindow

with tempfile.TemporaryDirectory() as folder:
    m=LevaWindow.__new__(LevaWindow);m.root=tk.Tk();m.preferences=Preferences(Path(folder)/'prefs.db')
    m.mode=tk.StringVar(value='Dual GPU');m.dual=tk.BooleanVar(value=True)
    m.spoken_replies=tk.BooleanVar(value=False);m.speech_language=tk.StringVar(value='Indonesia')
    m.status=tk.StringVar();m.activity=tk.StringVar();m.busy=True;m.closed=False;m.generation=0;m.profile_rows=[];m.link_sequence=0
    m.events=queue.Queue();m.desktop=Mock(paused=False,sleeping=False,memory_notice='')
    m.voice_window=m.voice_pack_window=m.duplex_window=None
    m.reply_voice=Mock(active=False);m.reply_voice.poll.return_value=[];m.reply_voice.service.loaded=False
    m.hardware=None;m.local_partial='';m.local_notice='Pendengar uji';m.local_mic_failed=False
    m.local_mic=Mock(active=True,state='listening',input_level=.1);m.local_mic.telemetry=MicTelemetry();m.local_mic.poll.return_value=[]
    m.chat=Mock(process=None);m.chat.history=[];m.frontend=Mock();m.frontend.history=[]
    m._speech_inbox=SpeechJournal(Path(folder)/'speech.db')
    m._layout();m.show_task_reaction=Mock();m.play_task_reaction=Mock()
    errors=[];m.root.report_callback_exception=lambda *args:errors.append(str(args))
    try:
        m.desktop.handle.return_value={'kind':'command','reply':'Uji clock: tugas selesai.','needs_input':False}
        m.receive_voice({'text':'Leva, jam berapa sekarang?','command':'jam berapa sekarang?','accepted':True,'reason':'wake'})
        m.receive_voice({'text':'Leva, tanggal berapa hari ini?','command':'tanggal berapa hari ini?','accepted':True,'reason':'wake'})
        assert len(m._speech_inbox.pending())==2
        m.poll();m.root.after(150,m.root.quit);m.root.mainloop()
        assert not m.desktop.handle.called,'busy task was replaced'
        m.set_busy(False);deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            m.root.after(100,m.root.quit);m.root.mainloop()
            rows=m._speech_inbox.recent()
            if len(rows)==2 and all(r['state']=='completed' for r in rows):break
        assert [c.args[0] for c in m.desktop.handle.call_args_list]==['jam berapa sekarang?','tanggal berapa hari ini?']
        assert all(r['state']=='completed' for r in rows),rows
        raw='Leva, catatan panjang tanpa dipotong. '*200
        row=m._speech_inbox.capture({'text':raw,'reason':'awaiting_wake'})
        window=SpeechLogWindow(m);window.tree.selection_set(row['id']);window.show()
        assert window.text.get('1.0','end-1c')==raw
        m.root.after(150,m.root.quit);m.root.mainloop()
        assert not errors,errors
        proof={'synthetic_asr':True,'desktop_executor_stubbed':True,'actual_gui_poll_and_send_used':True,
            'commands_completed_in_order':True,'busy_task_not_cancelled':True,'full_log_text_characters':len(raw),
            'selected_full_text_matches':True,'tk_callback_errors':errors}
    finally:
        m.closed=True;m.preferences.close();m.root.destroy()
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/speech-turns-v0214');out.mkdir(parents=True,exist_ok=True)
(out/'dispatch-ui.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
