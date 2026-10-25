"""Desktop workspace transitions and tool-free request dispatch."""
import threading
import re
import time
from collections import deque
from conversation_rooms import ROOMS,GPUS,model_choices,validate_room_settings
from conversation_attachments import compose_message
from hybrid_engine import EngineError

def switch_workspace(main,workspace):
    if workspace not in ROOMS:raise ValueError('invalid_workspace')
    if workspace=='companion_avatar' and main.preferences.get('companion_enabled') is not True:raise ValueError('Aktifkan pratinjau Leva ♡ terlebih dahulu.')
    if main.busy or getattr(main,'_translation_pending',False):raise ValueError('Tunggu jawaban aktif selesai atau tekan Lepaskan AI sebelum berpindah ruang.')
    if workspace==getattr(main,'workspace','assistant'):return
    main.stop_reply_voice();main.cancel_inference();main.cancel_voice_queue()
    main.room_attachments=[]
    if hasattr(main,'attachment_label'):main.attachment_label.set('')
    main.workspace=workspace
    button=getattr(main.hud,'process_button',None)
    if button:
        if workspace in ('secret','companion_avatar'):button.pack_forget()
        else:button.pack(side='right',padx=4)
    main.companion_mic_consent=False
    if workspace=='companion_avatar':main.local_mic.stop()
    main.entry.delete(0,'end')
    main.history=main.room_views[workspace]
    main._web_log=deque(main._assistant_log if workspace=='assistant' else main.rooms.rows(workspace),maxlen=120)
    host=getattr(main,'_web_host',None)
    if host:
        with host.bridge.lock:
            host.bridge.logs.clear()
            for s,t in main._web_log:host.bridge.log(s,t)
            host.bridge.revision+=1
    main.hud.tabs.select(list(ROOMS).index(workspace))
    main.status.set(ROOMS[workspace]+' · '+('alat laptop aktif' if workspace=='assistant' else 'percakapan lokal · tanpa kendali laptop'))
    from presence_companion import greet,touch
    touch(main);greet(main,workspace)

def apply_room_settings(main,values):
    value=validate_room_settings(values)
    from model_registry import TRIALS
    if value['model'] in TRIALS and main.preferences.get('experimental_models_enabled') is not True:raise ValueError('Aktifkan model eksperimen terlebih dahulu. Model produksi tidak diganti otomatis.')
    if main.busy or getattr(main,'_translation_pending',False):raise ValueError('Tunggu jawaban selesai sebelum mengganti model.')
    r=value['workspace'];main.preferences.set_many({r+'_model':value['model'],r+'_gpu':value['gpu']})
    main.rooms.cancel();return value

def attach_file(main):
    from tkinter import filedialog,messagebox
    from pathlib import Path
    from conversation_attachments import MAX_BYTES
    if main.busy:return
    path=filedialog.askopenfilename(parent=main.root,title='Lampirkan bahan untuk percakapan',filetypes=[('Teks, kode, PDF','*.txt *.md *.pdf *.py *.js *.ts *.json *.csv *.ino *.html *.css'),('Semua','*.*')])
    if not path:return
    try:
        p=Path(path)
        if p.stat().st_size>MAX_BYTES:raise ValueError('Lampiran maksimal 6 MB.')
        from file_workspace import checked_path
        p=checked_path(str(p))
        row={'name':p.name,'local_reference':str(p),'truncated':False}
        if len(main.room_attachments)>=3:raise ValueError('Maksimal 3 lampiran per pesan.')
        main.room_attachments.append(row);main.attachment_label.set('Lampiran: '+', '.join(r['name']+(' (cuplikan)' if r['truncated'] else '') for r in main.room_attachments))
    except (ValueError,OSError) as error:messagebox.showerror('Lampiran',str(error),parent=main.root)

def send_room(main,text,display=None,voice_id=None,attachments=None):
    from input_normalization import normalize_input
    normalized=normalize_input(text);original=text;text=normalized['text']
    room=main.workspace
    if room not in ROOMS:raise ValueError('invalid_conversation_room')
    if room=='companion_avatar' and main.preferences.get('companion_enabled') is not True:raise ValueError('companion_disabled')
    from conversation_attachments import materialize
    rows=materialize(list(attachments if attachments is not None else main.room_attachments))
    if not text.strip() or len(text)>3000:return
    goal=compose_message(text,rows)
    if len(goal)>18000:raise ValueError('Bahan terlalu panjang untuk konteks percakapan ini.')
    if room=='assistant':
        from pipeline_routing import route_spec
        from speech_resources import agent_mode
        model=main.preferences.get('agent_local_model');gpu=agent_mode(route_spec(main.preferences.get('agent_provider')),main.preferences.get('agent_gpu'))
        if gpu is None:main.add('Info','Agent/LLM sedang dinonaktifkan.');return False
    else:
        model=main.preferences.get(room+'_model');gpu=main.preferences.get(room+'_gpu')
        if model in __import__('model_registry').TRIALS and main.preferences.get('experimental_models_enabled') is not True:raise ValueError('experimental_model_opt_in_required')
        validate_room_settings({'workspace':room,'model':model,'gpu':gpu})
    main.rooms.service(room)  # Restore past context before logging this new user turn.
    main.stop_reply_voice();main.frontend.cancel();main.chat.cancel()
    main.room_attachments=[]
    if hasattr(main,'attachment_label'):main.attachment_label.set('')
    if not voice_id:main.add('Anda',(display or original)+(' ⎯ Lampiran: '+', '.join(r['name'] for r in rows) if rows else ''))
    if normalized['edits']:main.add('Info · Input','Koreksi ejaan: '+', '.join(e['from']+' → '+e['to'] for e in normalized['edits'])+'. Maksud asli tetap dipertahankan.')
    main.entry.delete(0,'end');main.set_busy(True);main.generation+=1;generation=main.generation
    if voice_id:main.active_voice=(voice_id,generation)
    from task_progress import tracker,begin_request
    progress=begin_request(main,ROOMS[room]);progress.add('understand','Memahami arah percakapan dan konteks ruang')
    from leva_persona import DELIVERY
    from leva_persona import simple_greeting
    if room in ('assistant','chat') and (rows or not simple_greeting(text)):main.add('Leva · Proses',DELIVERY.acknowledgement(text,room))
    language=main.preferences.get('speech_language');want_voice=main.spoken_replies.get()
    from pipeline_routing import route_spec
    from speech_resources import pipeline_gpu
    voice_route=route_spec(main.mode.get(),main.dual.get())
    tts_gpu=pipeline_gpu(voice_route,'tts',main.preferences.get('tts_gpu')) if voice_route['gpu']!='none' else 'none'
    keep_room_warm=main.preferences.get('keep_models_warm') and (not want_voice or gpu in ('gpu4050','gpu5070') and gpu.replace('gpu','rtx')!=tts_gpu)
    from conversation_stream import begin,prepare_voice,receive,finish
    capture=begin(main,room,model,gpu,language,want_voice)
    main.activity.set('Menyiapkan '+ROOMS[room]+' · '+model_choices(room,include_trials=model in __import__('model_registry').TRIALS)[model]);started=time.perf_counter()
    # Shared VRAM is sequential: our ASR worker yields to this room, while capture remains active.
    main.audio_resource_hold=True
    def run():
        published=False
        try:
            main.local_mic.hold_asr()
            try:prepare_voice(main,capture)
            except (ValueError,OSError,RuntimeError):capture['pipeline']=None
            from conversation_intent import intent
            direction=intent(text)
            if room in ('chat','secret') and (direction['kind']=='action' or room=='secret' and direction['kind']=='information') and direction['confidence']>=.9:
                target='assistant' if direction['kind']=='action' else 'chat'
                main.rooms.propose(target,text,source=room)
                result={'provider':'local','response':'Aku bisa meneruskan pekerjaan ini ke '+ROOMS[target]+'. Mau berpindah dan menyalin riwayat '+ROOMS[room]+'? Jawab “ya, pindah” atau gunakan tombol Salin & lanjut. Tindakan belum dijalankan.'}
            else:
                stream_options={'stream_callback':lambda event:receive(main,capture,event)} if main.preferences.get('streaming_text') is True else {}
                result=main.rooms.answer(room,goal,model,gpu,keep_warm=keep_room_warm or capture['pipeline'] is not None,intent_text=text,has_attachments=bool(rows),playful=main.preferences.get('companion_playful'),progress=lambda stage,label:main.events.put((generation,{'_progress_event':progress.add(stage,label)})),**stream_options)
            if generation!=main.generation:return
            reply=result.get('response','')
            personal=room=='secret' or result.get('routing',{}).get('kind')=='personal'
            result.update(engine_role=result.get('engine_role',ROOMS[room]),_speech_language=language,_speech_style={'style':'personal' if personal else 'assistant'},_speak_reply=want_voice,text_ready_ms=round((time.perf_counter()-started)*1000,2))
            streamed_voice=finish(main,capture,reply)
            if streamed_voice:result['_speak_reply']=False;result['_streamed_voice']=True
            if not streamed_voice and language=='ja' and want_voice and reply and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',result.get('speech_text','')):
                main.events.put((generation,{**result,'_speak_reply':False,'_translation_pending':True}));published=True
                main.rooms.cancel()
                from speech_translation import translate_speech
                def authorized():return generation==main.generation and getattr(main,'_muted_voice_generation',None)!=generation and not getattr(main,'closed',False)
                translated=translate_speech(main.frontend,reply,gpu,authorized=authorized,
                    progress=lambda p:main.events.put((generation,{'_translation_progress':p})))
                result={'_voice_only':True,'speech_text':translated['text'],'_speech_style':result['_speech_style'],'translation_metrics':{k:v for k,v in translated.items() if k!='text'}}
            if generation==main.generation:main.events.put((generation,result))
        except Exception as error:
            if capture.get('pipeline'):capture['pipeline'].cancel()
            code=str(error) if isinstance(error,EngineError) else 'conversation_room_failure'
            if generation==main.generation:main.events.put((generation,{'_voice_only':True,'_voice_notice':'Terjemahan belum berhasil. Teks tetap tersedia. Kode: '+code} if published else {'error':code}))
    threading.Thread(target=run,daemon=True).start()

def add_room_tabs(hud,tabs):
    import tkinter as tk
    from tkinter import ttk
    from hud_view import BG,PANEL,INK,ACCENT,MUTED,CARD
    main=hud.main
    if not hasattr(main,'rooms'):
        from conversation_rooms import ConversationRooms
        main.rooms=ConversationRooms(main.preferences.path.parent/'conversation-rooms.sqlite3')
    if not hasattr(main,'workspace'):main.workspace='assistant';main.room_attachments=[];main._assistant_log=deque(maxlen=120)
    main.room_views={'assistant':main.history};main.room_controls={}
    # Insert before the module map. The shared composer and local voice toolbar stay available.
    main.room_frames={};main.room_model_pickers={}
    for index,room in enumerate(('chat','secret','companion_avatar'),1):
        frame=tk.Frame(tabs,bg=PANEL,padx=24,pady=18);tabs.insert(index,frame,text='  '+ROOMS[room]+'  ')
        main.room_frames[room]=frame
        top=tk.Frame(frame,bg=PANEL);top.pack(fill='x')
        hud.text(top,ROOMS[room],fg='#e8b1d1' if room=='secret' else '#a0bff2',font=('Segoe UI',23)).pack(side='left')
        hud.button(top,'Percakapan baru',main.new_conversation).pack(side='right')
        from conversation_export import copy_conversation,save_conversation
        hud.button(top,'Salin semua',lambda:copy_conversation(main)).pack(side='right',padx=6)
        hud.button(top,'Simpan laporan',lambda:save_conversation(main)).pack(side='right')
        hud.text(frame,'Pikirkan bersama. Baca, tanyakan, dan temukan hubungannya.' if room=='chat' else 'Tempat untuk cerita kecil, obrolan santai, dan harimu ~',fg=MUTED).pack(anchor='w',pady=8)
        controls=tk.Frame(frame,bg=PANEL);controls.pack(fill='x',pady=8)
        choices=model_choices(room,include_trials=main.preferences.get('experimental_models_enabled') is True);model=tk.StringVar(value=choices.get(main.preferences.get(room+'_model'),'Model eksperimen dinonaktifkan'));gpu=tk.StringVar(value=GPUS[main.preferences.get(room+'_gpu')])
        main.room_controls[room]=(model,gpu,choices)
        picker=ttk.Combobox(controls,textvariable=model,values=list(choices.values()),state='readonly',width=52);picker.pack(side='left',padx=(0,8))
        main.room_model_pickers[room]=picker
        gpicker=ttk.Combobox(controls,textvariable=gpu,values=list(GPUS.values()),state='readonly',width=13);gpicker.pack(side='left')
        def save(r=room,m=model,g=gpu,c=choices):
            try:apply_room_settings(main,{'workspace':r,'model':next(k for k,v in c.items() if v==m.get()),'gpu':next(k for k,v in GPUS.items() if v==g.get())})
            except ValueError as error:
                from tkinter import messagebox
                messagebox.showinfo('Model percakapan',str(error),parent=main.root)
        picker.bind('<<ComboboxSelected>>',lambda e,f=save:f());gpicker.bind('<<ComboboxSelected>>',lambda e,f=save:f())
        transfer=tk.Frame(frame,bg=PANEL)
        if room in ('chat','secret'):
            transfer.pack(fill='x',pady=4)
            hud.text(transfer,'Salin seluruh riwayat saat pindah:',fg=MUTED).pack(side='left')
            if room=='secret':hud.button(transfer,'Salin & lanjut ke Chat',lambda:accept_handoff(main,'chat')).pack(side='left',padx=6)
            hud.button(transfer,'Salin & lanjut ke Asisten',lambda:accept_handoff(main,'assistant')).pack(side='left')
            if room=='secret':hud.text(frame,'Secret adalah nama ruang; riwayat lokal tidak dienkripsi dan dibagikan ke perangkat yang dipasangkan.',fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',pady=4)
        if room=='companion_avatar':
            hud.button(frame,'Buka panggung avatar di Web / HP',main.open_web).pack(anchor='w',pady=6)
            hud.text(frame,'Placeholder orisinal · lokal · tanpa alat PC · riwayat hanya sesi ini · mic laptop perlu diaktifkan manual',fg=MUTED,wraplength=900).pack(anchor='w',pady=4)
        body=tk.Frame(frame,bg=PANEL);body.pack(fill='both',expand=True)
        history=tk.Text(body,wrap='word',bg=PANEL,fg=INK,relief='flat',padx=12,pady=12,state='disabled',font=('Segoe UI',11));history.pack(side='left',fill='both',expand=True)
        scroll=tk.Scrollbar(body,command=history.yview,width=10);scroll.pack(side='right',fill='y');history.configure(yscrollcommand=scroll.set)
        for tag,col in [('Leva',ACCENT),('Anda','#a6c5ff'),('Info',MUTED),('AI','#cdbbff')]:history.tag_configure(tag,foreground=col,font=('Segoe UI',10,'bold'),spacing1=8,spacing3=4)
        history.tag_configure('body',spacing3=22);history.tag_configure('assistant_align',justify='right',lmargin1=45,lmargin2=45,rmargin=8,background='#132c2c');history.tag_configure('user_align',justify='left',lmargin1=8,lmargin2=8,rmargin=45,background='#142634')
        history.tag_configure('assistant_align',background='#2b2032' if room=='secret' else '#172b3b')
        main.room_views[room]=history
        hud.check(top,'Teks 日本語',hud.translation_visible).pack(side='right',padx=8)
        history.tag_configure('spoken_translation',elide=not main.preferences.get('show_japanese'))
        from conversation_export import install_menu,mark_message
        install_menu(main,history)
        history.configure(state='normal')
        for speaker,text in main.rooms.rows(room):
            start=history.index('end-1c');history.insert('end',speaker+'\n'+text+'\n\n',('user_align' if speaker.startswith('Anda') else 'assistant_align',));mark_message(history,start)
        history.configure(state='disabled')
        controls.pack_forget();transfer.pack_forget()
        hud.button(top,'Model & ruang',lambda c=controls,t=transfer,b=body:toggle_room_options(c,t,b)).pack(side='right',padx=6)
        hide_translation_rows(history,main.preferences.get('show_japanese'))
        if room=='companion_avatar' and main.preferences.get('companion_enabled') is not True:tabs.hide(frame)
    def select(event):
        index=tabs.index(tabs.select())
        if index<4:
            selected=str(tabs.select())
            actual=next((r for r,f in main.room_frames.items() if str(f)==selected),'assistant' if index==0 else None)
            if actual is None:return
            try:switch_workspace(main,actual)
            except ValueError:tabs.select(list(ROOMS).index(main.workspace))
    tabs.bind('<<NotebookTabChanged>>',select)


def accept_handoff(main,target):
    if main.busy or getattr(main,'_translation_pending',False):return False
    source=main.workspace
    if source not in ('chat','secret') or target not in ('chat','assistant') or source==target:raise ValueError('invalid_handoff')
    from chat_service import bounded_history
    pending=main.rooms.pending
    if pending and pending.get('source','secret')!=source:raise ValueError('handoff_source_changed')
    goal=pending['goal'] if pending and pending['target']==target else ''
    rows=main.rooms.clone(source,target)
    main.rooms.clear_pending()
    if target=='assistant':
        main._assistant_log.extend(rows)
        main.chat.history=bounded_history([*main.chat.history,*[{'role':'user' if s.startswith('Anda') else 'assistant','content':t} for s,t in rows if __import__('room_memory').dialogue(s)]])
        main.frontend.history=list(main.chat.history)
    switch_workspace(main,target)
    view=main.room_views[target];view.configure(state='normal');view.delete('1.0','end')
    from conversation_export import mark_message
    for speaker,text in (main._assistant_log if target=='assistant' else main.rooms.rows(target)):
        start=view.index('end-1c');view.insert('end',speaker+'\n'+text+'\n\n',('user_align' if speaker.startswith('Anda') else 'assistant_align',));mark_message(view,start)
    view.configure(state='disabled');hide_translation_rows(view,main.preferences.get('show_japanese'));view.see('end')
    main.add('Info','Riwayat '+ROOMS[source]+' disalin ke '+ROOMS[target]+'. Sumber tetap tersimpan; konteks aktif mengikuti batas model.')
    if goal:
        # Re-enter the destination's dispatch only after explicit acceptance.
        main.send(goal,workspace=target)
    return True


def sync_room_controls(main):
    for room,(model,gpu,choices) in getattr(main,'room_controls',{}).items():
        key=main.preferences.get(room+'_model')
        if key not in choices:
            from model_registry import TRIALS
            if key in TRIALS:choices[key]=TRIALS[key]['label']+' · aktifkan model eksperimen untuk memakai'
        selected=choices[key]
        if model.get()!=selected:model.set(selected)
        selected_gpu=GPUS[main.preferences.get(room+'_gpu')]
        if gpu.get()!=selected_gpu:gpu.set(selected_gpu)


def toggle_room_options(controls,transfer,body):
    if controls.winfo_manager():controls.pack_forget();transfer.pack_forget()
    else:controls.pack(fill='x',pady=8,before=body);transfer.pack(fill='x',pady=4,before=body)

def hide_translation_rows(view,visible):
    value=view.get('1.0','end-1c');offset=0;inside=False
    for line in value.splitlines(keepends=True):
        if line.startswith('Ucapan'):inside=True
        elif inside and line.startswith(('Anda','Leva','Info')):inside=False
        if inside:view.tag_add('spoken_translation','1.0+'+str(offset)+'c','1.0+'+str(offset+len(line))+'c')
        offset+=len(line)
    view.tag_configure('spoken_translation',elide=not visible)
