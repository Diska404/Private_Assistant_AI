"""Local microphone -> segmented ASR -> wake/commands. No recording or cloud audio."""
import base64
import contextlib
import json
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

# Embedded Python's _pth isolation omits the script directory. Both source and
# packaged assistant_runtime workers must resolve their own sibling modules.
sys.path.insert(0,str(Path(__file__).resolve().parent))
from local_audio_core import WakePolicy,Segmenter,EchoGuard,self_transcript
from speech_turns import TurnAssembler,TurnWindow

def run(request,emit,capture_factory=None):
    import numpy as np
    if capture_factory is None:
        from mic_capture import CaptureProcess
        capture_factory=CaptureProcess
    models=Path('D:/AI/AI Lokal Asisten/AI Models')
    modern=request.get('asr_model','whisper_cpu')!='whisper_cpu'
    if modern:
        from speech_asr import SpeechASR,normalized_transcript
        emit({'kind':'local_status','state':'loading','text':'Memuat ASR khusus · '+request['asr_model']+'…'})
        recognizer=SpeechASR(request['asr_model'],request.get('asr_gpu','auto'))
        backend=request['asr_model']+' · '+recognizer.gpu['name']
    else:
        from faster_whisper import WhisperModel
        emit({'kind':'local_status','state':'loading','text':'Memuat pendengar kompatibilitas · Whisper CPU…'})
        tiny=WhisperModel(str(models/'faster-whisper-tiny'),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
        small=WhisperModel(str(models/'faster-whisper-small'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
        backend='Whisper tiny/small · CPU'
    audio=queue.Queue(maxsize=1500);meter_audio=queue.Queue(maxsize=10);controls=queue.Queue(maxsize=100);stop=threading.Event()
    jobs=queue.Queue(maxsize=16);failures=queue.Queue();parent_drops=0;pending_loss=False
    hold_asr=threading.Event()
    telemetry={'phase':'listening','threshold':.009,'noise':.001,'voiced':False,'echo_rejected':False,'awake':False}
    wake=WakePolicy(request.get('wake_word','leva'),followup_seconds=120);segmenter=Segmenter(silence_frames=55);echo=EchoGuard()
    window=TurnWindow(uuid.uuid4().hex)
    def read():
        try:
            for line in sys.stdin:
                try:controls.put_nowait(json.loads(line))
                except (ValueError,queue.Full):pass
        finally:stop.set()
    threading.Thread(target=read,daemon=True).start()
    def callback(indata,frames,stamp,status):
        nonlocal parent_drops,pending_loss
        pcm=bytes(indata)
        captured_at=time.monotonic() if stamp is None else stamp
        try:
            audio.put_nowait((pcm,captured_at,str(status) if status else 'parent_queue_loss' if pending_loss else ''))
            pending_loss=False
        except queue.Full:parent_drops+=frames;pending_loss=True
        try:meter_audio.put_nowait(pcm)
        except queue.Full:
            try:meter_audio.get_nowait();meter_audio.put_nowait(pcm)
            except queue.Empty:pass
    def meters():
        from mic_indicator import pcm_measurements
        while not stop.wait(.1):
            frames=[]
            while True:
                try:frames.append(meter_audio.get_nowait())
                except queue.Empty:break
            if frames:
                level=pcm_measurements(b''.join(frames))
                emit({'kind':'local_meter','input':round(min(1,level['rms']*8),4),
                      'state':'listening',**level,**telemetry})
    spoken_text='';assembler=TurnAssembler()
    def transcribe_jobs():
        nonlocal recognizer
        try:
            while not stop.is_set():
                if hold_asr.is_set():
                    if modern and recognizer is not None:
                        recognizer=None
                        import gc,torch
                        gc.collect()
                        for index in range(torch.cuda.device_count()):
                            with torch.cuda.device(index):torch.cuda.empty_cache()
                    telemetry['phase']='buffering'
                    emit({'kind':'local_asr_held','text':'Mikrofon tetap merekam dalam RAM · ASR menunggu GPU.'})
                    while hold_asr.is_set() and not stop.wait(.1):pass
                    if stop.is_set():break
                    if modern:recognizer=SpeechASR(request['asr_model'],request.get('asr_gpu','auto'))
                    telemetry['phase']='listening'
                    emit({'kind':'local_asr_resumed','text':'ASR aktif kembali · memproses ucapan yang mengantre.'})
                try:ident,complete,final,incomplete,captured_at,manual=jobs.get(timeout=.1)
                except queue.Empty:continue
                began=time.monotonic();text='';execution={}
                telemetry['phase']='transcribing';emit({'kind':'local_asr_state','phase':'transcribing'})
                if complete:
                    samples=np.frombuffer(complete,dtype=np.int16).astype(np.float32)/32768
                    if modern:
                        transcript=recognizer.transcribe(samples,request.get('asr_language','id'),'Leva adalah nama asisten. Diska, Chrome, ChatGPT, EdLink, ComfyUI, Fooocus, matematika diskrit')
                        text=normalized_transcript(transcript['text']);execution=transcript['module_forward_cuda_ms']
                    else:
                        # One recognizer for the entire turn; tiny wake detection
                        # used to discard names before small could hear them.
                        segments,_=small.transcribe(samples,language='id',beam_size=1,condition_on_previous_text=False,vad_filter=True,
                            initial_prompt='Leva adalah nama asisten pribadi. Leva, buka Chrome.')
                        text=' '.join(s.text.strip() for s in segments).strip()
                turn=assembler.append(ident,text,final,(time.monotonic()-began)*1000,incomplete)
                if not final:
                    window.recognized(ident,turn['text'])
                    emit({'kind':'local_heard_partial',**turn,'reason':'collecting'})
                    telemetry['phase']='collecting';emit({'kind':'local_asr_state','phase':'collecting'})
                    continue
                text=turn['text'];accepted={'accepted':False,'wake':False,'command':''}
                if turn['incomplete']:reason='incomplete'
                elif not text:reason='empty'
                elif not manual and self_transcript(text,spoken_text,time.monotonic()-echo.last_reference) and echo.last_metrics.get('echo_rejected',False):reason='echo'
                else:
                    # A queued follow-up belongs to its capture time, not the
                    # possibly much later completion of model inference.
                    if manual:wake.arm(now=captured_at)
                    accepted=wake.accept(text,now=captured_at)
                    if accepted['accepted']:wake.until=max(wake.until,time.monotonic()+wake.followup_seconds)
                    reason='wake' if accepted['wake'] else 'followup' if accepted['accepted'] else 'awaiting_wake'
                emit({'kind':'local_diagnostic','asr_ms':turn['asr_ms'],'heard_characters':len(text),
                      'wake_detected':accepted['wake'],'accepted':accepted['accepted'],'module_forward_cuda_ms':execution})
                emit({'kind':'local_heard',**turn,'reason':reason,'accepted':accepted['accepted'],
                      'command':accepted['command'],'backend':backend,'wake':accepted['wake']})
                # Compatibility event; the GUI dispatches the journalled final
                # local_heard event once, never this second copy.
                if accepted['accepted']:
                    emit({'kind':'local_transcript' if accepted['command'] else 'local_wake','text':accepted['command'],
                          'turn_id':ident,'raw_transcript':text,'journalled':True,'backend':backend,
                          'asr_ms':turn['asr_ms'],'wake':accepted['wake']})
                telemetry['phase']='transcribing' if not jobs.empty() else 'listening'
                emit({'kind':'local_asr_state','phase':telemetry['phase']})
        except Exception as error:
            failures.put(error);stop.set()
    emit({'kind':'local_phase','phase':'capture_open'})
    with capture_factory(request,callback) as capture:
        device_name=capture.info['device_name']
        emit({'kind':'local_status','state':'listening','text':backend+' · ucapkan Leva','microphone_open':True,
              'device_name':device_name,'capture_isolated':bool(getattr(capture,'process',None)),'capture_pid':capture.health.get('capture_pid'),
              'gpu_name':recognizer.gpu['name'] if modern else 'CPU',
              'gpu_devices':recognizer.devices if modern else [],
              'parameter_counts':recognizer.parameter_counts if modern else {}})
        meter_thread=threading.Thread(target=meters,daemon=True);meter_thread.start()
        asr_thread=threading.Thread(target=transcribe_jobs,daemon=True);asr_thread.start()
        incomplete=False;manual=False;commit_remaining=None;turn_bytes=0;manual_frames=[];manual_signal=0
        last_loss=-1e9;last_packet=None;warned=False
        def part(pcm):
            nonlocal turn_bytes
            if not pcm:return
            window.submitted();turn_bytes+=len(pcm)
            try:jobs.put_nowait((window.ident,pcm,False,incomplete,window.started or time.monotonic(),manual))
            except queue.Full:raise BufferError('speech_transcription_backlog')
        def commit(broken=False):
            nonlocal window,incomplete,manual,commit_remaining,turn_bytes,manual_frames,manual_signal,warned
            if manual:
                part(b''.join(manual_frames));manual_frames=[]
                broken=broken or manual_signal<10
            part(segmenter.flush())
            if window.parts:
                try:jobs.put_nowait((window.ident,b'',True,incomplete or broken,window.started or time.monotonic(),manual))
                except queue.Full:raise BufferError('speech_transcription_backlog')
            if manual:emit({'kind':'local_dictation','recording':False,'text':'Perintah panjang selesai ditangkap · menunggu pengenalan lengkap.' if manual_signal>=10 else 'Sinyal ucapan terlalu rendah · catatan tidak dijalankan otomatis.'})
            window=TurnWindow(uuid.uuid4().hex);incomplete=False;manual=False;commit_remaining=None;turn_bytes=0;manual_signal=0
            warned=False
        while not stop.is_set():
            capture.check()
            telemetry['capture_health']={**capture.health,'parent_queue_dropped_frames':parent_drops,'parent_queued_frames':audio.qsize()}
            while not controls.empty():
                item=controls.get_nowait()
                if item.get('kind')=='reference':echo.offer(base64.b64decode(item['pcm']));spoken_text=item.get('spoken_text','')
                elif item.get('kind')=='reference_reset':echo.reset()
                elif item.get('kind')=='sleep':wake.until=0
                elif item.get('kind')=='arm':
                    wake.arm(45)
                    emit({'kind':'local_armed','text':'Perintah suara aktif 45 detik · tidak perlu menyebut Leva.'})
                elif item.get('kind')=='keepalive':wake.arm()
                elif item.get('kind')=='dictation_start':
                    if window.parts or segmenter.frames:commit(True)
                    manual=True;wake.arm();window.started=time.monotonic()
                    emit({'kind':'local_dictation','recording':True,'text':'Perintah panjang aktif · tekan Selesai & kirim setelah seluruh arahan selesai.'})
                elif item.get('kind')=='dictation_commit':commit_remaining=audio.qsize()
                elif item.get('kind')=='hold_asr':hold_asr.set()
                elif item.get('kind')=='resume_asr':hold_asr.clear()
                elif item.get('kind')=='stop':stop.set()
            if commit_remaining==0:commit()
            elif window.started is not None and time.monotonic()-window.started>=120:
                emit({'kind':'local_capture_warning','text':'Batas satu ucapan dua menit tercapai; catatan disimpan tanpa eksekusi otomatis.'});commit(True)
            else:
                current=not getattr(capture,'process',None) or last_packet is None or time.monotonic()-last_packet<.5
                ending=window.finish(time.monotonic(),manual) if audio.empty() and current else None
                if ending:
                    if ending=='incomplete':emit({'kind':'local_capture_warning','text':'Kalimat berakhir dengan kata penghubung; ucapan dicatat tanpa eksekusi. Lanjutkan melalui Catatan suara atau Rekam perintah panjang.'})
                    commit(ending=='incomplete')
            try:pcm,captured_at,loss=audio.get(timeout=.1)
            except queue.Empty:continue
            last_packet=captured_at
            if loss:
                last_loss=captured_at
                if manual or window.last_voice is not None and captured_at-window.last_voice<2:incomplete=True
            rms,is_echo=echo.classify(pcm)
            pcm=echo.cleaned if echo.cleaned is not None else pcm
            telemetry.update(echo.last_metrics)
            speaking=time.monotonic()-echo.last_reference<.4
            if manual:
                # Explicit dictation retains every frame between the buttons,
                # including quiet word onsets and pauses. A minimum signal gate
                # prevents a silent recording from becoming a hallucinated action.
                manual_frames.append(pcm)
                if not is_echo and rms>.002:
                    if captured_at-last_loss<.25:incomplete=True
                    manual_signal+=1;window.voiced(captured_at)
                if len(manual_frames)>=600:part(b''.join(manual_frames));manual_frames=[]
                telemetry.update(threshold=.002,voiced=rms>.002,awake=True,awake_remaining=max(0,round(wake.until-time.monotonic())))
                if commit_remaining is not None:commit_remaining=max(0,commit_remaining-1)
                if incomplete and not warned:
                    emit({'kind':'local_capture_warning','text':'Ada kehilangan audio pada ucapan aktif; teks tetap dicatat untuk diperiksa sebelum dijalankan.'});warned=True
                continue
            complete,interrupted,voiced=segmenter.push(pcm,rms,is_echo,speaking,wake.active())
            if voiced:
                if captured_at-last_loss<.25:incomplete=True
                window.voiced(captured_at)
            if incomplete and not warned:
                emit({'kind':'local_capture_warning','text':'Ada kehilangan audio pada ucapan aktif; teks tetap dicatat untuk diperiksa sebelum dijalankan.'});warned=True
            telemetry.update(threshold=segmenter.threshold,noise=segmenter.noise,voiced=voiced,echo_rejected=is_echo,awake=wake.active())
            telemetry['awake_remaining']=max(0,round(wake.until-time.monotonic()))
            if interrupted:emit({'kind':'local_barge_in','text':'Ucapan pengguna menyela keluaran suara.'})
            if complete is not None:
                part(complete)
            if commit_remaining is not None:commit_remaining=max(0,commit_remaining-1)
        stop.set();meter_thread.join(timeout=.4)
        if not failures.empty():raise failures.get_nowait()

if __name__=='__main__':
    protocol=sys.stdout
    import os
    diagnostic={'pid':os.getpid(),'microphone_open':False,'phase':'bootstrap'};last_diagnostic=0
    emit_lock=threading.RLock()
    def emit(event):
        with emit_lock:_emit(event)
    def _emit(event):
        global last_diagnostic
        if event.get('kind')=='local_status':diagnostic['phase']='asr_load' if event.get('state')=='loading' else 'capture'
        elif event.get('kind')=='local_asr_state':diagnostic['phase']=event['phase']
        elif event.get('kind')=='local_phase':diagnostic['phase']=event['phase']
        protocol.write(json.dumps(event,ensure_ascii=True)+'\n');protocol.flush()
        if os.environ.get('LEVA_MIC_DIAGNOSTICS')=='0':return
        kind=event.get('kind');now=time.time()
        if kind in ('local_status','local_diagnostic','error','stopped') or (kind=='local_meter' and now-last_diagnostic>=2):
            try:
                diagnostic.update({k:v for k,v in event.items() if k in ('state','microphone_open','gpu_name','gpu_devices','parameter_counts','module_forward_cuda_ms','asr_ms','heard_characters','wake_detected','accepted','input','awake','echo_rejected','code','message','phase','winerror','errno','retryable','capture_health','capture_pid','capture_isolated')})
                diagnostic.update(last_event=kind,updated_at=now)
                folder=Path('D:/AI/AI Lokal Asisten/Leva/status');folder.mkdir(parents=True,exist_ok=True)
                temporary=folder/('local-microphone-'+str(os.getpid())+'.tmp')
                temporary.write_text(json.dumps(diagnostic),encoding='utf-8');temporary.replace(folder/'local-microphone.json')
                last_diagnostic=now
            except OSError:pass
    try:
        request=json.loads(sys.stdin.readline())
        with contextlib.redirect_stdout(sys.stderr):run(request,emit)
    except Exception as error:
        from mic_recovery import failure_details
        event=failure_details(error,diagnostic['phase'])
        if os.environ.get('LEVA_MIC_DIAGNOSTICS')!='0':
            try:
                import traceback
                folder=Path('D:/AI/AI Lokal Asisten/Leva/status');folder.mkdir(parents=True,exist_ok=True)
                (folder/'local-microphone-error.json').write_text(json.dumps({**event,'pid':os.getpid(),'time':time.time(),'traceback':traceback.format_exc()},indent=2),encoding='utf8')
            except OSError:pass
        emit(event)
    finally:emit({'kind':'stopped','microphone_open':False})
