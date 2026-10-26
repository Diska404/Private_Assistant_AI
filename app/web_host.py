"""Main-thread adapter: the browser shares the exact desktop inference/audio services."""
from collections import deque
from pathlib import Path
import queue
import threading
import time
import urllib.request
import webbrowser
from web_bridge import WebBridge
from web_data import WebData
from web_store import WebStore,delivery_status

class DesktopWebHost:
    def __init__(self,main):
        self.main=main
        # Fixture Preferences live beside their own isolated remote database.
        prefs_path=getattr(main.preferences,'path',None)
        db=prefs_path.parent/'web-control.sqlite3' if isinstance(prefs_path,Path) else None
        remote=main.preferences.get('web_remote_origin') if isinstance(prefs_path,Path) else ''
        self.bridge=WebBridge(WebData(main.desktop.tools),int(main.preferences.get('web_port')),store=WebStore(db),remote=remote)
        from conversation_export import current_transcript
        self.bridge.transcript_provider=lambda room:current_transcript(main,room)
        self.bridge.trace_store_provider=lambda:getattr(main,'_trace_store',None)
        self.opening=False;self.last_update=0;self.active_job=None;self.stopped=False
        self.bind_audio()
        for speaker,text in getattr(main,'_web_log',[]):self.bridge.log(speaker,text)
    def open(self,show=True):
        if self.opening:return
        self.opening=True;self.main.add('Info','Membuka versi web lokal; memakai agent dan audio desktop yang sama.')
        def start():
            try:
                url=self.bridge.start()
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(self.bridge.origin+'/health',timeout=3) as response:
                    if response.status!=200:raise OSError('web_not_ready')
                self.main.events.put((self.main.generation,{'_web_ready':url,'_web_open_browser':show}))
            except Exception as error:self.main.events.put((self.main.generation,{'_web_failure':type(error).__name__}))
        threading.Thread(target=start,daemon=True).start()
    def bind_audio(self):
        voice=getattr(self.main,'reply_voice',None)
        if voice:
            voice.audio_cancel_callback=self.bridge.cancel_audio
            voice.service.audio_ready_callback=self.bridge.publish_audio
        from conversation_stream import output_service,voice_active
        if voice_active(self.main):output_service(self.main).audio_ready_callback=self.bridge.publish_audio
    def ready(self,result):
        self.opening=False
        if result.get('_web_ready'):
            if result.get('_web_open_browser',True) and not webbrowser.open(result['_web_ready']):self.main.add('Info','Layanan web siap, tetapi browser default belum terbuka. Tekan Versi Web untuk mencoba lagi.')
        else:self.main.add('Info','Versi web belum dapat dimulai: '+result['_web_failure'])
    def cancel_queue(self):
        while not self.bridge.commands.empty():
            try:self.bridge.finish(self.bridge.commands.get_nowait(),'cancelled','Dibatalkan dari kontrol desktop/web.')
            except queue.Empty:break
    def control(self,job):
        m=self.main;kind=job['kind'];value=job.get('value')
        if kind in ('route','dual','language','spoken','new_conversation','workspace','room_settings','handoff') and m.busy:raise ValueError('Tunggu tugas aktif selesai sebelum mengubah pengaturan/percakapan.')
        if kind in ('route','dual') and self.bridge.speech.pending():raise ValueError('Tunggu transkrip selesai atau batalkan rekaman sebelum mengubah GPU/rute.')
        if kind in ('release','pause','new_conversation'):
            self.cancel_queue()
            for row in list(self.bridge.speech.jobs.values()):
                if row['status'] in ('queued','running'):self.bridge.speech.cancel(row['id'],row['owner'])
        if kind in ('release','pause') and self.active_job:self.complete({'cancelled':True,'reply':'Dihentikan dari kontrol desktop/web; periksa hasil tindakan yang sudah berjalan.'})
        if kind=='release':m.release()
        elif kind=='pause':
            if not m.desktop.paused:m.toggle_pause()
        elif kind=='resume':
            if m.desktop.paused or m.desktop.sleeping:m.toggle_pause()
        elif kind=='stop_voice':m.stop_reply_voice()
        elif kind=='arm':m.arm_local_mic()
        elif kind in ('dictation_start','dictation_commit'):
            desired=kind=='dictation_start'
            if desired!=bool(getattr(m,'dictation_active',False)):m.toggle_dictation()
        elif kind=='new_conversation':
            self.bridge.logs.clear();getattr(m,'_web_log',deque()).clear();m.new_conversation()
        elif kind=='handoff':
            from room_ui import accept_handoff
            if not accept_handoff(m,value):raise ValueError('Perpindahan belum dilakukan.')
        elif kind=='workspace':
            from room_ui import switch_workspace
            switch_workspace(m,value)
        elif kind=='companion_settings':
            from companion_avatar import configure
            configure(m,value)
        elif kind=='companion_stop':
            from companion_avatar import interrupt
            interrupt(m)
            if self.active_job:self.complete({'cancelled':True,'reply':'Percakapan companion dihentikan.'})
        elif kind=='room_settings':
            from room_ui import apply_room_settings
            apply_room_settings(m,value)
        elif kind=='route':
            from pipeline_routing import route_spec
            m.dual.set(route_spec(value)['gpu']=='dual');m.mode.set(value)
        elif kind=='dual':m.dual.set(value)
        elif kind=='language':m.speech_language.set('日本語' if value=='ja' else 'Indonesia')
        elif kind=='spoken':m.spoken_replies.set(value)
        elif kind=='persona_settings':
            from presence_companion import apply_settings
            apply_settings(m,value)
        elif kind=='pipeline_settings':
            from speech_configuration import apply_pipeline_settings
            apply_pipeline_settings(m,value)
        elif kind=='test_audio':
            from task_reactions import cached_reaction
            pack=m.preferences.get('target_voice_pack');language=m.preferences.get('speech_language')
            path=cached_reaction(pack,language)
            if path is None:raise ValueError('Klip uji belum tersedia. Aktifkan Jawaban suara lalu kirim pesan ke Leva.')
            self.bridge.publish_audio(path,{'pack':pack,'language':language})
        elif kind=='navigate':{'center':m.open_advanced,'skills':m.open_skills,'memory':m.open_memory,'voice':m.open_voice_packs,'settings':m.open_settings}[value]()
    def complete(self,result):
        if not self.active_job:return
        status=delivery_status(result)
        self.bridge.finish(self.active_job,status,str(result.get('error') or result.get('reply') or result.get('response') or 'Selesai.'),result.get('task_id',''))
        self.active_job=None
    def progress(self,tool):
        if self.active_job:self.bridge.finish(self.active_job,'running','Menjalankan '+tool)
    def poll(self):
        m=self.main
        self.bind_audio()
        with self.bridge.lock:clients=self.bridge.presence.active(self.bridge.store.active)
        m.remote_clients=clients
        remote=any(c['kind'] in ('android','ios') for c in clients)
        if remote!=bool(getattr(m,'remote_control_active',False)):
            m.remote_control_active=remote
            if remote:
                m.local_mic.stop()
                if hasattr(m,'cancel_voice_queue'):m.cancel_voice_queue()
                m.local_notice='HP tersambung · mic laptop dijeda · gunakan tombol mic HP'
            if hasattr(m,'ensure_local_mic'):m.ensure_local_mic()
        from conversation_stream import voice_active
        if self.bridge.speech.pending() and not m.busy and not m.desktop.paused and not m.desktop.sleeping and not m.reply_voice.active and not voice_active(m) and not getattr(m,'_translation_pending',False):
            from pipeline_routing import route_spec
            from speech_resources import pipeline_gpu
            spec=route_spec(m.mode.get(),m.dual.get())
            if spec['gpu']!='none':
                model=m.preferences.get('asr_model')
                if model not in ('qwen_asr_06b','qwen_asr_17b'):model='qwen_asr_06b'
                def prepare():
                    m.local_mic.stop();m.reply_voice.cancel(keep_warm=False);m.chat.cancel();m.frontend.cancel()
                self.bridge.speech.pump({'model':model,'gpu':pipeline_gpu(spec,'asr',m.preferences.get('asr_gpu')),'language':m.preferences.get('asr_language')},self.bridge.store.active,prepare)
        for _ in range(5):
            try:job=self.bridge.controls.get_nowait()
            except queue.Empty:break
            if not self.bridge.store.active(job.get('owner','desktop')):
                self.bridge.finish(job,'cancelled','Perangkat telah dicabut.');continue
            try:self.control(job);self.bridge.finish(job,'dispatched','Kontrol diteruskan ke desktop.')
            except Exception as error:
                self.bridge.finish(job,'failed',str(error));m.add('Info','Kontrol web belum diterapkan: '+str(error)[:200])
        if not m.busy and not self.bridge.speech.pending() and not m.entry.get().strip():
            try:
                job=self.bridge.commands.get_nowait()
                if not self.bridge.store.active(job.get('owner','desktop')):self.bridge.finish(job,'cancelled','Perangkat telah dicabut.')
                else:
                    self.active_job=job;self.bridge.finish(job,'running','Permintaan sedang dikerjakan oleh desktop.')
                    try:
                        value=job['value']
                        if isinstance(value,dict):
                            rows=self.bridge.uploads.resolve(job.get('owner','desktop'),value['attachments'])
                            accepted=m.send(value['text'],client_context=job.get('client'),workspace=value['workspace'],attachments=rows)
                        elif job.get('client'):accepted=m.send(value,client_context=job['client'])
                        else:accepted=m.send(value)
                        if accepted is False:self.complete({'error':'Permintaan belum dimulai; periksa pesan pada ruang percakapan.'})
                    except Exception as error:self.complete({'error':type(error).__name__})
            except queue.Empty:pass
        if time.monotonic()-self.last_update<.25:return
        self.last_update=time.monotonic()
        from pipeline_routing import VOICE_SINGLE as SINGLE_CHOICES,VOICE_DUAL as DUAL_CHOICES,route_spec
        mic=m.local_mic.telemetry.snapshot(m.local_mic.active)
        from conversation_stream import output_service,voice_active
        output=float(getattr(output_service(m),'output_level',0));active=m.local_mic.active
        tool=getattr(m,'_web_tool','') if m.busy else ''
        phase='paused' if m.desktop.paused or m.desktop.sleeping else 'speaking' if output>0 and (m.reply_voice.active or voice_active(m)) else 'memory' if tool=='obsidian_action' else 'tool' if tool else 'thinking' if m.busy else 'listening' if active else 'idle'
        if not m.busy and getattr(m,'_web_last_error',''):phase='error'
        hardware=getattr(m,'hardware',None)
        from speech_configuration import configuration_snapshot
        self.bridge.update({'phase':phase,'busy':m.busy,'route':m.mode.get(),'dual':m.dual.get(),'route_choices':list(dict.fromkeys(SINGLE_CHOICES+DUAL_CHOICES)),
            'language':m.preferences.get('speech_language'),'spoken':m.spoken_replies.get(),'mic':mic,'output_level':round(output,4),
            'translation_pending':bool(getattr(m,'_translation_pending',False)),'workspace':getattr(m,'workspace','assistant'),'rooms':m.rooms.snapshot(m.preferences) if hasattr(m,'rooms') else {},'handoff':m.rooms.pending if hasattr(m,'rooms') else None,
            'avatar':__import__('companion_avatar').presentation(m,phase,output),
            'experimental_models_enabled':m.preferences.get('experimental_models_enabled'),
            'pipeline':configuration_snapshot(m.preferences,route_spec(m.mode.get(),m.dual.get())),
            'audio_output':m.preferences.get('output_device_name'),'model':m.preferences.get('agent_local_model'),'tool':tool,
            'hardware':hardware.value if hardware else {},'hardware_age_s':round(max(0,time.time()-hardware.value['measured_at']),1) if hardware and hardware.value.get('measured_at') else None,
            'activity':m.activity.get(),'voice_pack':m.preferences.get('target_voice_pack'),
            'avatar_revision':self.bridge.avatar.metadata()['revision'],
            'voice_progress':m.live_speech.progress() if voice_active(m) else m.reply_voice.progress(),
            'translation_progress':getattr(m,'translation_progress',{}),
            'task_progress':__import__('task_progress').tracker(m).snapshot() if getattr(m,'workspace','assistant') in ('assistant','chat') else [],
            'trace_events':m.process_trace.snapshot(getattr(m,'workspace','assistant')) if isinstance(getattr(m,'process_trace',None),__import__('process_trace').TraceHub) else [],
            'reply_stream':getattr(m,'_web_stream',{}) if isinstance(getattr(m,'_web_stream',None),dict) else {},
            'companion':{**__import__('presence_companion').settings(m),'last':getattr(m,'companion_last',{}),'max_per_idle':2,'max_per_hour':4},
            'clients':clients,'desktop_mic_suspended':remote,'mobile_mic':'push_to_talk_draft',
            'error':getattr(m,'_web_last_error',''),'text_ms':getattr(m,'last_text_ms',None),'version':'0.44.0','shared_agent':True})
    def stop(self):
        if self.stopped:return
        self.stopped=True
        self.cancel_queue()
        if self.active_job:self.bridge.finish(self.active_job,'interrupted','Desktop dihentikan; periksa hasil sebelum melanjutkan.');self.active_job=None
        self.bridge.stop();self.bridge.store.close()
