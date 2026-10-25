"""Leva Windows desktop preview and isolated inference worker entrypoint."""
import json
import os
from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "experiments")]

from paths import ROOT, DATA


def main():
    if '--microphone-self-test' in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from mic_runtime_check import check
        sys.stdout.write(json.dumps(check(),ensure_ascii=True));sys.stdout.flush()
        return
    if '--performance-check' in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from performance_check import check
        sys.stdout.write(json.dumps(check(),ensure_ascii=True));sys.stdout.flush()
        return
    if '--chat-session-worker' in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from chat_service import session_worker
        def emit(event):
            sys.stdout.write(json.dumps(event,ensure_ascii=True)+'\n');sys.stdout.flush()
        session_worker(emit)
        return
    if '--spoken-reply-check' in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from spoken_reply_check import check
        sys.stdout.write(json.dumps(check(),ensure_ascii=True));sys.stdout.flush()
        return
    if "--voice-pack-self-test" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from voice_pack_check import check_runtime
        sys.stdout.write(json.dumps(check_runtime(), ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--duplex-worker" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from duplex_service import duplex_worker
        def emit(event):
            sys.stdout.write(json.dumps(event,ensure_ascii=True)+"\n")
            sys.stdout.flush()
        duplex_worker(emit)
        return
    if "--duplex-replay" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from duplex_core import replay_scenarios
        sys.stdout.write(json.dumps(replay_scenarios(),ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--voice-worker" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from live_voice import voice_worker
        request = json.loads(sys.stdin.readline())
        def emit(event):
            sys.stdout.write(json.dumps(event, ensure_ascii=True) + "\n")
            sys.stdout.flush()
        voice_worker(request, emit)
        return
    if "--voice-devices" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from live_voice import audio_devices
        sys.stdout.write(json.dumps(audio_devices(),ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--chat-worker" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from chat_service import run_worker
        from hybrid_engine import EngineError
        try:
            request = json.load(sys.stdin)
            result = run_worker(request)
        except EngineError as error:
            result = {"error": str(error)}
        except Exception:
            result = {"error": "worker_configuration_or_runtime_error"}
        sys.stdout.write(json.dumps(result, ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--packaged-self-test" in sys.argv:
        # No external network/model/browser effects: validate a packaged worker's pipe and ownership.
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from chat_service import ChatService
        service = ChatService(persistent=False)
        results = {}
        try:
            service.ask("", "local")  # Empty message is rejected before any inference starts.
        except Exception as error:
            results["worker_roundtrip"] = str(error) == "invalid_chat_request"
        import tempfile
        from preferences import Preferences
        from scheduled_tasks import ScheduleStore,parse_schedule
        from datetime import datetime,timedelta
        from command_resolution import WIB
        check_dir = DATA / "verification"
        check_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=check_dir,prefix="storage-self-test-") as folder:
            if not Path(folder).resolve().is_relative_to(check_dir.resolve()):
                raise RuntimeError("invalid_self_test_directory")
            path=Path(folder)/"fixture.sqlite3"
            from speech_stream import receive_pcm
            from voice_pack_service import VoicePackService
            import io,base64,struct
            raw=struct.pack('<h',500)*24000
            fixture=b'data: '+json.dumps({'type':'speech.audio.delta','audio':base64.b64encode(raw).decode()}).encode()+b'\n\ndata: {"type":"speech.audio.done"}\n\ndata: [DONE]\n\n'
            class StreamFixture(io.BytesIO):headers={'Content-Type':'text/event-stream'}
            clips=[];parsed=receive_pcm(StreamFixture(fixture),Path(folder)/'stream.wav',clips.append)
            results['bounded_stream_parser']=parsed['stream_completed'] and parsed['pcm_bytes']==len(raw) and len(clips)==2
            results['stable_speech_default']=VoicePackService().stream_audio is False
            results['speech_stream_worker_asset']=(Path(sys._MEIPASS)/'local_voice_runtime/speech_stream.py').is_file() if getattr(sys,'frozen',False) else (ROOT/'app/speech_stream.py').is_file()
            store=Preferences(path)
            try:
                store.set("voice","Leda")
                store.set_alias("fixture","synthetic-profile")
                for _ in range(3):store.record("youtube","synthetic-profile")
            finally:
                store.close()
            store=Preferences(path)
            try:
                results["storage_roundtrip"]=store.persistent and store.get("voice")=="Leda" and store.suggestions({"synthetic-profile"})=={"youtube":"synthetic-profile"}
            finally:
                store.close()
            now=datetime.now(WIB)
            schedules=ScheduleStore(Path(folder)/'schedules.sqlite3')
            job=schedules.add(**parse_schedule('ingatkan uji dalam 1 menit lalu buka Notepad',now),now=now)
            due=now+timedelta(minutes=1)
            results['scheduler_roundtrip']=(schedules.claim(now) is None
                and len(schedules.notifications(due))==1
                and schedules.notifications(due)==[]
                and schedules.claim(due)['id']==job['id']
                and schedules.claim(due) is None)
            schedules.finish(job['id'],'completed','Self-test only; no application launched.')
            results['scheduler_persisted']=ScheduleStore(Path(folder)/'schedules.sqlite3').recent()[0]['status']=='completed'
            from project_workspace import ProjectWorkspace
            from terminal_service import TerminalService
            from task_journal import TaskJournal
            project=ProjectWorkspace(Path(folder)/'patch-history');target=Path(folder)/'example.py'
            target.write_text('value = 1\n',encoding='utf-8')
            preview=project.preview(Path(folder),'--- a/example.py\n+++ b/example.py\n@@\n-value = 1\n+value = 2\n')
            project.change(preview['patch_id']);applied=target.read_text('utf-8')=='value = 2\n'
            project.change(preview['patch_id'],True);results['patch_roundtrip']=applied and target.read_text('utf-8')=='value = 1\n'
            terminal=TerminalService(Path(folder)/'terminal')
            try:
                process=terminal.start('python','print("LEVA_TERMINAL_OK")',folder,10)
                for _ in range(12):
                    output=terminal.poll(process['process_id'],wait=1)
                    if output['status']!='running':break
                results['terminal_roundtrip']=output.get('exit_code')==0 and 'LEVA_TERMINAL_OK' in output.get('output','')
            finally:terminal.stop_all()
            journal=TaskJournal(Path(folder)/'tasks.sqlite3');task=journal.begin('Buka Chrome lalu Edge')
            journal.wait_for_input(task,'Profil mana yang ingin digunakan?')
            results['task_continuity']=TaskJournal(journal.path).continuation('Diska')['id']==task
            from comfy_service import ComfyService,validate_graph,ui_workflow
            fixture={'Source':{'input':{'required':{'width':['INT',{'min':1,'max':64}]}},'output':['IMAGE']},
                     'Sink':{'input':{'required':{'images':['IMAGE']}},'output':[],'output_node':True}}
            graph={'1':{'class_type':'Source','inputs':{'width':8}},'2':{'class_type':'Sink','inputs':{'images':['1',0]}}}
            results['comfy_graph_validation']=validate_graph(graph,fixture)['links']==1 and len(ui_workflow(graph,fixture)['nodes'])==2
            from assistant_tools import comfy_generation_requested
            results['comfy_generation_typo']=comfy_generation_requested('bisakah leva buat 1 generat gambar dengan template bebas')
            results['comfy_template_is_not_generation']=not comfy_generation_requested('buka comfyui dan buatkan template gambar untuk mengenerate gambar')
            from comfy_service import ComfyError
            try:
                ComfyService(storage=Path(folder)/'vae-check').check_vae({'1':{'class_type':'EmptyLatentImage'},'2':{'class_type':'VAELoader','inputs':{'vae_name':'ae.safetensors'}}})
                results['comfy_incompatible_vae_blocked']=False
            except ComfyError:results['comfy_incompatible_vae_blocked']=True
            comfy=ComfyService(storage=Path(folder)/'comfy')
            record={'id':'123456abcdef','base':comfy.client.base,'title':'self-test','state':'queued','prompt_id':'fixture-job','selection':{}}
            comfy._save(record)
            results['comfy_job_persisted']=ComfyService(storage=comfy.storage).recent()['workflows'][0]['prompt_id']=='fixture-job'
            from image_jobs import ImageJobs
            from fooocus_service import FooocusService
            jobs=ImageJobs(Path(folder)/'image-jobs.sqlite3');jobs.track('fooocus','123456abcdef')
            results['image_job_persisted']=ImageJobs(jobs.path).pending()==[('fooocus','123456abcdef')]
            jobs.acknowledge('fooocus','123456abcdef')
            foo=FooocusService.__new__(FooocusService)
            results['compatible_gpu_selection']=foo.pick_gpu([{'name':'large-incompatible','total':12,'compatible':False},{'name':'compatible','total':6,'compatible':True}])['name']=='compatible'
            from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,route_spec,visible_route
            results['speech_route_matrix']=len(SINGLE_CHOICES)==9 and len(DUAL_CHOICES)==5 and all(
                route_spec(visible_route(label,True))['local_mode']=='dual' for label in SINGLE_CHOICES[1:])
            results['no_ai_has_no_provider']=route_spec('Tanpa AI',True)['providers']==[]
            from conversation_frontend import parse_frontend
            original='Dua menit lagi buka Chrome Diska, jangan sekarang.'
            results['frontend_preserves_original_goal']=parse_frontend({'response':'{"kind":"delegate","summary":"buka sekarang"}'},original)['original_goal']==original
            results['natural_relative_reminder']=datetime.fromisoformat(parse_schedule('Dua menit lagi ingatkan belajar',now)['when'])==due+timedelta(minutes=1)
            from conversation_frontend import conversation_request
            from speech_resources import agent_mode
            from saluki_backend import SalukiEngine
            from task_reactions import needs_reaction
            class NoModel:
                def ask(self,*args,**kwargs):raise RuntimeError('unexpected_frontend_inference')
            routed=conversation_request(NoModel(),original,route_spec('Dual GPU'),None,'ja',True)
            results['direct_delegation_preserves_schedule']=routed['original_goal']==original and routed['frontend_bypassed']
            results['saluki_dual_payload']=SalukiEngine(Path(folder),acceleration='plain',mode=agent_mode(route_spec('Dual GPU'))).mode=='dual'
            results['reaction_does_not_block_pause']=not needs_reaction('Leva, jedakan sistemmu')
            from mic_recovery import MicRecovery,failure_details
            recovery=MicRecovery()
            for n in range(4):recovery.failed(now=n*100)
            results['microphone_retry_bounded']=recovery.retry_at is None and not recovery.claim(now=10000)
            failure=OSError('fixture');failure.winerror=1455
            results['microphone_error_classification']=failure_details(failure,'asr_load')['code']=='microphone_windows_memory'
            from speech_turns import SpeechJournal,TurnAssembler
            journal=SpeechJournal(Path(folder)/'speech-test.db')
            raw='Leva, jangan buka sebelum jam 19:00. '*200
            item=journal.capture({'text':raw,'reason':'awaiting_wake'})
            results['full_rejected_speech_preserved']=journal.get(item['id'])['text']==raw and not journal.pending()
            assembly=TurnAssembler();assembly.append('turn','Leva buka',False)
            turn=assembly.append('turn','Chrome Diska',True)
            results['speech_parts_join_before_execution']=turn['text']=='Leva buka Chrome Diska' and turn['final']
            from speech_turns import TurnWindow
            window=TurnWindow('x');window.voiced(0);window.submitted();window.recognized('x','buat web boleh menggunakan')
            results['unfinished_speech_waits']=window.finish(10) is None and window.finish(15)=='incomplete'
            results['manual_dictation_ignores_pause']=window.finish(60,manual=True) is None
            from conversation_frontend import conversation_request
            greeting=conversation_request(NoModel(),'hai apa kabar Arimo',route_spec('Dual GPU'),None,'ja',True)
            results['greeting_identity_is_leva']=greeting['kind']=='respond' and 'Arimo' not in greeting['text'] and 'Namamu Leva' in __import__('conversation_frontend').FRONT_SYSTEM
            greeting=conversation_request(NoModel(),'hai leva apa kabar',route_spec('Dual GPU'),None,'ja',True)
            results['named_greeting_skips_heavy_agent']=greeting['kind']=='respond' and greeting.get('frontend_bypassed') is True and bool(greeting['text'])
            from leva_persona import PersonaDelivery,GREETINGS
            from companion_lines import GREETINGS_BY_ROOM
            from presence_companion import CompanionPolicy,observed_apps,validate_settings
            persona=PersonaDelivery()
            results['persona_three_mode_banks']=all(len(GREETINGS)+len(GREETINGS_BY_ROOM[r])==26 and persona.greeting(room=r)['room']==r for r in ('assistant','chat','secret'))
            results['persona_app_claim_requires_pid']=observed_apps({'status':'done','windows':[{'pid':1,'title':'Discord tutorial'}]},lambda pid:'chrome.exe')=={'chrome':True}
            moments=[0.];idle=CompanionPolicy(clock=lambda:moments[0]);moments[0]=200;token=idle.reserve(True);idle.touch()
            results['persona_stale_idle_cancelled']=not idle.commit(token)
            results['persona_strict_settings']=validate_settings({'companion_idle':False,'companion_playful':True,'companion_idle_delay':'120'})['companion_idle'] is False

            from agent_contract import website_creation,correction_goal,development_evidence
            from assistant_tools import selected_skills
            results['website_tools_available']={'project_action','terminal','file_action'}<={s.name for s in selected_skills('buatkan website model pesawat free cam')}
            results['chat_only_code_respected']=not website_creation('buat website tanpa berkas')
            results['correction_preserves_goal']=correction_goal('eh bukan iPhone','buatkan website iPhone').endswith('eh bukan iPhone')
            results['website_cannot_complete_without_evidence']=development_evidence([])==(False,False)
            from second_brain import VaultIndex
            vault=Path(folder)/'vault';vault.mkdir();(vault/'Index.md').write_text('# Index\n[[Project]]\n',encoding='utf8')
            (vault/'Project.md').write_text('# Project\nFixture violet-194.\n',encoding='utf8')
            knowledge=VaultIndex(vault,Path(folder)/'knowledge-index')
            results['second_brain_read_search']=knowledge.search('violet')[0]['path']=='Project.md' and 'violet-194' in knowledge.read('Project.md')['excerpt']
            results['second_brain_wikilink']=knowledge.related('Index.md')['links'][0]['targets']==['Project.md']
            try:knowledge.read('../outside.md');results['second_brain_root_boundary']=False
            except ValueError:results['second_brain_root_boundary']=True
            from agent_contract import knowledge_question,briefing_request
            from scheduled_tasks import deferred_request
            spoken='Leva menurut catatan obsidian saya apa prioritas pengembangan untuk suara live eh bisakah sebutkan sebenernya'
            results['spoken_knowledge_scope']=knowledge_question(spoken) and {s.name for s in selected_skills(spoken)}=={'respond','ask_user','obsidian_action'}
            briefing='Buat briefing singkat: jam komputer saat ini, agenda lokal hari ini dan 3 headline berita terbaru dengan tautan sumber.'
            results['briefing_is_not_reminder']=briefing_request(briefing) and not deferred_request(briefing) and 'add_agenda' not in {s.name for s in selected_skills(briefing)}
            from web_bridge import WebBridge,ASSETS
            import urllib.request
            bridge=WebBridge(None,port=0)
            try:
                bridge.start();url=bridge.origin
                health=json.load(urllib.request.urlopen(url+'/health',timeout=3))
                data=urllib.request.urlopen(url,timeout=3).read()
                results['web_loopback_assets']=health.get('desktop_bridge') is True and b'app.js' in data and all((ASSETS/name).is_file() for name in ('index.html','app.js','graph.js','physics.js','style.css'))
                req=urllib.request.Request(url+'/api/session',data=b'',method='POST',headers={'Origin':url,'X-Leva-Bootstrap':bridge.bootstrap})
                auth=urllib.request.urlopen(req,timeout=3);cookie=auth.headers['Set-Cookie'].split(';')[0]
                payload=json.dumps({'id':'package-web-test','kind':'chat','value':'fixture only'}).encode()
                req=urllib.request.Request(url+'/api/commands',data=payload,headers={'Origin':url,'Cookie':cookie,'Content-Type':'application/json'})
                accepted=json.load(urllib.request.urlopen(req,timeout=3))
                results['web_authenticated_queue']=accepted['status']=='queued' and bridge.commands.get_nowait()['value']['text']=='fixture only'
                from file_workspace import FileWorkspace,source_redact
                from pypdf import PdfWriter
                fixture_pdf=Path(folder)/'fixture.pdf';writer=PdfWriter();writer.add_blank_page(width=100,height=100)
                with fixture_pdf.open('wb') as stream:writer.write(stream)
                file_reader=FileWorkspace();pdf_result=file_reader.run({'action':'read','path':str(fixture_pdf)},str(fixture_pdf))
                results['pdf_packaged_reader']=pdf_result['total_pages']==1 and pdf_result['ocr_required']
                results['arduino_credential_redaction']='fixture-secret' not in source_redact('#define FIREBASE_AUTH "fixture-secret"')
                from web_presence import WebPresence
                presence=WebPresence();presence.touch({'id':'fixture','name':'Android'},'Android',True)
                results['phone_presence_expires_on_revoke']=presence.active(lambda owner:False)==[]
                from feature_bridge import resource
                results['phone_mic_worker_assets']=resource('remote_speech_worker.py').is_file() and all((ASSETS/name).is_file() for name in ('mic.js','mic-worklet.js'))
                import wave,urllib.error
                sample=Path(folder)/'web-audio.wav'
                with wave.open(str(sample),'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\x01\x04'*4800)
                bridge.publish_audio(sample,{'pack':'packaged-fixture','language':'ja'})
                audio_url=url+bridge.snapshot()['audio']['clips'][0]['url']
                with urllib.request.urlopen(urllib.request.Request(audio_url,headers={'Cookie':cookie}),timeout=3) as response:
                    results['remote_packaged_audio_bytes']=response.headers['Content-Type']=='audio/wav' and response.read()==sample.read_bytes()
                try:urllib.request.urlopen(audio_url,timeout=3);results['remote_packaged_audio_auth']=False
                except urllib.error.HTTPError as error:results['remote_packaged_audio_auth']=error.code==401
                bridge.cancel_audio()
                try:urllib.request.urlopen(urllib.request.Request(audio_url,headers={'Cookie':cookie}),timeout=3);results['remote_packaged_audio_cancel']=False
                except urllib.error.HTTPError as error:results['remote_packaged_audio_cancel']=error.code==404
            finally:bridge.stop()
            from code_graph import CodeGraph
            from rea_analysis import scrub
            from workflow_skills import WorkflowSkills
            from assistant_tools import REGISTRY
            graph_fixture=Path(folder)/'code-fixture';(graph_fixture/'graphify-out').mkdir(parents=True)
            (graph_fixture/'graphify-out/graph.json').write_text(json.dumps({'nodes':[{'id':'a','label':'Entry'},{'id':'b','label':'Service'}],'links':[{'source':'a','target':'b','relation':'imports'}]}),encoding='utf8')
            graph_result=CodeGraph(graph_fixture).run({'action':'path','query':'a','target':'b'})
            results['code_graph_packaged']=graph_result['status']=='done' and len(graph_result['nodes'])==2
            results['capability_tools_packaged']={'code_graph','rea_analysis','capability_catalog'}.issubset(REGISTRY)
            results['capability_guides_packaged']={'graphify-code-investigation','rea-static-investigation','project-acceptance-evidence','source-linked-memory','briefing-with-evidence'}.issubset({r['id'] for r in WorkflowSkills().rows()})
            results['rea_redaction_packaged']=scrub({'nested':{'api_key':'fixture-only'}})['nested']['api_key']=='[REDACTED]'
            import zipfile
            from conversation_attachments import extract_upload
            document=io.BytesIO()
            with zipfile.ZipFile(document,'w') as archive:archive.writestr('word/document.xml','<document><p>Teori Graf</p></document>')
            results['office_attachment_packaged']='Teori Graf' in extract_upload('materi.docx',document.getvalue())['text']
            from profile_avatar import ProfileAvatar
            from PIL import Image
            photo=Image.new('RGB',(800,400),'red');photo.paste('blue',(400,0,800,400));photo_bytes=io.BytesIO();photo.save(photo_bytes,format='PNG')
            avatar_fixture=ProfileAvatar(Path(folder)/'crop-profile');avatar_fixture.save(photo_bytes.getvalue(),{'x':1,'y':.5,'zoom':1})
            results['avatar_position_packaged']=Image.open(io.BytesIO(avatar_fixture.read())).getpixel((256,256))[:3]==(0,0,255)
            from capability_catalog import catalog
            results['capability_sources_packaged']=len(catalog()['sources'])==6
            # Hidden real Tk widgets, fixture services: verify the packaged button
            # reaches readiness and shared-host dispatch without opening models/mic.
            import tkinter as tk
            import queue,time
            from unittest.mock import Mock,patch
            from gui import LevaWindow
            from mic_indicator import MicTelemetry
            m=LevaWindow.__new__(LevaWindow);m.root=tk.Tk();m.root.withdraw()
            m.preferences=Preferences(Path(folder)/'web-ui.db');m.preferences.set('web_port','0')
            m.mode=tk.StringVar(value='Tanpa AI');m.dual=tk.BooleanVar(value=False)
            m.spoken_replies=tk.BooleanVar(value=False);m.speech_language=tk.StringVar(value='Indonesia')
            m.status=tk.StringVar();m.activity=tk.StringVar();m.busy=False;m.closed=False;m.profile_rows=[]
            m.desktop=Mock(paused=False,sleeping=False);m.voice_window=m.voice_pack_window=m.duplex_window=None
            m.reply_voice=Mock(active=False);m.hardware=None;m.local_partial='';m.local_notice='Fixture'
            m.local_mic=Mock(active=False);m.local_mic.telemetry=MicTelemetry()
            m.chat=Mock();m.frontend=Mock();m.events=queue.Queue();m.generation=0;m.link_sequence=0
            m._layout()
            from types import SimpleNamespace
            m.hud.orb.drag_origin=(0,0,0.,0.);m.hud.orb.orbit(SimpleNamespace(x=100,y=40))
            results['native_orb_rotates']=abs(m.hud.orb.yaw-.8)<1e-9 and m.hud.orb.zoom==1
            m.add('Anda','Pemilik di kiri.');m.add('Leva','Leva di kanan.')
            results['native_chat_alignment']=m.history.tag_cget('assistant_align','justify')=='right' and m.history.tag_cget('user_align','justify')=='left'
            results['native_avatar_placeholder']=m.hud.profile_photo is not None
            results['conversation_tabs']=len(m.hud.tabs.tabs())==5 and set(m.room_views)=={'assistant','chat','secret','companion_avatar'}
            from companion_avatar import configure,AvatarDirector
            frame=m.room_frames['companion_avatar']
            results['companion_default_off']=not m.preferences.get('companion_enabled') and m.hud.tabs.tab(frame,'state')=='hidden'
            m._translation_pending=False
            configure(m,{'enabled':True,'label':'Fixture Avatar'})
            results['companion_native_opt_in']=m.hud.tabs.tab(frame,'state')=='normal' and 'Fixture Avatar' in m.hud.tabs.tab(frame,'text')
            configure(m,{'enabled':False})
            results['companion_no_auto_microphone']=m.local_mic.start.call_count==0
            results['companion_assets_packaged']=all((ASSETS/name).is_file() for name in ('avatar.js','avatar.css','vrm_avatar.js','avatar_dynamics.js','avatar-vendor.js','THIRD_PARTY_NOTICES.txt'))
            from avatar_validation import audit
            results['avatar_structure_audit_packaged']=callable(audit)
            from avatar_emotion import expression_for_reply
            results['avatar_context_calibration_packaged']=expression_for_reply('Permintaan belum berhasil.')=='thinking'
            results['avatar_performance_module_packaged']=(ASSETS/'avatar_performance.js').is_file()
            from llm_stream import AdaptiveSegmenter
            from process_trace import TraceHub
            from live_speech_pipeline import SpeechRuntimePool
            results['streaming_module_packaged']=bool(AdaptiveSegmenter().feed('Halo Leva.',final=True))
            results['private_process_trace_empty']=TraceHub('secret').snapshot('secret')==[]
            from trace_store import TraceStore
            journal=TraceStore(Path(folder)/'trace-package-check.sqlite3')
            recorded=TraceHub('assistant',store=journal);recorded.emit('run.started','request_host',status='started')
            journal.close();journal=TraceStore(Path(folder)/'trace-package-check.sqlite3');journal.ready.wait(2)
            results['trace_persistence_packaged']=journal.replay('assistant',recorded.run_id)['events']==recorded.snapshot('assistant')
            results['trace_private_replay_empty']=journal.replay('secret',recorded.run_id)['events']==[]
            journal.close()
            results['trace_web_modules_packaged']=all((ASSETS/name).is_file() for name in ('messages.js','trace.js'))
            pool=SpeechRuntimePool();pool.close();results['stream_runtime_pool_packaged']=pool.cached is None
            director=AvatarDirector();director.apply({'state':'speaking','mouth':.5});director.cancel()
            results['companion_stale_event_rejected']=not director.apply({'generation':0,'state':'speaking','mouth':1}) and director.snapshot()['mouth']==0
            results['workspace_resizable_split']=len(m.hud.assistant_split.panes())==2
            m.add('Ucapan · 日本語','こんにちは。')
            results['japanese_text_hidden']=m.history.tag_cget('spoken_translation','elide')=='1'
            m.hud.translation_visible.set(True)
            results['japanese_display_toggle']=m.history.tag_cget('spoken_translation','elide')=='0' and m.preferences.get('show_japanese') is True
            m.hud.translation_visible.set(False)
            from conversation_rooms import model_choices
            results['secret_large_model_label']='Tidak Direkomendasikan' in model_choices('secret')['saluki']
            from personal_models import PROFILES,model_path
            from chat_service import make_local
            results['personal_model_choices_all_rooms']=all(set(PROFILES)<=set(model_choices(room)) for room in ('assistant','chat','secret'))
            model_probe=make_local({'local_model':'qwen3_8b','local_mode':'gpu5070'})
            results['qwen3_non_thinking_profile']=model_probe.thinking_budget==0 and model_probe.model==model_path('qwen3_8b')
            results['personal_model_preference_validation']=all(__import__('preferences').validate_setting('secret_model',key) is None for key in PROFILES)
            results['room_uploaded_text']=__import__('conversation_attachments').extract_upload('note.txt',b'local note')['text']=='local note'
            from speech_pipeline_window import SpeechPipelineWindow
            from speech_configuration import configuration_snapshot
            pipeline_panel=SpeechPipelineWindow(m);pipeline_panel.window.withdraw()
            results['independent_model_controls']=set(('asr_model','asr_gpu','agent_local_model','agent_provider')).issubset(pipeline_panel.values)
            results['asr_default_5070']=m.preferences.get('asr_gpu')=='rtx5070'
            results['independent_route_snapshot']=configuration_snapshot(m.preferences,route_spec('RTX 4050'))['effective']=={'asr_gpu':'rtx5070','agent_mode':'gpu5070'}
            pipeline_panel.window.destroy()
            m.hud.full_visual('neural');window=m.hud.visual_window;window.withdraw()
            results['native_neural_fullscreen']=bool(window.attributes('-fullscreen'))
            m.root.tk.call(window.protocol('WM_DELETE_WINDOW'))
            previous_canvas=m.hud.canvas;m.hud.full_visual('knowledge');window=m.hud.visual_window;window.withdraw()
            results['native_knowledge_fullscreen']=m.hud.canvas is not previous_canvas
            m.root.tk.call(window.protocol('WM_DELETE_WINDOW'))
            results['native_graph_restore']=m.hud.canvas is previous_canvas
            def children(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from children(child)
            button=next(w for w in children(m.root) if isinstance(w,tk.Button) and w.cget('text')=='Versi Web')
            try:
                with patch('webbrowser.open',return_value=True) as opened:
                    button.invoke();_,event=m.events.get(timeout=5);m._web_host.ready(event)
                    first=m._web_host.bridge.server
                    button.invoke();_,event=m.events.get(timeout=5);m._web_host.ready(event)
                    results['web_packaged_tk_button']=opened.call_count==2 and first is m._web_host.bridge.server and event.get('_web_ready','').startswith(m._web_host.bridge.origin)
                m.send=Mock();m._web_host.last_update=time.monotonic()
                m._web_host.bridge.submit({'id':'frozen-ui-message','kind':'chat','value':'fixture dispatch only'})
                m._web_host.poll();results['web_packaged_shared_dispatch']=m.send.call_args.args==('fixture dispatch only',) and m.send.call_args.kwargs.get('workspace')=='assistant'

                from remote_window import RemoteWindow
                m.preferences.set_many({'web_remote_enabled':True,'web_remote_origin':'https://fixture.example.ts.net'})
                m._web_host.bridge.remote='https://fixture.example.ts.net'
                with patch('remote_window.RemoteGateway') as gateway:
                    gateway.return_value.status.return_value={'ready':False,'detail':'Fixture only; no Tailscale operation.'}
                    remote_panel=RemoteWindow(m);remote_panel.window.withdraw();remote_panel.pair()
                    pairing_code=remote_panel.code.get()
                    req=urllib.request.Request(m._web_host.bridge.origin+'/api/pair',data=json.dumps({'code':pairing_code,'name':'Frozen Android fixture'}).encode(),headers={'Origin':m._web_host.bridge.origin,'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=3) as response:device_token=response.headers['Set-Cookie'].split(';')[0].split('=',1)[1]
                    remote_panel.devices();device_id=m._web_host.bridge.store.authenticate(device_token)['id']
                    results['remote_packaged_pairing_panel']=len(pairing_code)==8 and device_id in remote_panel.rows.get_children()
                    remote_panel.rows.selection_set(device_id);remote_panel.revoke()
                    results['remote_packaged_device_revocation']=m._web_host.bridge.store.authenticate(device_token) is None
                    remote_panel.window.destroy()
                results['remote_mobile_assets']=all((ASSETS/name).is_file() for name in ('mobile.js','audio.js','manifest.webmanifest','icon.svg'))
                results['workspace_layout_assets']=all((ASSETS/name).is_file() for name in ('workspace.js','workspace.css'))
                results['personal_profile_external_worker_asset']=(Path(getattr(sys,'_MEIPASS',ROOT/'app'))/'assistant_runtime/personal_models.py').is_file() if getattr(sys,'frozen',False) else (ROOT/'app/personal_models.py').is_file()
                from settings_window import SettingsWindow
                m.desktop.profiles={};m.open_remote=Mock()
                with patch.object(SettingsWindow,'refresh'),patch.object(SettingsWindow,'refresh_status'):
                    settings_panel=SettingsWindow(m);settings_panel.window.withdraw()
                    remote_button=next(w for w in children(settings_panel.window) if isinstance(w,tk.Button) and w.cget('text')=='Hubungkan Android')
                    remote_button.invoke();results['remote_settings_entry_button']=m.open_remote.call_count==1
                    settings_panel.window.destroy()
                m._web_host.complete({'needs_input':True,'reply':'Fixture needs input','task_id':'a'*12})
                results['remote_actual_completion_receipt']=m._web_host.bridge.store.recent()[0]['status']=='needs_input'

            finally:
                if getattr(m,'_web_host',None):m._web_host.stop()
                m.rooms.close();m.preferences.close();m.root.destroy()
        sys.stdout.write(json.dumps(results))
        sys.stdout.flush()
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, "Local\\LevaDesktopPreview")
    if ctypes.get_last_error() == 183:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user.FindWindowW.restype = wintypes.HWND
        window = user.FindWindowW(None, "Leva — Asisten Desktop")
        if window:
            user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user.SetForegroundWindow.argtypes = [wintypes.HWND]
            user.ShowWindow(window, 9)
            user.SetForegroundWindow(window)
        return
    try:
        DATA.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # Preferences show an explicit session-only warning if D is unavailable.
    from gui import LevaWindow
    LevaWindow().run()


if __name__ == "__main__":
    main()
