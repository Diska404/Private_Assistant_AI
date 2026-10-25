"""Visible QA fixture: real Tk queue + HTTP + browser, no inference or personal data."""
import json,queue,sys,tempfile,time,tkinter as tk
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from web_host import DesktopWebHost
from web_data import WebData
from preferences import Preferences
from second_brain import SecondBrain
from conversation_memory import ConversationMemory
from task_journal import TaskJournal
from mic_indicator import MicTelemetry

OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/web-v023');OUT.mkdir(parents=True,exist_ok=True)
stopfile=OUT/'stop-preview';stopfile.unlink(missing_ok=True)
with tempfile.TemporaryDirectory(prefix='leva-web-qa-') as folder:
    base=Path(folder);vault=base/'VerificationVault';vault.mkdir()
    for i in range(120):
        (vault/f'Note_{i:03d}.md').write_text(f'# Catatan uji {i:03d}\n\nData fixture untuk menguji graf.\n[[Note_{(i+1)%120:03d}]] [[Note_{(i+11)%120:03d}]]\n',encoding='utf8')
    prefs=Preferences(base/'prefs.db');prefs.set_many({'obsidian_vault':str(vault),'web_port':'8776','always_listen':False})
    journal=TaskJournal(base/'tasks.db')
    for i in range(6):
        ident=journal.begin('Tugas verifikasi '+str(i))
        for j in range(4):journal.intent(ident,j,'obsidian_action',{'action':'read','path':f'Note_{j:03d}.md'});journal.receipt(ident,j,{'status':'done'})
        journal.finish(ident,'completed')
    root=tk.Tk();root.withdraw();m=Mock();m.root=root;m.preferences=prefs;m.events=queue.Queue();m.generation=0;m.busy=False;m.entry=tk.Entry(root)
    m.mode=tk.StringVar(value='Tanpa AI');m.dual=tk.BooleanVar(value=False);m.spoken_replies=tk.BooleanVar(value=False);m.speech_language=tk.StringVar(value='Indonesia');m.activity=tk.StringVar(value='Mode verifikasi · tanpa inferensi')
    m.desktop.paused=False;m.desktop.sleeping=False;m.desktop.tools.desktop.preferences=prefs
    m.desktop.tools.second_brain=SecondBrain(prefs,base/'index');m.desktop.tools.conversations=ConversationMemory(base/'memory.db')
    m.hardware.value={};m.local_mic.active=False;m.local_mic.telemetry=MicTelemetry();m.reply_voice.active=False;m.reply_voice.service.output_level=0
    m._web_log=[('Info','MODE UJI INTEGRASI — data catatan dan tugas contoh; tidak memakai vault pribadi atau menjalankan AI kedua.')]
    m._web_tool='';m._web_last_error='';m.last_text_ms=None;calls=[]
    host=DesktopWebHost(m);host.bridge.reader=WebData(m.desktop.tools,lambda:journal);host.bridge.bootstrap='leva-fixture-preview-only-not-a-user-secret'
    update=host.bridge.update
    host.bridge.update=lambda state:update({**state,'verification_mode':True})
    def add(speaker,text):host.bridge.log(speaker,text)
    m.add=add
    def send(value):calls.append({'text':value,'thread':'Tk main'});add('Anda',value);add('Leva · Uji integrasi','Pesan diterima oleh antrean desktop uji. Ini bukan hasil model AI.');m.activity.set('Jembatan desktop/web terverifikasi')
    m.send=send
    m.release=lambda:m.activity.set('Permintaan lepas AI diterima · fixture tanpa model')
    m.new_conversation=lambda:add('Leva','Percakapan uji baru siap.')
    host.poll();url=host.bridge.start();print(json.dumps({'origin':host.bridge.origin,'fixture':True,'pid':__import__('os').getpid()}),flush=True)
    began=time.monotonic()
    def tick():
        host.poll()
        if stopfile.exists() or time.monotonic()-began>1800:
            host.stop();root.destroy();return
        root.after(50,tick)
    root.after(50,tick)
    try:root.mainloop()
    finally:
        host.stop();prefs.close();(OUT/'preview-host.json').write_text(json.dumps({'fixture_only':True,'inference_started':False,'received':calls,'server_stopped':host.bridge.server is None},indent=2),encoding='utf8')
