"""Tkinter desktop shell. Only the UI thread touches widgets."""
from datetime import datetime
import json
import os
import queue
import sqlite3
import re
import threading
import tkinter as tk
from tkinter import ttk

from chat_service import ChatService
from command_resolution import WIB
from desktop_service import DesktopService
from hybrid_engine import EngineError
from paths import DATA
from preferences import Preferences, MODES
from reply_voice import ReplyVoice
from conversation_stream import voice_active as stream_voice_active

from pipeline_routing import local_voice_route

BG, PANEL, CARD, INK, MUTED, ACCENT = "#0b1120", "#111b2d", "#1b2940", "#e7edf8", "#99abc5", "#7ce4ca"


class LevaWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Leva — Asisten Desktop")
        self.root.geometry("1120x780")
        self.root.minsize(960, 700)
        self.root.configure(bg=BG)
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.preferences = Preferences()
        self.desktop, self.chat = DesktopService(preferences=self.preferences), ChatService()
        self.frontend=ChatService()
        from conversation_rooms import ConversationRooms
        from collections import deque
        self.rooms=ConversationRooms();self.workspace="assistant";self.room_attachments=[];self._assistant_log=deque(maxlen=120)
        self._scheduled_job=None
        self.desktop.schedules.recover()
        from task_journal import TaskJournal
        TaskJournal().recover_dead_owners()
        self.voice_window = None
        self.voice_pack_window = None
        self.duplex_window = None
        self.settings_window = None
        self.reply_voice = ReplyVoice(keep_warm=self.preferences.get('keep_models_warm'))
        from local_mic_service import LocalMicService
        from autonomy_services import HardwareMonitor,ProactiveService
        self.local_mic=LocalMicService();self.hardware=HardwareMonitor();self.hardware.start()
        self.proactive=ProactiveService(self.desktop.tools.conversations,self.desktop.tools.bridge)
        self.local_notice='Pendengar lokal belum dimulai';self.local_partial='';self.local_mic_failed=False
        self.audio_resource_hold=False
        self.advanced_window=None;self.last_chat_ms=None;self.last_briefing='';self.agenda_notified=set()
        from router_gateway import RouterGateway
        self.router_gateway=RouterGateway();self.router_window=None
        if self.preferences.get('auto_memory'):
            try:self.chat.history=self.desktop.tools.conversations.recent(4)
            except sqlite3.Error:pass
        self.events = queue.Queue()
        self.busy, self.closed, self.generation = False, False, 0
        self.link_sequence=0
        self.mode = tk.StringVar(value=self.preferences.get("provider"))
        self.dual = tk.BooleanVar(value=self.preferences.get("dual_gpu"))
        from pipeline_routing import visible_route,route_spec
        self.mode.set(local_voice_route(self.mode.get(),self.dual.get()))
        initial_gpu=route_spec(self.mode.get())['gpu']
        self.last_single_gpu=initial_gpu if initial_gpu in ('rtx4050','rtx5070') else self.preferences.get('route_single_gpu')
        self.mode.set(visible_route(self.mode.get(),self.dual.get(),self.last_single_gpu))
        self.spoken_replies = tk.BooleanVar(value=self.preferences.get('spoken_replies'))
        self.speech_language=tk.StringVar(value='日本語' if self.preferences.get('speech_language')=='ja' else 'Indonesia')
        self.status = tk.StringVar(value="Aktif · perintah lokal siap")
        self.activity = tk.StringVar(value="AI tidak dimuat")
        self._layout()
        self.mode.trace_add("write",lambda *_: self.route_changed())
        self.dual.trace_add("write",lambda *_: self.dual_changed())
        self.spoken_replies.trace_add('write',lambda *_:self.set_spoken_replies())
        self.speech_language.trace_add('write',lambda *_:self.set_speech_language())
        self._profiles()
        from presence_companion import greet,touch
        greet(self,'assistant')
        self.root.bind('<KeyPress>',lambda event:touch(self),add='+')
        self.root.bind('<ButtonPress>',lambda event:touch(self),add='+')
        if self.preferences.warning:
            self.add("Info",self.preferences.warning)
        self.root.after(100, self.poll)
        self.root.after(1000, self.tick)
        self.entry.focus_set()
        self.root.after(1500,self.apply_autonomy_settings)
        if self.preferences.get('web_remote_enabled'):self.root.after(2500,self.restore_remote)
        import sys
        if '--quiet-start' not in sys.argv:self.root.after(15000,self.daily_briefing)
        from image_jobs import ImageJobs
        self.image_jobs=ImageJobs();self.image_events=queue.Queue();self.image_job_busy=False
        self.root.after(5000,self.poll_image_jobs)
        import sys
        if '--background' in sys.argv:self.root.iconify()

    def label(self, parent, text, **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", PANEL), fg=kwargs.pop("fg", INK), **kwargs)

    def route_changed(self):
        from pipeline_routing import route_spec
        local=local_voice_route(self.mode.get(),self.dual.get())
        if local!=self.mode.get():self.mode.set(local);return
        spec=route_spec(self.mode.get(),self.dual.get())
        if self.mode.get()!=spec['label']:
            self.mode.set(spec['label']);return
        if spec['gpu'] in ('rtx4050','rtx5070'):
            self.last_single_gpu=spec['gpu'];self.save_preference('route_single_gpu',self.last_single_gpu)
        self.save_preference('provider',spec['label'])
        if not self.busy:self.cancel_inference();self.stop_reply_voice()
        preview=getattr(self,'voice_pack_window',None)
        if preview:preview.stop()
        lab=getattr(self,'duplex_window',None)
        if lab and lab.service.active:lab.stop()
        if self.local_mic.active:self.local_mic.stop()
        self.local_mic_failed=False
        if hasattr(self,'mic_recovery'):self.mic_recovery.reset()

    def dual_changed(self):
        from pipeline_routing import VOICE_SINGLE as SINGLE_CHOICES,VOICE_DUAL as DUAL_CHOICES,visible_route
        self.save_preference('dual_gpu',self.dual.get())
        self.save_preference('route_single_gpu',self.last_single_gpu)
        self.provider.configure(values=DUAL_CHOICES if self.dual.get() else SINGLE_CHOICES)
        self.mode.set(visible_route(self.mode.get(),self.dual.get(),self.last_single_gpu))

    def cancel_inference(self):
        self.chat.cancel()
        rooms=getattr(self,'rooms',None)
        if rooms:rooms.cancel()
        frontend=getattr(self,'frontend',None)
        if frontend:frontend.cancel()
        pool=getattr(self,'_speech_runtime_pool',None)
        if pool:pool.close()
        preparation=getattr(self,'reaction_prepare_service',None)
        if preparation:preparation.stop();self.reaction_prepare_service=None

    def open_speech_pipeline(self):
        from speech_pipeline_window import SpeechPipelineWindow
        SpeechPipelineWindow(self)

    def button(self, parent, text, command, primary=False, **kwargs):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else CARD,
                         fg=BG if primary else INK, activebackground="#a4f4df" if primary else "#2a3f5e",
                         activeforeground=BG if primary else INK, bd=0, relief="flat", cursor="hand2",
                         padx=14, pady=10, **kwargs)

    def _layout(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=INK,
                        arrowcolor=ACCENT, borderwidth=0, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", INK)],
                  selectbackground=[("readonly", CARD)], selectforeground=[("readonly", INK)])
        from hud_view import WorkspaceHUD
        self.hud = WorkspaceHUD(self)

    def add(self, speaker, text):
        from collections import deque
        if not hasattr(self,'_web_log'):self._web_log=deque(maxlen=120)
        self._web_log.append((speaker,text))
        room=getattr(self,'workspace','assistant')
        from avatar_emotion import observe_reply
        observe_reply(self,speaker,text)
        if room=='assistant' and hasattr(self,'_assistant_log'):self._assistant_log.append((speaker,text))
        if room in ('assistant','chat','secret','companion_avatar') and hasattr(self,'rooms'):self.rooms.append(room,speaker,text)
        host=getattr(self,'_web_host',None)
        if host:host.bridge.log(speaker,text)
        if speaker=='Info' and 'Kode:' in text:self._web_last_error=text[:300]
        tag = "AI" if speaker.startswith("Leva ·") else speaker
        self.history.configure(state="normal")
        message_start=self.history.index('end-1c')
        align='assistant_align' if speaker.startswith(('Leva','Ucapan')) and 'Proses' not in speaker else 'user_align' if speaker.startswith('Anda') else ''
        if speaker.startswith('Leva') and getattr(self.hud,'profile_photo',None):
            start=self.history.index('end-1c');self.history.image_create('end',image=self.hud.profile_photo);self.history.insert('end',' ')
            if align:self.history.tag_add(align,start,'end-1c')
        self.history.insert("end", speaker + "\n", (tag,align) if align else tag)
        body_start=self.history.index('end-1c')
        self.history.insert("end", text + "\n\n", ('body',align) if align else 'body')
        if speaker.startswith('Ucapan'):
            self.history.tag_add('spoken_translation',message_start,'end-1c')
            self.history.tag_configure('spoken_translation',elide=not self.preferences.get('show_japanese'))
        from conversation_export import mark_message
        mark_message(self.history,message_start)
        for match in re.finditer(r'https?://[^\s<>]+',text):
            url=match.group(0).rstrip(').,]');self.link_sequence+=1;name='link_'+str(self.link_sequence)
            self.history.tag_add(name,body_start+'+'+str(match.start())+'c',body_start+'+'+str(match.start()+len(url))+'c')
            self.history.tag_configure(name,foreground='#6bdce6',underline=True)
            self.history.tag_bind(name,'<Button-1>',lambda event,link=url:self.open_link(link))
        if int(self.history.index("end-1c").split(".")[0]) > 1000:
            self.history.delete("1.0","250.0")
        self.history.configure(state="disabled")
        self.history.see("end")
        self.hud.note(speaker, text)

    def _profiles(self):
        self.profile_rows = list(self.desktop.profiles.values())
        self.listbox.delete(0, "end")
        for profile in self.profile_rows:
            suffix = profile["profile_directory"].replace("Profile ", "#")
            self.listbox.insert("end", profile["name"] + "   · " + suffix)
        self.hud.update_inventory()
        if not self.profile_rows:
            self.add("Info", "Belum ada profil Chrome yang ditemukan. Periksa instalasi Chrome lalu segarkan profil.")

    def open_profile(self, youtube):
        selected = self.listbox.curselection()
        if not selected:
            self.send("buka YouTube" if youtube else "buka Chrome")
        else:
            profile = self.profile_rows[selected[0]]
            prefix = "buka YouTube di profil " if youtube else "buka Chrome profil "
            self.send(prefix + profile["id"], display=prefix + profile["name"])

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.entry, self.send_button, self.open_chrome, self.open_youtube, self.refresh_button, self.dual_check]:
            widget.configure(state="disabled" if busy else "normal")
        self.provider.configure(state="disabled" if busy else "readonly")
        if hasattr(self,'language_picker'):self.language_picker.configure(state='disabled' if busy else 'readonly')
        if not busy:
            self.entry.focus_set()

    def send(self, supplied=None, display=None, commands_only=False, scheduled_id=None, voice_id=None,client_context=None,workspace=None,attachments=None):
        if self.busy:
            return
        host=getattr(self,'_web_host',None)
        if host and host.bridge.speech.pending():
            self.add('Info','Tunggu transkrip HP selesai atau batalkan rekaman sebelum memulai tugas baru.');return
        self._web_last_error='';self._web_tool=''
        text = supplied or self.entry.get().strip()
        if not text and getattr(self,'room_attachments',[]):text='Tolong periksa dan ringkas lampiran ini; jelaskan bagian yang belum dapat dianalisis.'
        if not text:
            return
        from presence_companion import touch
        touch(self,text)
        requested=workspace or ('assistant' if scheduled_id else getattr(self,'workspace','assistant'))
        if requested!=getattr(self,'workspace','assistant'):
            from room_ui import switch_workspace
            switch_workspace(self,requested)
        if requested in ('chat','secret') and getattr(self.rooms,'pending',None) and self.rooms.pending.get('source','secret')==requested:
            if re.fullmatch(r'(?:ya|iya|setuju|boleh|oke|ok)(?:[, ]+(?:pindah|lanjut|salin|silakan))*[.! ]*',text.strip(),re.I):
                from room_ui import accept_handoff
                self.add('Anda',text);return accept_handoff(self,self.rooms.pending['target'])
            if re.fullmatch(r'(?:tidak|jangan|batal|tetap di secret)[.! ]*',text.strip(),re.I):self.rooms.clear_pending()
        from conversation_rooms import NO_AGENT
        if requested in ('chat','secret','companion_avatar') or requested=='assistant' and self.preferences.get('agent_local_model') in NO_AGENT:
            from room_ui import send_room
            try:return send_room(self,text,display,voice_id,attachments)
            except ValueError as error:self.add('Info',str(error));return False
        self.desktop.tools.client_context=client_context or {'kind':'desktop','name':'Laptop','executor':'laptop Windows'}
        from conversation_attachments import materialize
        try:attachment_rows=materialize(list(attachments if attachments is not None else getattr(self,'room_attachments',[])))
        except (ValueError,OSError) as error:self.add('Info',str(error));return False
        self.desktop.tools.user_attachments=attachment_rows
        if attachment_rows:
            self.add('Info · Lampiran','Bahan terlampir: '+', '.join(r['name'] for r in attachment_rows)+'. Teks masukan tetap terpisah dari isi berkas.')
            self.room_attachments=[]
            if hasattr(self,'attachment_label'):self.attachment_label.set('')
        if len(text) > 3000:
            self.add("Info", "Pesannya terlalu panjang untuk versi awal ini. Batasi hingga 3.000 karakter.")
            return
        raw_text=text
        from input_normalization import normalize_input
        normalized=normalize_input(text);text=normalized['text']
        from agent_contract import correction_goal,website_creation
        previous=getattr(self,'_last_user_goal','')
        if not previous:
            history=getattr(self.chat,'history',[])
            previous=next((m['content'] for m in reversed(history if isinstance(history,list) else []) if m['role']=='user' and website_creation(m['content'])),'')
        corrected=correction_goal(text,previous)
        if len(corrected)<=3000:text=corrected
        if website_creation(text):self._last_user_goal=text
        import time
        request_started=time.perf_counter();self._request_started=request_started
        self._reaction_shown=False
        if not voice_id:self.add('Anda',display or raw_text)
        if normalized['edits']:self.add('Info · Input','Koreksi ejaan: '+', '.join(e['from']+' → '+e['to'] for e in normalized['edits'])+'. Angka, nama dan negasi dipertahankan.')
        if text!=raw_text:self.add('Info','Koreksi ditautkan ke permintaan sebelumnya; arahan koreksi diutamakan.')
        from task_reactions import needs_reaction
        task_request=needs_reaction(text)
        if not commands_only and task_request:
            self.show_task_reaction(self.preferences.get('speech_language'),play=False,text=text)
            self.root.update_idletasks()
        if re.match(r'^(?:leva[, ]*)?(?:jeda|jedakan|pause|bekukan|matikan sistem)',text,re.I):
            self.local_mic.stop()
        from pipeline_routing import route_spec
        route_now=route_spec(self.mode.get(),self.dual.get())
        if getattr(self,'_translation_pending',False):
            self.frontend.cancel();self._translation_pending=False
        # Online conversation need not evict its TTS cache every turn.
        self.reply_voice.cancel(keep_warm=not task_request and self.preferences.get('keep_models_warm') and (route_now['mode'] in ('hybrid','cascade','router') or route_now['gpu']=='dual'))
        if supplied is None:self.entry.delete(0, "end")
        if scheduled_id:self._scheduled_job=scheduled_id
        self.set_busy(True)
        self.generation += 1
        generation = self.generation
        self._voice_reply_generation=generation if voice_id else None
        if voice_id:self.active_voice=(voice_id,generation)
        mode, dual = self.mode.get(), self.dual.get()
        saluki_acceleration=self.preferences.get('saluki_acceleration')
        language=self.preferences.get('speech_language')
        want_voice=self.spoken_replies.get()
        from pipeline_routing import route_spec
        route=route_spec(mode,dual)
        using_router=route['mode']=='router'
        using_chain=route['mode']=='cascade'
        has_router=using_router or using_chain
        router_local=self.preferences.get('agent_local_model')
        router_config={'url':self.preferences.get('router_url'),'model':self.preferences.get('router_model')} if has_router else None
        keep_warm=self.preferences.get('keep_models_warm')
        from task_progress import tracker,begin_request
        progress=begin_request(self,"Asisten")
        progress.add("understand","Memahami tujuan dan memilih jalur pelaksanaan")
        self.activity.set("Memahami permintaan…")
        self.hud.task_state(display or text, "BERJALAN")
        self._progress_count=0
        self._last_progress_at=0
        if not commands_only and task_request:self.play_task_reaction(language)
        from speech_resources import agent_mode
        agent_route=route_spec(self.preferences.get('agent_provider'))
        executor_mode=agent_mode(agent_route,self.preferences.get('agent_gpu'))
        agent_router_config={'url':self.preferences.get('router_url'),'model':self.preferences.get('router_model')} if agent_route['mode'] in ('router','cascade') else None
        def start_agent_gateway():
            if agent_router_config and agent_router_config['model']:
                try:self.router_gateway.start(agent_router_config['url'])
                except (ValueError,OSError):pass
        def run():
            published=False
            try:
                result = self.desktop.handle(text)
                if result.get("cancel_ai"):
                    self.cancel_inference()
                if result["kind"] == "chat":
                    if commands_only:
                        result = {"reply": "Transkrip ini belum dikenali sebagai perintah desktop. Percakapan suara tetap ditangani Google Live."}
                    elif self.duplex_window and self.duplex_window.service.active:
                        result = {"reply":"Lab lokal sedang memakai model. Hentikan model di Duplex Lab sebelum memulai chat AI."}
                    elif route['mode']=='commands':
                        if agent_route['mode']=='commands':result={'reply':'Suara dan agent/LLM dinonaktifkan. Pilih rute pada Suara & agent untuk memakai AI.'}
                        else:
                            start_agent_gateway()
                            result=self.chat.ask(text,agent_route['mode'],executor_mode,local_model=router_local,acceleration=saluki_acceleration,keep_warm=keep_warm,
                                tool_executor=lambda name,args,valid:self.execute_tool(name,args,text,valid,generation),
                                tool_context=self.desktop.tools.context(text),speech_language=language,router_config=agent_router_config)
                    else:
                        if self.preferences.get('separate_agent') and not attachment_rows:
                            from conversation_frontend import conversation_request
                            if has_router and router_config['model']:
                                try:self.router_gateway.start(router_config['url'])
                                except (ValueError,OSError):pass
                            front=conversation_request(self.frontend,text,route,router_config,language,dual,keep_warm=keep_warm,client_context=self.desktop.tools.client_context)
                            if front['kind']=='cancelled':return
                            if generation!=self.generation:return
                            if front['kind']=='delegate' and agent_route['mode']=='commands':
                                front={'kind':'respond','text':'Agent/LLM sedang nonaktif. Pilih rute agent pada Suara & agent untuk menjalankan tugas ini.'}
                            if front['kind']=='delegate':
                                self.frontend.cancel()
                                if not self._reaction_shown:
                                    self.events.put((generation,{'_task_reaction':True,'language':language}))
                                # A 27B agent and GPU ASR may exceed the same card's capacity.
                                # Preserve the utterance/goal, release only our own ASR worker.
                                held_asr=router_local=='saluki' and self.preferences.get('asr_model')!='whisper_cpu' and self.local_mic.active and (executor_mode=='dual' or ('4050' in self.local_mic.gpu_name)==(executor_mode=='gpu4050'))
                                if held_asr:
                                    self.audio_resource_hold=True;self.local_mic.hold_asr()
                                    self.local_notice='Mikrofon tetap menangkap · pengenalan mengantre selama agent memakai GPU'
                                self.events.put((generation,{'_progress_event':progress.add('inference','Model agent sedang memproses permintaan')}))
                                self.events.put((generation,{'_tool_progress':'Agent · '+router_local}))
                                start_agent_gateway()
                                result=self.chat.ask(text,agent_route['mode'],executor_mode,
                                    local_model=router_local,acceleration=saluki_acceleration,keep_warm=keep_warm,
                                    tool_executor=lambda name,args,valid:self.execute_tool(name,args,text,valid,generation),
                                    tool_context={**self.desktop.tools.context(text),'intent_brief':front.get('summary','')[:800]},speech_language=language,router_config=agent_router_config)
                                if held_asr:self.chat.cancel()
                                result['frontend_provider']=front.get('frontend_provider')
                                result['engine_role']='Agent / LLM'
                                result['provider_failures']=front.get('provider_failures',[])+result.get('provider_failures',[])
                            else:
                                result={'response':front.get('text',''),'speech_text':front.get('speech_text',''),
                                    'engine_role':'Percakapan',
                                    'provider':front.get('frontend_provider'),'needs_input':front['kind']=='clarify',
                                    'provider_failures':front.get('provider_failures',[]),'google_paused':front.get('google_paused',False)}
                        elif has_router:
                            if router_config['model']:
                                try:self.router_gateway.start(router_config['url'])
                                except (ValueError,OSError):pass
                            if generation!=self.generation:return
                            result=self.chat.ask(text,route['mode'],executor_mode,local_model=router_local,acceleration=saluki_acceleration,keep_warm=keep_warm,
                                tool_executor=lambda name,args,valid:self.execute_tool(name,args,text,valid,generation),
                                tool_context=self.desktop.tools.context(text),speech_language=language,router_config=router_config)
                        elif route['mode']=='local' and router_local=='saluki':
                            result=self.chat.ask(text,'local',executor_mode,local_model=router_local,acceleration=saluki_acceleration,keep_warm=keep_warm,
                                tool_executor=lambda name,args,valid:self.execute_tool(name,args,text,valid,generation),
                                tool_context=self.desktop.tools.context(text),speech_language=language)
                        else:
                            result = self.chat.ask(text,route['mode'],executor_mode,local_model=router_local,keep_warm=keep_warm,
                                tool_executor=lambda name,args,valid:self.execute_tool(name,args,text,valid,generation),
                                tool_context=self.desktop.tools.context(text),speech_language=language)
                if generation!=self.generation:return
                reply=result.get('reply',result.get('response',''))
                if reply:
                    from chat_service import bounded_history
                    self.frontend.history=bounded_history([*self.frontend.history,{'role':'user','content':text},{'role':'assistant','content':reply}])
                if result.get('kind')=='command' and reply and not result.get('cancel_ai'):
                    from chat_service import bounded_history
                    self.chat.history=bounded_history([*self.chat.history,{'role':'user','content':text},{'role':'assistant','content':reply}])
                from assistant_tools import effective_speech_language
                effective_language=effective_speech_language(result,self.preferences.get('speech_language'))
                # Publish the factual answer before a possibly slow Japanese translation.
                result['_speech_language']=effective_language
                from speech_style import SpeechStylePolicy
                if not hasattr(self,'speech_style_policy'):self.speech_style_policy=SpeechStylePolicy()
                result['_speech_style']=self.speech_style_policy.choose(text,result.get('voice_style',''),result.get('tool_receipts',[]),self.preferences.get('speech_style'))
                result['_speak_reply']=not commands_only and not result.get('image_job_active')
                if result.get('image_job_active'):self._image_gpu_active=True
                if reply and self.preferences.get('auto_memory') and not result.get('cancelled'):
                    try:self.desktop.tools.conversations.record(text,reply,result.get('tool_receipts',[]))
                    except (OSError,sqlite3.Error):result['detail']='Percakapan belum berhasil disimpan ke memori otomatis.'
                result['text_ready_ms']=round((time.perf_counter()-request_started)*1000,2)
                delayed_voice=effective_language=='ja' and want_voice and reply and not result.get('cancel_ai') and not result.get('image_job_active') and not commands_only and not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',result.get('speech_text',''))
                if delayed_voice:
                    self.events.put((generation,{**result,'_speak_reply':False,'_translation_pending':True}))
                    published=True
                if effective_language=='ja' and want_voice and reply and not result.get('cancel_ai') and not result.get('image_job_active') and not commands_only:
                    spoken=result.get('speech_text','')
                    if not re.search(r'[\u3040-\u30ff\u3400-\u9fff]',spoken) and route['mode']!='commands':
                        try:
                            # The answer is published; free this task's warm agent before
                            # loading the small translator. Keep the existing ASR hold.
                            self.chat.cancel()
                            from speech_translation import translate_speech
                            translated=translate_speech(self.frontend,reply,route['local_mode'],
                                authorized=lambda:generation==self.generation and getattr(self,'_muted_voice_generation',None)!=generation and not self.closed,
                                mode=route['mode'],router_config=router_config,
                                progress=lambda p:self.events.put((generation,{'_translation_progress':p})))
                            spoken=translated['text']
                        except EngineError as error:
                            spoken='';result['_voice_notice']='Terjemahan suara Jepang belum berhasil; jawaban teks tetap tersedia. Kode: '+str(error)
                    result['speech_text']=spoken
                if generation!=self.generation:return
                self.events.put((generation, {'_voice_only':True,'speech_text':result.get('speech_text',''),
                    '_speech_style':result['_speech_style'],'_voice_notice':result.get('_voice_notice','')} if delayed_voice else result))
            except EngineError as error:
                self.events.put((generation, {'_voice_only':True,'_voice_notice':'Terjemahan suara belum berhasil; jawaban teks tetap tersedia.'} if published else {"error": str(error)}))
            except Exception:
                self.events.put((generation, {'_voice_only':True,'_voice_notice':'Keluaran suara belum berhasil; jawaban teks tetap tersedia.'} if published else {"error": "desktop_or_runtime_failure"}))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        host=getattr(self,'_web_host',None)
        if host:host.poll()
        while not self.events.empty():
            generation, result = self.events.get_nowait()
            if result.get('_stream_text') and generation==self.generation:
                from conversation_stream import display
                display(self,result);continue
            if result.get('_remote_error'):
                self.add('Info','Akses HP belum siap. Buka Pengaturan → Hubungkan Android. Kode: '+result['_remote_error']);continue
            if result.get('_web_ready') or result.get('_web_failure'):
                if host:host.ready(result)
                continue
            if result.get('_companion'):
                if generation==self.generation:
                    from presence_companion import deliver
                    deliver(self,result['_companion'])
                continue
            if result.get('_proactive'):
                if not self.desktop.paused and not self.desktop.sleeping:self.add('Leva · Pantauan',result['_proactive'])
                continue
            if generation != self.generation:
                continue
            if result.get('_task_reaction'):
                self.show_task_reaction(result['language']);continue
            if result.get('_voice_only'):
                self._translation_pending=False
                self.translation_progress={}
                if getattr(self,'_muted_voice_generation',None)==generation:continue
                if result.get('speech_text'):
                    self.add('Ucapan · 日本語',result['speech_text'])
                    self.speak_reply(result['speech_text'],'ja',result.get('_speech_style',{}).get('style','assistant'))
                elif result.get('_voice_notice'):self.add('Info',result['_voice_notice'])
                continue
            if result.get('_translation_progress'):
                if getattr(self,'_muted_voice_generation',None)!=generation:
                    self.translation_progress=result['_translation_progress']
                    self.activity.set('Menyiapkan ucapan Jepang · '+str(self.translation_progress['completed'])+' / '+str(self.translation_progress['total']))
                continue
            if result.get('_reaction_prepared'):
                self.set_busy(False);self.add('Info',result['_reaction_prepared']);continue
            if result.get('_progress_event'):
                event=result['_progress_event']
                self.activity.set(event['label'])
                self.hud.task_state(event['label'],'BERJALAN')
                continue
            if result.get('_tool_progress'):
                tool=result['_tool_progress']
                self._web_tool=tool
                if host:host.progress(tool)
                self.hud.task_state('Menjalankan '+tool,'BERJALAN')
                self._progress_count=getattr(self,'_progress_count',0)+1
                progress={'browser_action':'Aku sedang memeriksa dan mengerjakan halaman web.','file_action':'Aku sedang memeriksa berkas dan hasil perubahan.','list_windows':'Aku memeriksa jendela yang tersedia.','web_search':'Aku mencari sumber yang sesuai dengan tujuanmu.',
                    'comfy_action':'Aku sedang memeriksa alur, model, dan hasil ComfyUI.','image_action':'Aku sedang memeriksa proses gambar dan hasilnya.','terminal_action':'Aku sedang menjalankan proses dan membaca hasilnya.','project_action':'Aku sedang memeriksa perubahan proyek.'}
                import time
                now=time.monotonic()
                if tool in progress and now-getattr(self,'_last_progress_at',0)>=8:
                    self.add('Leva · Proses',progress[tool]);self._last_progress_at=now
                continue
            if getattr(self,'_scheduled_job',None):
                from scheduled_tasks import completion_status
                self.desktop.schedules.finish(self._scheduled_job,completion_status(result),result.get('reply',result.get('response',result.get('error',''))))
                self._scheduled_job=None
            if getattr(self,'active_voice',None) and self.active_voice[1]==generation:
                from speech_turns import STATUS_LABELS
                state='failed' if result.get('error') else 'interrupted' if result.get('cancelled') else 'needs_input' if result.get('incomplete') or result.get('needs_input') else 'completed'
                self.speech_inbox().update(self.active_voice[0],state,str(result.get('error') or result.get('reply') or result.get('response') or ''))
                self.local_notice=STATUS_LABELS[state];self.active_voice=None
            from conversation_stream import clear_display
            clear_display(self)
            trace=getattr(self,'process_trace',None)
            if trace:
                terminal='failed' if result.get('error') else 'cancelled' if result.get('cancelled') else 'waiting' if result.get('needs_input') or result.get('incomplete') else 'completed'
                trace.emit('run.'+terminal,'room_host',status=terminal)
            if host:host.complete(result)
            from task_progress import tracker
            state='failed' if result.get('error') else 'cancelled' if result.get('cancelled') else 'needs_input' if result.get('needs_input') or result.get('incomplete') else 'done'
            tracker(self).add('response','Jawaban teks tersedia' if state=='done' else 'Giliran berakhir · '+state,state)
            self.set_busy(False)
            self._translation_pending=bool(result.get('_translation_pending'))
            if result.get('_speech_language') in ('id','ja'):
                label='日本語' if result['_speech_language']=='ja' else 'Indonesia'
                if self.speech_language.get()!=label:self.speech_language.set(label)
            self.hud.task_state(result.get("error") or result.get("reply") or result.get("response") or "Permintaan dihentikan.",
                                "GALAT" if result.get("error") else "DIHENTIKAN" if result.get("cancelled") else "DITANGGAPI")
            if result.get("cancel_ai") and self.voice_window:
                self.voice_window.stop(sleeping=self.desktop.paused or self.desktop.sleeping)
            if result.get("cancel_ai") and getattr(self,"duplex_window",None):
                self.duplex_window.stop()
            if result.get("cancel_ai") and getattr(self,"voice_pack_window",None):
                self.voice_pack_window.stop()
            if result.get('cancel_ai'):self.stop_reply_voice()
            if result.get('cancel_ai'):
                if getattr(self,'router_gateway',None):self.router_gateway.stop()
                self.local_mic.stop()
                self.hardware.stop()
                if self.desktop.tools._bridge:self.desktop.tools._bridge.stop()
            if result.get('resumed'):self.local_mic_failed=False
            if result.get("cancelled"):
                self.add("Info", "Permintaan AI dihentikan.")
            elif result.get("error"):
                error = result["error"]
                if error=='saluki_benchmark_pending':
                    text='Akselerasi otomatis agent Saluki belum siap. Pilih agent Qwen 4B pada Suara & agent, atau pilih akselerasi Saluki manual di Pengaturan.'
                elif error.startswith("online_"):
                    text = "Layanan Google belum merespons dengan benar. Periksa koneksi/key atau pilih mode Lokal."
                else:
                    text = "Permintaan belum berhasil. Periksa ketersediaan runtime/model dan coba lagi."
                self.add("Info", text + " Kode: " + error)
            else:
                provider = result.get("provider")
                speaker = "Leva · " + ({'google':'Google','9router':'9Router'}.get(provider,'Lokal')) if provider else "Leva"
                if result.get('engine_role'):speaker+=' · '+result['engine_role']
                reply=result.get('reply',result.get('response',''))
                self.add(speaker,reply)
                image_ids=set()
                for receipt in result.get('tool_receipts',[]):
                    outcome=receipt.get('result',{});ident=outcome.get('job_id') or outcome.get('workflow_id')
                    if receipt.get('name') in ('image_action','comfy_action') and outcome.get('status')=='done' and outcome.get('outputs') and ident not in image_ids:
                        image_ids.add(ident);self.add_image_files(receipt.get('args',{}).get('engine','comfyui'),outcome)
                if result.get('task_id') and result.get('incomplete'):
                    self.add('Info','Tugas '+result['task_id']+' tersimpan. Untuk melanjutkan, tulis: lanjut tugas '+result['task_id']+'. Keadaan aplikasi akan diperiksa ulang.')
                if result.get('provider_failures'):
                    failures=' → '.join(('Google' if r['provider']=='google' else '9Router')+' ('+r['reason']+')' for r in result['provider_failures'])
                    self.add('Info','Peralihan provider: '+failures+'. Jawaban dilanjutkan melalui '+({'google':'Google','9router':'9Router'}.get(provider,'model lokal'))+'.')
                elif str(result.get('fallback_reason','')).startswith('router_'):
                    self.add('Info','9Router belum tersedia untuk permintaan ini; dilanjutkan dengan model lokal. Kode: '+result['fallback_reason'])
                if result.get('_speak_reply') and not result.get('cancel_ai') and getattr(self,'_muted_voice_generation',None)!=generation:
                    spoken=result.get('speech_text') if result.get('_speech_language')=='ja' else result.get('speech_text') or reply
                    if spoken:
                        if result.get('_speech_language')=='ja':self.add('Ucapan · 日本語',spoken)
                        self.speak_reply(spoken,result.get('_speech_language','id'),result.get('_speech_style',{}).get('style','assistant'))
                    elif result.get('_speech_language')=='ja':self.add('Info',result.get('_voice_notice','Teks tersedia; pilih model AI untuk menyiapkan terjemahan suara Jepang.'))
                for receipt in result.get('tool_receipts',[]):
                    status=receipt['result'].get('status','unverified')
                    self.hud.tool_result(receipt['name'],status,receipt['result'].get('reply',''))
                    if receipt['name']=='set_theme' and status=='done':self.apply_theme()
                self.last_chat_ms=result.get('request_ms')
                self.last_text_ms=result.get('text_ready_ms')
                if result.get("detail"):
                    self.add("Info", result["detail"])
                if self.desktop.memory_notice:
                    self.add("Info",self.desktop.memory_notice)
                    self.desktop.memory_notice=""
                if result.get("kind")=="command" and self.voice_window:
                    self.voice_window.desktop_result(result.get("reply",""))
            lab=getattr(self,"duplex_window",None)
            chat=getattr(self,'chat',None)
            chat_loaded=bool(chat and chat.process and chat.process.poll() is None)
            self.activity.set('Duplex Lab aktif · model dimuat' if lab and lab.service.active else 'Siaga cepat · model dapat tetap dimuat 2 menit' if chat_loaded else 'Model chat tidak dimuat')
        reply_voice=getattr(self,'reply_voice',None)
        if reply_voice:
            for notice in reply_voice.poll():self.add('Info',notice)
            if reply_voice.active:self.activity.set('Jawaban suara lokal · mikrofon lokal tetap mendengar' if self.local_mic.active else 'Jawaban suara lokal · sintesis / pemutaran · mikrofon mati')
            elif self.activity.get().startswith('Jawaban suara lokal'):self.activity.set('Suara selesai · siaga cepat 2 menit' if reply_voice.service.loaded else 'Keluaran suara selesai · model suara dilepas')
            elif self.activity.get().startswith(('Siaga cepat','Suara selesai')) and not reply_voice.service.loaded and not (self.chat.process and self.chat.process.poll() is None):self.activity.set('Batas siaga tercapai · model dilepas')
        self.poll_local_mic()
        live=getattr(self,'live_speech',None)
        if live:
            for notice in live.poll():self.add('Info',notice)
        self.dispatch_voice()
        self.hud.sync()
        self.root.after(100, self.poll)

    def tick(self):
        if self.closed:
            return
        voice_reply=getattr(self,'_voice_reply_generation',None)==self.generation
        voice_work=self.reply_voice.active or stream_voice_active(self) or bool(getattr(self,'active_voice',None)) or voice_reply and (getattr(self,'_translation_pending',False) or getattr(self,'_tts_waiting',False))
        if voice_work and self.local_mic.active and not self.desktop.paused and not self.desktop.sleeping:
            self.local_mic.worker.send({'kind':'keepalive'})
        previous_sleeping = self.desktop.sleeping
        changed = self.desktop.tick()
        if self.desktop.sleeping and not previous_sleeping:
            self.desktop.stop_owned_processes()
            self.cancel_inference()
            self.stop_reply_voice()
            self.local_mic.stop()
        if self.desktop.sleeping and self.voice_window and self.voice_window.service.active:
            self.voice_window.stop(sleeping=True)
        if self.desktop.sleeping and self.duplex_window and self.duplex_window.service.active:
            self.duplex_window.stop()
        pack_window = getattr(self, "voice_pack_window", None)
        if self.desktop.sleeping and pack_window and pack_window.service.active:
            pack_window.stop()
        machine = self.desktop.controller.sleep
        if self.desktop.paused:
            self.status.set("Dijeda · tekan Aktifkan untuk melanjutkan")
        elif machine.mode == "paused":
            self.status.set("Istirahat sampai " + machine.next_transition.strftime("%H.%M WIB"))
        elif machine.mode == "observing":
            self.status.set("Aktif · observasi aktivitas sampai " + machine.next_transition.strftime("%H.%M WIB"))
        else:
            self.status.set("Aktif · " + str(len(self.profile_rows)) + " profil Chrome tersedia")
        self.pause_button.configure(text="Aktifkan" if self.desktop.paused or machine.mode != "off" else "Jeda")
        if changed and machine.mode == "off":
            self.add("Info", "Ada aktivitas saat observasi. Mekanisme tidur dibatalkan; aku aktif kembali.")
        if self.duplex_window and self.duplex_window.service.active:
            self.activity.set("Duplex Lab aktif · model tetap dimuat selama sesi lab")
        elif not self.busy and self.activity.get().startswith("Duplex Lab"):
            self.activity.set("Model lab dilepas · AI lokal tidak dimuat")
        self.ensure_local_mic()
        if self.desktop.paused or self.desktop.sleeping:self.hardware.stop()
        else:self.hardware.start()
        if self.desktop.tools._bridge:self.desktop.tools._bridge.expire_idle()
        self.proactive.tick(lambda text:self.events.put((0,{'_proactive':text})),self.proactive_allowed)
        from presence_companion import tick as companion_tick
        companion_tick(self)
        self.poll_schedules()
        if not self.desktop.paused and not self.desktop.sleeping:
            for agenda in self.desktop.tools.conversations.agenda():
                if agenda['id'] not in self.agenda_notified and 0<=(datetime.now(WIB)-datetime.fromisoformat(agenda['when'])).total_seconds()<60:
                    self.agenda_notified.add(agenda['id']);self.add('Leva · Agenda',agenda['title']+' · '+agenda['when'])
        self.root.after(1000, self.tick)

    def notify_schedule(self,job):
        when=datetime.fromtimestamp(job['due'],WIB).strftime('%d-%m-%Y %H.%M WIB')
        self.add('Leva · Pengingat',job['title']+' · '+when+' · ID '+job['id'])
        popup=tk.Toplevel(self.root);popup.title('Leva — Pengingat');popup.geometry('520x240');popup.configure(bg=PANEL)
        self.label(popup,'Waktunya '+job['title'],font=('Segoe UI',15,'bold'),wraplength=470,justify='left').pack(fill='x',padx=22,pady=18)
        self.label(popup,when+('\nTindakan lanjutan menunggu Leva siap; draf Anda tetap disimpan.' if job['goal'] else ''),wraplength=470,justify='left').pack(fill='x',padx=22,pady=8)
        self.button(popup,'Tutup pemberitahuan',popup.destroy).pack(anchor='e',padx=22,pady=12)
        try:
            import winsound
            winsound.PlaySound('SystemExclamation',winsound.SND_ALIAS|winsound.SND_ASYNC)
        except (RuntimeError,OSError):pass

    def poll_schedules(self,now=None):
        if self.desktop.paused or self.desktop.sleeping:return
        now=now or datetime.now(WIB)
        try:
            for job in self.desktop.schedules.notifications(now):self.notify_schedule(job)
            if self.busy or self.entry.get().strip() or self.reply_voice.active or stream_voice_active(self):return
            host=getattr(self,'_web_host',None)
            if host and host.bridge.speech.pending():return
            job=self.desktop.schedules.claim(now)
            if not job:return
            if job['status']=='needs_input':
                self.add('Leva · Pengingat','Tindakan untuk '+job['title']+' tertunda lebih dari 15 menit. Aku belum membukanya. Beri perintah baru untuk menjalankan atau menjadwalkan ulang. ID '+job['id'])
            elif not job['goal']:
                self.desktop.schedules.finish(job['id'],'completed','Pengingat ditampilkan.')
            else:
                self.send(job['goal'],display='Tugas terjadwal '+job['id']+': '+job['goal'],scheduled_id=job['id'])
        except (OSError,sqlite3.Error):
            self.status.set('Penyimpanan pengingat belum tersedia; periksa drive D.')

    def interrupt_schedule(self):
        if getattr(self,'_scheduled_job',None):
            self.desktop.schedules.finish(self._scheduled_job,'interrupted','Dihentikan pengguna; periksa tindakan yang mungkin sudah terkirim sebelum melanjutkan.')
            self._scheduled_job=None

    def release(self):
        from presence_companion import policy
        policy(self).suspend()
        if getattr(self,'_web_host',None):self._web_host.complete({'cancelled':True,'reply':'Dihentikan dari desktop; periksa hasil tindakan yang sudah berjalan.'})
        self.cancel_voice_queue()
        self.interrupt_schedule()
        self.desktop.stop_owned_processes()
        if getattr(self,'router_gateway',None):self.router_gateway.stop()
        self.cancel_inference()
        self.generation+=1;self.set_busy(False)
        self.local_mic.stop();self.local_mic_failed=True
        if self.desktop.tools._bridge:self.desktop.tools._bridge.stop()
        self.stop_reply_voice()
        if getattr(self, "voice_pack_window", None):
            self.voice_pack_window.stop()
        if self.duplex_window:
            self.duplex_window.stop()
        if self.voice_window:
            self.voice_window.stop()
        self.activity.set("Proses AI dihentikan · resource dilepas")
        self.add("Info", "Permintaan AI dihentikan dan worker lokal milik Leva dilepas.")

    def toggle_pause(self):
        from presence_companion import policy,touch
        policy(self).suspend()
        if getattr(self,'_web_host',None):self._web_host.complete({'cancelled':True,'reply':'Dihentikan saat mengubah mode jeda.'})
        self.cancel_voice_queue()
        self.interrupt_schedule()
        self.desktop.stop_owned_processes()
        if getattr(self,'router_gateway',None):self.router_gateway.stop()
        self.cancel_inference()
        self.generation+=1;self.set_busy(False)
        self.local_mic.stop()
        self.hardware.stop()
        if self.desktop.tools._bridge:self.desktop.tools._bridge.stop()
        self.stop_reply_voice()
        if getattr(self, "voice_pack_window", None):
            self.voice_pack_window.stop()
        if self.duplex_window:
            self.duplex_window.stop()
        if self.voice_window:
            self.voice_window.stop(sleeping=True)
        if self.desktop.paused or self.desktop.controller.sleep.mode != "off":
            self.desktop.resume()
            touch(self,force=True)
            self.local_mic_failed=False
            if self.voice_window:
                self.voice_window.set_state("idle")
            self.add("Leva", "Aku aktif kembali. Jadwal jeda sebelumnya sudah dibatalkan.")
        else:
            self.desktop.pause()
            self.add("Leva", "Aku dijeda dan proses AI dilepas. Chrome tetap terbuka. Tekan Aktifkan untuk melanjutkan.")
        self.activity.set("AI tidak dimuat")

    def retry_online(self):
        self.chat.online_paused = False
        self.add("Info", "Permintaan Hybrid berikutnya akan mencoba Google kembali.")

    def refresh(self):
        if self.busy:
            return
        self.desktop.refresh_profiles()
        self._profiles()
        self.add("Info", "Daftar profil diperbarui. Pengingat tersimpan tetap dipertahankan.")

    def close(self):
        if getattr(self,'_web_host',None):self._web_host.stop()
        self.interrupt_schedule()
        self.desktop.stop_owned_processes()
        if getattr(self,'router_gateway',None):self.router_gateway.stop()
        self.closed = True
        self.cancel_inference()
        self.local_mic.stop();self.hardware.stop()
        if self.desktop.tools._bridge:self.desktop.tools._bridge.stop()
        self.stop_reply_voice()
        if getattr(self, "voice_pack_window", None):
            self.voice_pack_window.close()
        if self.voice_window:
            self.voice_window.close()
        if self.duplex_window:
            self.duplex_window.close()
        if hasattr(self,'rooms'):self.rooms.close()
        if getattr(self,'_trace_store',None):self._trace_store.close()
        self.root.destroy()

    def open_voice(self):
        self.stop_reply_voice()
        if self.voice_window and not self.voice_window.closed:
            self.voice_window.window.lift()
            return
        from voice_window import VoiceWindow
        self.voice_window = VoiceWindow(self)

    def open_web(self):
        if getattr(self,'_web_host',None) is None:
            from web_host import DesktopWebHost
            self._web_host=DesktopWebHost(self)
        self._web_host.open()

    def open_companion(self):
        from companion_avatar import configure
        from room_ui import switch_workspace
        configure(self,{'enabled':True});switch_workspace(self,'companion_avatar');self.open_web()

    def open_remote(self):
        from remote_window import RemoteWindow
        RemoteWindow(self)

    def restore_remote(self):
        if self.closed:return
        if not getattr(self,'_web_host',None):
            from web_host import DesktopWebHost
            self._web_host=DesktopWebHost(self)
        self._web_host.open(show=False)
        def run():
            try:
                from remote_gateway import RemoteGateway
                host=self._web_host
                host.bridge.start();result=RemoteGateway().enable(host.bridge.server.server_port)
                host.bridge.remote=result['origin']
            except Exception as error:self.events.put((self.generation,{'_remote_error':str(error)}))
        threading.Thread(target=run,daemon=True).start()

    def open_voice_packs(self):
        self.stop_reply_voice()
        if self.voice_pack_window:
            self.voice_pack_window.window.lift()
            return
        from voice_pack_window import VoicePackWindow
        self.voice_pack_window = VoicePackWindow(self)

    def open_duplex(self):
        self.stop_reply_voice()
        if self.duplex_window:
            self.duplex_window.window.lift()
            return
        from duplex_window import DuplexWindow
        self.duplex_window=DuplexWindow(self)

    def save_preference(self,key,value):
        try:
            self.preferences.set(key,value)
        except (OSError,ValueError,sqlite3.Error):
            self.add("Info","Pengaturan belum tersimpan. Periksa folder data pada D.")

    def open_settings(self):
        if self.settings_window:
            self.settings_window.window.lift()
            return
        from settings_window import SettingsWindow
        self.settings_window=SettingsWindow(self)

    def new_conversation(self):
        if self.busy:
            return False
        self.cancel_voice_queue()
        self.local_mic.telemetry.clear_text()
        self.stop_reply_voice()
        self.cancel_inference()
        if getattr(self, "voice_pack_window", None):
            self.voice_pack_window.stop()
        if self.duplex_window:
            self.duplex_window.stop()
        if self.voice_window:
            self.voice_window.stop()
            self.voice_window.heard.configure(text="Anda: —")
            self.voice_window.said.configure(text="Leva: —")
            self.voice_window.app_result.configure(text="")
        room=getattr(self,'workspace','assistant')
        if room in ('chat','secret','companion_avatar'):
            self.rooms.clear(room)
        else:
            self.rooms.clear('assistant')
            self.chat.history=[]
            self.frontend.history=[]
            if hasattr(self,'_assistant_log'):self._assistant_log.clear()
        if hasattr(self,'_web_log'):self._web_log.clear()
        host=getattr(self,'_web_host',None)
        if host:
            with host.bridge.lock:host.bridge.logs.clear();host.bridge.revision+=1
        self._last_user_goal=''
        if room=='assistant':
            self.desktop.controller.pending=None
            self.desktop.pending_browser=None
        self.history.configure(state="normal")
        self.history.delete("1.0","end")
        self.history.configure(state="disabled")
        self.add("Info","Percakapan baru siap. Catatan kebiasaan dan pengaturan tetap tersimpan.")
        from presence_companion import greet
        greet(self,room,force=True)
        return True

    def stop_reply_voice(self):
        from conversation_stream import clear_display
        clear_display(self)
        live=getattr(self,'live_speech',None)
        if live and live.active:live.cancel()
        self._muted_voice_generation=getattr(self,'generation',0)
        self._tts_waiting=False
        self.translation_progress={}
        if getattr(self,'_translation_pending',False):
            self.frontend.cancel();self._translation_pending=False
        voice=getattr(self,'reply_voice',None)
        if voice:voice.stop()

    def show_task_reaction(self,language,play=True,text=""):
        if getattr(self,'_reaction_shown',False):return
        from task_reactions import TEXT,cached_reaction
        self._reaction_shown=True
        from leva_persona import DELIVERY
        self._reaction_text=DELIVERY.acknowledgement(text,getattr(self,'workspace','assistant'))
        self.add('Leva · Proses',self._reaction_text)
        import time
        self.last_reaction_ms=round((time.perf_counter()-getattr(self,'_request_started',time.perf_counter()))*1000,2)
        if play:self.play_task_reaction(language)

    def play_task_reaction(self,language):
        from task_reactions import cached_reaction,TEXT
        from leva_persona import acknowledgement_speech
        speech=acknowledgement_speech(getattr(self,'_reaction_text',TEXT),language)
        if not speech:return
        if not self.spoken_replies.get() or self.desktop.paused or self.desktop.sleeping:return
        from pipeline_routing import route_spec
        if route_spec(self.mode.get(),self.dual.get())['mode']=='commands':return
        if (self.voice_window and self.voice_window.service.active) or (self.duplex_window and self.duplex_window.service.active):return
        target=self.preferences.get('target_voice_pack')
        path=cached_reaction(target,language,speech=speech)
        if not path:return  # A cold TTS must never delay or evict an active agent.
        try:
            service=self.reply_voice.service
            service.output_device_name=self.preferences.get('output_device_name')
            service.output_hostapi=self.preferences.get('output_hostapi')
            service.reference_callback=self.local_mic.reference
            from task_reactions import SPEECH
            self.local_mic.spoken_text=speech
            self.reply_voice.speak_cached(path,target,language)
        except (ValueError,OSError,RuntimeError):pass

    def prepare_task_reaction(self):
        if self.busy:return
        from pipeline_routing import route_spec
        from speech_resources import pipeline_gpu
        spec=route_spec(self.mode.get(),self.dual.get())
        if spec['mode']=='commands':return
        self.cancel_inference();self.stop_reply_voice()
        self.set_busy(True);self.generation+=1;generation=self.generation
        target=self.preferences.get('target_voice_pack');language=self.preferences.get('speech_language');gpu=pipeline_gpu(spec,'tts')
        self.activity.set('Menyiapkan klip balasan awal · tanpa pemutaran')
        from voice_pack_service import VoicePackService
        preparation=VoicePackService(persistent=True);self.reaction_prepare_service=preparation
        def prepare():
            try:
                from task_reactions import prepare_reaction
                from leva_persona import ACKS,acknowledgement_speech
                for rows in ACKS.values():
                    for phrase in rows:
                        prepare_reaction(target,language,gpu,service=preparation,cancelled=lambda:generation!=self.generation,speech=acknowledgement_speech(phrase,language),stop_service=False)
                notice='14 variasi balasan awal siap untuk voice pack dan bahasa saat ini; diputar tanpa inferensi GPU.'
            except Exception:notice='Sebagian klip balasan awal belum dapat disiapkan. Periksa kapasitas GPU dan Voice Packs; balasan teks tetap langsung tersedia.'
            finally:preparation.stop()
            self.events.put((generation,{'_reaction_prepared':notice}))
        threading.Thread(target=prepare,daemon=True).start()

    def poll_image_jobs(self):
        if self.closed:return
        if not self.desktop.paused and not self.desktop.sleeping and not self.busy:
            pending=set(self.image_jobs.pending())
            while not self.image_events.empty():
                update=self.image_events.get_nowait();engine=update['engine'];ident=update['id'];result=update['result']
                if (engine,ident) not in pending:continue
                self.add('Leva · Gambar',result.get('reply','Status job diperbarui.')+' Job '+ident)
                self.add_image_files(engine,result)
                if result.get('status')=='done' and result.get('outputs'):
                    language=self.preferences.get('speech_language')
                    self.speak_reply('画像ができたよ。画面で確認してね。' if language=='ja' else 'Gambarnya sudah siap. Kamu bisa melihat hasilnya di layar.',language)
                self.image_jobs.acknowledge(engine,ident)
            self._image_gpu_active=bool(self.image_jobs.pending())
            if not self.image_job_busy and self.image_jobs.pending():
                self.image_job_busy=True
                def observe():
                    try:
                        for update in self.image_jobs.observe(self.desktop.tools):self.image_events.put(update)
                    finally:self.image_job_busy=False
                threading.Thread(target=observe,daemon=True).start()
        self.root.after(5000,self.poll_image_jobs)

    def add_image_files(self,engine,result):
        from pathlib import Path
        from paths import DATA
        for row in result.get('outputs',[])[:4]:
            if engine=='fooocus':path=Path(row.get('path',''));base=DATA/'fooocus/outputs'
            else:
                try:code,_,_=self.desktop.tools.comfy_service.installation()
                except ValueError:continue
                base=code/'output';path=base/row.get('subfolder','')/row.get('filename','')
            try:
                path=path.resolve()
                if not path.is_relative_to(base.resolve()) or not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
            except OSError:continue
            label='Buka gambar: '+path.name;self.history.configure(state='normal');start=self.history.index('end-1c')
            self.history.insert('end',label+'\n\n','body');self.link_sequence+=1;tag='image_'+str(self.link_sequence)
            self.history.tag_add(tag,start,start+'+'+str(len(label))+'c');self.history.tag_configure(tag,foreground='#6bdce6',underline=True)
            self.history.tag_bind(tag,'<Button-1>',lambda event,p=str(path):os.startfile(p));self.history.configure(state='disabled');self.history.see('end')

    def set_spoken_replies(self):
        self.save_preference('spoken_replies',self.spoken_replies.get())
        if not self.spoken_replies.get():self.stop_reply_voice()

    def set_speech_language(self):
        self.stop_reply_voice()
        self.save_preference('speech_language','ja' if self.speech_language.get()=='日本語' else 'id')

    def apply_warm_policy(self):
        self.cancel_inference();self.stop_reply_voice()
        self.reply_voice=ReplyVoice(keep_warm=self.preferences.get('keep_models_warm'))
        self.reply_voice.service.reference_callback=self.local_mic.reference

    def speak_reply(self,text,language='id',style='assistant'):
        if not self.spoken_replies.get() or self.desktop.paused or self.desktop.sleeping:return
        if getattr(self,'busy',False):return
        from pipeline_routing import route_spec
        if route_spec(self.mode.get(),self.dual.get())['mode']=='commands':return
        live=self.voice_window
        lab=self.duplex_window
        if (live and live.service.active) or (lab and lab.service.active):return
        pack=self.voice_pack_window
        if pack:pack.stop()
        try:
            self.local_mic.spoken_text=text
            if self.local_mic.active:self.local_mic.worker.send({'kind':'keepalive'})
            self.reply_voice.service.reference_callback=self.local_mic.reference
            self.reply_voice.service.output_device_name=self.preferences.get('output_device_name')
            self.reply_voice.service.output_hostapi=self.preferences.get('output_hostapi')
            from speech_resources import pipeline_gpu
            selected_tts_gpu=pipeline_gpu(route_spec(self.mode.get(),self.dual.get()),'tts',self.preferences.get('tts_gpu'))
            self.reply_voice.service.gpu_preference=selected_tts_gpu
            target=self.preferences.get('target_voice_pack')
            if target.startswith(('higgs_','omnivoice_')):
                from speech_resources import gpu_rows
                from audio_cpp_voice import choose_gpu
                family='higgs_audio_tts' if target.startswith('higgs_') else 'omnivoice'
                if family=='higgs_audio_tts' and selected_tts_gpu=='rtx4050':
                    raise ValueError('Profil Higgs ini terverifikasi pada RTX 5070; RTX 4050 belum dikualifikasi untuk runtime persisten. GPU tidak dialihkan.')
                cached=self.reply_voice.service.loaded and self.reply_voice.service.actual_pack==target
                from live_speech_pipeline import SpeechRuntimePool
                pool=getattr(self,'_speech_runtime_pool',None)
                if isinstance(pool,SpeechRuntimePool) and pool.cached is not None:
                    cached=cached or pool.cached.worker.active and pool.cached.actual_pack==target
                def fits():
                    try:choose_gpu(gpu_rows(),family,selected_tts_gpu);return True
                    except Exception:return False
                if not cached and not fits():
                    # Text/receipts remain intact; release only our caches, then recheck capacity.
                    self.cancel_inference()
                    if not fits() and self.preferences.get('asr_model')!='whisper_cpu' and self.local_mic.active and not self.local_mic.asr_held.is_set():
                        self.audio_resource_hold=True;self._tts_waiting=True
                        self.local_mic.request_asr_hold()
                        self.local_notice='Mikrofon tetap menangkap · GPU dilepas dari ASR untuk TTS'
                        import time
                        self.wait_voice_resources(text,language,style,self.generation,time.monotonic())
                        return
            if self.preferences.get('realtime_speech') is True and target.startswith('higgs_') and not self.reply_voice.active:
                from live_speech_pipeline import LiveSpeechPipeline,SpeechRuntimePool
                pool=getattr(self,'_speech_runtime_pool',None)
                if not isinstance(pool,SpeechRuntimePool):pool=self._speech_runtime_pool=SpeechRuntimePool()
                generation=self.generation;host=getattr(self,'_web_host',None)
                self.live_speech=LiveSpeechPipeline(target,language,style,selected_tts_gpu,
                    authorized=lambda:generation==self.generation and not self.closed and getattr(self,'_muted_voice_generation',None)!=generation,
                    audio_callback=host.bridge.publish_audio if host else None,reference_callback=self.local_mic.reference,
                    output_device=self.preferences.get('output_device_name'),output_hostapi=self.preferences.get('output_hostapi'),
                    native_stream=self.preferences.get('native_voice_stream') is True,pool=pool if self.preferences.get('keep_models_warm') else None)
                self.live_speech.feed(text,final=True);return
            if getattr(self.reply_voice,'is_reaction',False) is True:
                resolved=self.reply_voice.enqueue(text,self.preferences.get('target_voice_pack'),language=language,style=style)
            else:resolved=self.reply_voice.speak(text,self.preferences.get('target_voice_pack'),language=language,style=style)
            if resolved is None:return
            self.hud.last_voice_description=resolved['reason']
        except (ValueError,OSError,RuntimeError) as error:
            self.stop_reply_voice()
            self.add('Info',str(error) if isinstance(error,ValueError) else 'Jawaban suara belum dapat dibuat; teks tetap tersedia. Periksa Voice Packs.')

    def wait_voice_resources(self,text,language,style,generation,started):
        import time
        if self.closed or generation!=self.generation or getattr(self,'_muted_voice_generation',None)==generation or self.desktop.paused or self.desktop.sleeping:
            self._tts_waiting=False;return
        if self.local_mic.asr_held.is_set():
            self._tts_waiting=False;self.speak_reply(text,language,style);return
        if time.monotonic()-started>30:
            self._tts_waiting=False;self.add('Info','Pelepasan GPU suara melewati batas waktu; jawaban teks tetap tersedia.');return
        self.root.after(100,lambda:self.wait_voice_resources(text,language,style,generation,started))

    def run(self):
        self.root.mainloop()

    def open_memory(self):
        from memory_window import MemoryWindow
        MemoryWindow(self)

    def execute_tool(self,name,args,text,valid,generation):
        if generation!=self.generation:return {'status':'cancelled','reply':'Permintaan sudah berganti.'}
        from task_progress import tracker
        progress=tracker(self)
        trace=getattr(self,'process_trace',None)
        if isinstance(trace,__import__('process_trace').TraceHub):trace.emit('tool.started','tool_executor',status='started')
        self.events.put((generation,{'_progress_event':progress.tool(name,args)}))
        self.events.put((generation,{'_tool_progress':name}))
        try:
            result=self.desktop.tools.execute(name,args,text,valid)
        except Exception:
            if isinstance(trace,__import__('process_trace').TraceHub):trace.emit('tool.failed','tool_executor',status='failed')
            self.events.put((generation,{'_progress_event':progress.tool(name,args,{'status':'failed'})}));raise
        self.events.put((generation,{'_progress_event':progress.tool(name,args,result)}))
        if isinstance(trace,__import__('process_trace').TraceHub):trace.emit('tool.failed' if result.get('status')=='failed' else 'tool.completed' if result.get('status')=='done' else 'tool.unverified','tool_executor',{'exit_code':result.get('exit_code')} if result.get('exit_code') is not None else {},status=result.get('status','unverified'))
        return result

    def ensure_local_mic(self):
        if self.closed:return
        if getattr(self,'workspace','assistant')=='companion_avatar' and getattr(self,'companion_mic_consent',False) is not True:
            if self.local_mic.active:self.local_mic.stop()
            return
        if not hasattr(self,'mic_recovery'):
            from mic_recovery import MicRecovery
            self.mic_recovery=MicRecovery()
        self.mic_recovery.tick()
        other=bool(self.voice_window and self.voice_window.service.active)
        if self.audio_resource_hold and not self.busy and not getattr(self,'_image_gpu_active',False) and not self.reply_voice.active and not stream_voice_active(self) and not getattr(self,'_tts_waiting',False) and not getattr(self,'_translation_pending',False):
            # A warm TTS cache can otherwise prevent ASR from fitting back on the
            # chosen cards even though playback has already ended.
            # Releasing a finished engine must not invalidate audio copies that
            # the phone is still playing. Keep the cache if ASR can coexist.
            try:
                from speech_resources import gpu_rows,select_asr_devices,pipeline_gpu
                from pipeline_routing import route_spec
                spec=route_spec(self.mode.get(),self.dual.get())
                select_asr_devices(gpu_rows(),self.preferences.get('asr_model'),pipeline_gpu(spec,'asr',self.preferences.get('asr_gpu')))
            except Exception:
                self.reply_voice.service.stop()
                pool=getattr(self,'_speech_runtime_pool',None)
                if pool:pool.close()
            self.audio_resource_hold=False;self.local_mic.resume_asr()
        from pipeline_routing import route_spec
        enabled=route_spec(self.mode.get(),self.dual.get())['mode']!='commands'
        host=getattr(self,'_web_host',None)
        remote_asr=bool(host and host.bridge.speech.pending())
        eligible=enabled and self.preferences.get('always_listen') and not self.desktop.paused and not self.desktop.sleeping and not other and not getattr(self,'remote_control_active',False) and not remote_asr
        if eligible and self.local_mic_failed and self.mic_recovery.claim():
            self.local_mic.stop();self.local_mic_failed=False
        remaining=self.mic_recovery.remaining()
        if eligible and self.local_mic_failed and remaining is not None:
            self.local_notice='Pendengar berhenti · mencoba ulang dalam '+str(remaining)+' detik'
        # Do not repeatedly bootstrap CUDA ASR while an agent or image job owns VRAM.
        image_hold=bool(getattr(self,'_image_gpu_active',False))
        wanted=eligible and not self.local_mic_failed and (self.local_mic.active or not self.busy and not self.audio_resource_hold and not image_hold and not getattr(self,'_translation_pending',False) and not self.reply_voice.active and not stream_voice_active(self))
        if wanted and not self.local_mic.active:
            try:
                from pipeline_routing import route_spec
                spec=route_spec(self.mode.get(),self.dual.get())
                from speech_resources import pipeline_gpu
                gpu=pipeline_gpu(spec,'asr',self.preferences.get('asr_gpu'))
                if self.preferences.get('asr_model')=='whisper_cpu':
                    raise ValueError('Pilih Qwen3-ASR untuk mode GPU; Whisper CPU tidak mengikuti rute GPU.')
                self.local_mic.start(self.preferences.get('input_device_name'),self.preferences.get('input_hostapi'),
                    self.preferences.get('asr_model'),gpu,self.preferences.get('asr_language'))
                self.local_notice='Memuat pendengar · '+self.preferences.get('asr_model')
            except (OSError,ValueError,RuntimeError) as error:
                from mic_recovery import failure_details
                detail=failure_details(error,'worker_start')
                self.local_mic_failed=True;self.mic_recovery.failed(detail['retryable']);self.local_notice=detail['message']
        elif not wanted and self.local_mic.active:self.local_mic.stop()

    def retry_local_mic(self):
        if self.busy:self.add('Info','Tunggu tugas selesai sebelum mencoba ulang mikrofon.');return
        if not self.preferences.get('always_listen'):
            self.add('Info','Pendengar lokal dinonaktifkan. Aktifkan melalui Pengaturan untuk memakai mikrofon lokal.');return
        self.local_mic.stop();self.local_mic_failed=False
        if hasattr(self,'mic_recovery'):self.mic_recovery.reset()
        self.local_notice='Mencoba ulang mikrofon · rute GPU tetap sama'
        self.ensure_local_mic()

    def poll_local_mic(self):
        if not hasattr(self,'mic_recovery'):
            from mic_recovery import MicRecovery
            self.mic_recovery=MicRecovery()
        for event in self.local_mic.poll():
            kind=event.get('kind')
            if getattr(self,'remote_control_active',False) and kind in ('local_heard','local_heard_partial','local_transcript','local_wake','local_barge_in'):continue
            if kind=='local_status':
                self.local_notice=event['text']
                if event.get('microphone_open'):self.mic_recovery.ready()
            elif kind=='local_partial':self.local_partial=event['text']
            elif kind in ('local_heard','local_heard_partial'):
                self.receive_voice(event)
            elif kind in ('local_armed','local_capture_warning'):
                self.local_notice=event['text'];self.add('Info',event['text'])
            elif kind in ('local_asr_held','local_asr_resumed'):self.local_notice=event['text']
            elif kind=='local_dictation':
                self.dictation_active=event['recording'];self.local_notice=event['text'];self.add('Info',event['text'])
                button=getattr(self.hud.mic_indicator,'dictate_button',None)
                if button:button.configure(text='Selesai & kirim' if self.dictation_active else 'Rekam perintah panjang',state='normal')
            elif kind=='local_wake':
                if not event.get('journalled'):
                    self.local_notice='Aku mendengarkan · percakapan lanjutan 45 detik'
            elif kind=='local_barge_in':
                # Stop playback immediately, but do not discard an in-flight
                # desktop task before knowing what the new utterance requests.
                self.stop_reply_voice();self.local_notice='Ucapan baru · keluaran suara disela, tugas tetap berjalan'
            elif kind=='local_transcript':
                if not event.get('journalled'):
                    self.receive_voice({**event,'kind':'local_heard','text':event.get('raw_transcript',event.get('text','')),
                                        'command':event.get('text',''),'accepted':True,'reason':'followup','final':True})
            elif kind=='error':
                self.local_mic_failed=True;self.mic_recovery.failed(event.get('retryable',True))
                self.local_notice=event.get('message','Mikrofon lokal berhenti: '+event.get('code','unknown'))
                if hasattr(self,'_speech_inbox'):self._speech_inbox.fail_collecting(self.local_notice)
                self.add('Info',self.local_notice)
            elif kind=='stopped':
                self.dictation_active=False
                button=getattr(self.hud.mic_indicator,'dictate_button',None)
                if button:button.configure(text='Rekam perintah panjang',state='normal')
                if hasattr(self,'_speech_inbox'):self._speech_inbox.fail_collecting('Pendengar berhenti sebelum ucapan selesai.')

    def speech_inbox(self):
        if not hasattr(self,'_speech_inbox'):
            from speech_turns import SpeechJournal
            self._speech_inbox=SpeechJournal();self._speech_inbox.recover()
        return self._speech_inbox

    def receive_voice(self,event):
        from presence_companion import touch
        touch(self,event.get('text',''))
        from speech_turns import STATUS_LABELS,stop_request
        try:
            row=self.speech_inbox().capture(event)
        except (OSError,sqlite3.Error):
            self.add('Info','Catatan suara tidak dapat disimpan di D; perintah belum dijalankan.');return
        self.local_partial='';self.local_notice=STATUS_LABELS[row['state']]
        if event.get('kind')=='local_heard_partial':return
        if row['text']:self.add('Anda · 🎙 Tertangkap',row['text'])
        if row['state']=='queued' and (self.desktop.paused or self.desktop.sleeping):
            self.speech_inbox().update(row['id'],'interrupted','Sistem dijeda; ucapan tidak dijalankan otomatis.');return
        if row['state']=='queued' and stop_request(row['command']):
            self.cancel_voice_queue();self.interrupt_schedule();self.desktop.stop_owned_processes()
            self.cancel_inference();self.stop_reply_voice();self.generation+=1;self.set_busy(False)
            self.speech_inbox().update(row['id'],'completed','Tugas dihentikan atas perintah suara.')
            self.add('Leva','Tugas dan antrean suara dihentikan.');return
        if row['state']=='queued':
            self.local_notice='Perintah diterima · menunggu tugas aktif' if self.busy else 'Perintah diterima · siap diproses'
        elif row['state']=='wake_only':
            from presence_companion import touch
            touch(self)
            self.add('Leva','Ya, aku mendengarkan. Sampaikan perintahmu.')
        elif row['text']:self.add('Info · Suara',STATUS_LABELS[row['state']])

    def dispatch_voice(self):
        if not hasattr(self,'_speech_inbox') or self.closed or self.busy or self.desktop.paused or self.desktop.sleeping:return
        if self.voice_window and self.voice_window.service.active:return
        try:
            rows=self._speech_inbox.pending()
            if not rows:return
            row=rows[0]
            if self.entry.get().strip():
                if row['state']!='waiting_draft':
                    self._speech_inbox.update(row['id'],'waiting_draft');self.add('Info','Perintah suara tersimpan penuh. Kirim atau kosongkan draf ketikan untuk melanjutkan.')
                self.local_notice='Perintah suara menunggu draf ketikan';return
            self._speech_inbox.update(row['id'],'running')
            self.local_notice='Perintah suara sedang diproses'
            self.send(row['command'],display='🎙 '+row['text'],voice_id=row['id'])
        except (OSError,sqlite3.Error):self.local_notice='Catatan suara belum tersedia; periksa drive D.'

    def cancel_voice_queue(self):
        if not hasattr(self,'_speech_inbox'):return
        self._speech_inbox.cancel_pending()
        if getattr(self,'active_voice',None):
            self._speech_inbox.update(self.active_voice[0],'interrupted');self.active_voice=None

    def arm_local_mic(self):
        if getattr(self,'workspace','assistant')=='companion_avatar':self.companion_mic_consent=True
        if self.desktop.paused or self.desktop.sleeping:
            self.add('Info','Aktifkan kembali Leva sebelum menerima perintah suara.');return
        if not self.local_mic.active:
            self.retry_local_mic()
            if not self.local_mic.active:return
        self.local_mic.worker.send({'kind':'arm'})
        self.local_notice='Mengaktifkan penerimaan perintah · tunggu konfirmasi pendengar'

    def toggle_dictation(self):
        if self.desktop.paused or self.desktop.sleeping:
            self.add('Info','Aktifkan Leva sebelum merekam perintah.');return
        if not self.local_mic.active:
            self.retry_local_mic()
            if not self.local_mic.active:return
        action='dictation_commit' if getattr(self,'dictation_active',False) else 'dictation_start'
        if action=='dictation_start':self.stop_reply_voice()
        button=getattr(self.hud.mic_indicator,'dictate_button',None)
        if button:button.configure(state='disabled')
        self.local_mic.worker.send({'kind':action})
        self.local_notice='Menunggu konfirmasi pendengar'

    def open_speech_log(self):
        from speech_log_window import SpeechLogWindow
        SpeechLogWindow(self)

    def apply_autonomy_settings(self):
        import sys
        self.local_mic_failed=False
        if hasattr(self,'mic_recovery'):self.mic_recovery.reset()
        if self.local_mic.active:self.local_mic.stop()
        if getattr(sys,'frozen',False):
            from autonomy_services import startup
            try:startup(self.preferences.get('autostart'))
            except (OSError,ValueError):self.add('Info','Startup Windows belum berhasil diubah; aplikasi tetap dapat dijalankan manual.')
        self.apply_theme();self.ensure_local_mic()

    def apply_theme(self):
        accent={'cyan':'#6bdce6','gold':'#f7c66d','violet':'#c29bf3'}[self.preferences.get('theme')]
        old={'#6bdce6','#7ce4ca','#f7c66d','#c29bf3'}
        def recolor(widget):
            for option in ('fg','foreground','insertbackground'):
                try:
                    if str(widget.cget(option)).lower() in old:widget.configure(**{option:accent})
                except tk.TclError:pass
            for child in widget.winfo_children():recolor(child)
        recolor(self.root)
        style=ttk.Style()
        style.configure('TFrame',background='#111b2d')
        style.configure('TLabel',background='#111b2d',foreground='#e7edf8')
        style.configure('TCheckbutton',background='#111b2d',foreground='#e7edf8',indicatorbackground='#1b2940')
        style.map('TCheckbutton',background=[('active','#1b2940')],foreground=[('disabled','#99abc5'),('active','#e7edf8')],indicatorbackground=[('selected',accent)])
        style.configure('TEntry',fieldbackground='#1b2940',foreground='#e7edf8',insertcolor='#e7edf8')
        style.map('TNotebook.Tab',foreground=[('selected',accent)])
        style=ttk.Style();style.configure('Treeview',background='#111b2d',fieldbackground='#111b2d',foreground='#e7edf8',rowheight=25);style.configure('Treeview.Heading',background='#182b3a',foreground=accent);style.map('Treeview',background=[('selected','#284453')])
        from neural_orb import PALETTES
        PALETTES['idle']={'cyan':(87,222,219),'gold':(240,180,77),'violet':(194,155,243)}[self.preferences.get('theme')]

    def proactive_allowed(self):
        from windows_runtime import idle_milliseconds
        idle=idle_milliseconds()
        return not self.closed and self.preferences.get('proactive') and not self.busy and not self.desktop.paused and not self.desktop.sleeping and not self.reply_voice.active and not stream_voice_active(self) and idle is not None and idle>=60000

    def daily_briefing(self):
        if self.closed:return
        today=datetime.now(WIB).date().isoformat()
        if self.preferences.get('briefing') and self.preferences.get('briefing_last_date')!=today and not self.busy and not self.desktop.paused and not self.desktop.sleeping and not self.entry.get().strip():
            city=self.preferences.get('weather_city')
            prompt='Buat briefing singkat: jam komputer saat ini, agenda lokal hari ini dan 3 headline berita terbaru dengan tautan sumber.'
            if city:prompt+=' Sertakan cuaca lokasi perangkat/pengaturan; gunakan city kosong agar host memilih sumber lokasi.'
            self.preferences.set('briefing_last_date',today);self.send(prompt,display='Briefing harian otomatis')
        self.root.after(60000,self.daily_briefing)

    def open_advanced(self):
        from advanced_window import AdvancedWindow
        if self.advanced_window and self.advanced_window.window.winfo_exists():self.advanced_window.window.lift();return
        self.advanced_window=AdvancedWindow(self)

    def open_router(self):
        from router_window import RouterWindow
        if self.router_window and self.router_window.window.winfo_exists():self.router_window.window.lift();return
        self.router_window=RouterWindow(self)

    def open_link(self,url):
        if self.busy or self.entry.get().strip():self.add('Info','Selesaikan permintaan/draf aktif sebelum membuka tautan.');return
        self.send('buka Chrome untuk '+url)

    def open_skills(self):
        from assistant_tools import SKILLS
        window=tk.Toplevel(self.root);window.title('Leva — Skill & aplikasi');window.geometry('940x650');window.configure(bg=BG)
        self.label(window,'Skill & aplikasi',bg=BG,font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=20)
        self.label(window,'Model memilih alat ini sesuai tujuan Anda. Hasil tindakan dikembalikan ke percakapan.',bg=BG,fg=ACCENT).pack(anchor='w',padx=24)
        tabs=ttk.Notebook(window);tabs.pack(fill='both',expand=True,padx=24,pady=16)
        skills=ttk.Treeview(tabs,columns=('name','detail'),show='headings');skills.heading('name',text='Skill');skills.heading('detail',text='Kemampuan');skills.column('name',width=140);skills.column('detail',width=690)
        tabs.add(skills,text='Skill aktif')
        for skill in SKILLS:skills.insert('','end',values=(skill.name,skill.description))
        guides=ttk.Treeview(tabs,columns=('name','detail'),show='headings');guides.heading('name',text='Panduan');guides.heading('detail',text='Prosedur & sumber');guides.column('name',width=260);guides.column('detail',width=570)
        tabs.add(guides,text='Panduan terkurasi')
        for row in self.desktop.tools.workflows.rows():guides.insert('','end',values=(row['title'],row['description']+' · '+row['source']))
        from capability_catalog import catalog as source_catalog
        sources=ttk.Treeview(tabs,columns=('name','detail'),show='headings');sources.heading('name',text='Repo');sources.heading('detail',text='Status integrasi');sources.column('name',width=300);sources.column('detail',width=530)
        tabs.add(sources,text='Sumber kemampuan')
        for row in source_catalog()['sources']:sources.insert('','end',values=(row['repo'],row['integration']+' · '+row['detail']))
        panel=tk.Frame(tabs,bg=PANEL);tabs.add(panel,text='Aplikasi terdeteksi')
        apps=ttk.Treeview(panel,columns=('name',),show='headings');apps.heading('name',text='Aplikasi dari instalasi / Start Menu');apps.pack(fill='both',expand=True)
        catalog=self.desktop.tools.apps
        for row in catalog.public():apps.insert('','end',iid=row['id'],values=(row['name'],))
        def open_selected():
            chosen=apps.selection()
            if chosen:self.send('buka aplikasi '+catalog.apps[chosen[0]]['name'])
        self.button(panel,'Buka aplikasi pilihan',open_selected,primary=True).pack(anchor='w',padx=12,pady=12)
        games_panel=tk.Frame(tabs,bg=PANEL);tabs.add(games_panel,text='Game Steam')
        games=ttk.Treeview(games_panel,columns=('name','id'),show='headings')
        games.heading('name',text='Instalasi game yang siap dijalankan');games.heading('id',text='Steam App ID');games.column('name',width=640);games.column('id',width=130);games.pack(fill='both',expand=True)
        for row in self.desktop.tools.steam.public():games.insert('','end',iid=row['id'],values=(row['name'],row['id']))
        def launch_selected():
            chosen=games.selection()
            if chosen:self.send('jalankan game '+self.desktop.tools.steam.games[chosen[0]]['name'])
        self.button(games_panel,'Jalankan game pilihan',launch_selected,primary=True).pack(anchor='w',padx=12,pady=12)
