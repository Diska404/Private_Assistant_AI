"""Local clipboard/export helpers. Nothing is uploaded or used for training."""
from datetime import datetime,timezone
import json

def transcript(rows,workspace='assistant',diagnostics=None):
    if workspace not in ('assistant','chat','secret','companion_avatar'):raise ValueError('invalid_workspace')
    # Memory entries are bounded; exports must retain all prose.
    from conversation_memory import redact_export
    messages=[{'speaker':str(s),'text':redact_export(str(t))} for s,t in rows]
    return {'schema':'leva.conversation.v1','workspace':workspace,'exported_at':datetime.now(timezone.utc).isoformat(),
            'messages':messages,'message_count':len(messages),'diagnostics':diagnostics or {},
            'privacy':'Ekspor lokal; credential disamarkan. Tidak diunggah dan bukan training otomatis.',
            'text':'\n\n'.join(r['speaker']+'\n'+r['text'] for r in messages)}

def current_transcript(main,workspace=None):
    room=workspace or getattr(main,'workspace','assistant')
    if room!=getattr(main,'workspace','assistant'):raise ValueError('workspace_changed_retry')
    rows=main.rooms.rows(room,limit=None)
    if not rows:rows=list(getattr(main,'_assistant_log',())) if room=='assistant' else []
    from paths import ROOT
    VERSION=json.loads((ROOT/'LEVA_PROJECT.json').read_text(encoding='utf-8-sig')).get('version','unknown')
    diagnostics={'version':VERSION,'workspace':room,'translation_pending':bool(getattr(main,'_translation_pending',False)),
                 'voice_progress':main.reply_voice.progress() if hasattr(main,'reply_voice') else {}}
    from task_progress import tracker
    diagnostics['task_progress']=tracker(main).snapshot()
    if hasattr(main,'preferences'):
        values={k:main.preferences.get(k) for k in ('chat_model','chat_gpu','secret_model','secret_gpu','asr_model','asr_gpu','tts_gpu','agent_local_model','agent_gpu','speech_language','target_voice_pack')}
        diagnostics['settings']={k:v for k,v in values.items() if isinstance(v,(str,int,float,bool)) or v is None}
    return transcript(rows,room,diagnostics)

def clipboard(main,text):
    main.root.clipboard_clear();main.root.clipboard_append(text)
    main.status.set('Tersalin ke clipboard · tidak diunggah otomatis')

def copy_conversation(main):clipboard(main,current_transcript(main)['text'])

def save_conversation(main):
    from tkinter import filedialog
    from pathlib import Path
    path=filedialog.asksaveasfilename(parent=main.root,title='Simpan laporan percakapan lokal',defaultextension='.json',filetypes=[('Laporan JSON','*.json'),('Percakapan teks','*.txt')])
    if path:
        data=current_transcript(main)
        Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2) if path.lower().endswith('.json') else data['text'],encoding='utf-8')
        main.status.set('Percakapan disimpan lokal; kirim secara manual bila ingin ditinjau.')

def install_menu(main,view):
    import tkinter as tk
    menu=tk.Menu(view,tearoff=False)
    def selection():
        try:clipboard(main,view.get('sel.first','sel.last'))
        except tk.TclError:main.status.set('Pilih teks yang ingin disalin.')
    def message_at(index):
        tags=view.tag_names(index)
        for tag in tags:
            if tag.startswith('copy_message_'):
                ranges=view.tag_ranges(tag)
                if ranges:clipboard(main,view.get(ranges[0],ranges[-1]).strip());return
        selection()
    target={'index':'1.0'}
    menu.add_command(label='Salin pesan ini',command=lambda:message_at(target['index']))
    menu.add_command(label='Salin teks terpilih',command=selection)
    menu.add_command(label='Salin seluruh percakapan',command=lambda:copy_conversation(main))
    menu.add_command(label='Simpan laporan percakapan…',command=lambda:save_conversation(main))
    def show(event):
        target['index']=view.index('@'+str(event.x)+','+str(event.y));menu.tk_popup(event.x_root,event.y_root)
    view.bind('<Button-3>',show)

def mark_message(view,start):
    sequence=getattr(view,'_copy_sequence',0)
    if not isinstance(sequence,int):sequence=0
    view._copy_sequence=sequence+1;tag='copy_message_'+str(sequence+1)
    view.tag_add(tag,start,'end-1c')
