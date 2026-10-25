"""UI/session integration for content streaming and optional speech overlap."""
import time
from process_trace import TraceHub

def voice_active(main):
    from live_speech_pipeline import LiveSpeechPipeline
    value=getattr(main,'live_speech',None)
    return isinstance(value,LiveSpeechPipeline) and value.active

def output_service(main):
    return main.live_speech.playback if voice_active(main) else main.reply_voice.service

def begin(main,room,model,gpu,language,want_voice):
    generation=main.generation
    capture={'generation':generation,'room':room,'text':'','pipeline':None,'model':model,'gpu':gpu,'language':language,'voice':want_voice}
    main._stream_capture=capture;main._web_stream={'generation':generation,'workspace':room,'text':'','active':False}
    from trace_store import start_trace
    start_trace(main,room)
    return capture

def prepare_voice(main,capture):
    if not capture['voice'] or main.preferences.get('realtime_speech') is not True:return
    pack=main.preferences.get('target_voice_pack')
    if not pack.startswith('higgs_'):return
    from pipeline_routing import route_spec
    from speech_resources import pipeline_gpu,gpu_rows
    route=route_spec(main.mode.get(),main.dual.get())
    if route['gpu']=='none':return
    tts=pipeline_gpu(route,'tts',main.preferences.get('tts_gpu'))
    gpu=capture['gpu'];model=capture['model'];generation=capture['generation']
    from live_speech_pipeline import LiveSpeechPipeline,SpeechRuntimePool
    pool=getattr(main,'_speech_runtime_pool',None)
    if not isinstance(pool,SpeechRuntimePool):pool=main._speech_runtime_pool=SpeechRuntimePool()
    rows=gpu_rows();selected=next((r for r in rows if ('RTX 5070' if tts=='rtx5070' else 'RTX 4050') in r['name']),None)
    cached=pool.cached is not None and pool.cached.worker.active and pool.cached.actual_pack==pack
    reserve=3500 if model in ('qwen4b','hauhau_qwen35_4b') else 7500
    same=(gpu=='gpu5070' and tts=='rtx5070') or (gpu=='gpu4050' and tts=='rtx4050') or gpu=='dual'
    need=(0 if cached else 6000)+(reserve if same else 0)
    if tts!='rtx5070' or not selected or selected['free_mib']<need:
        main.process_trace.emit('voice.deferred','speech_resource_policy',status='waiting');return
    def valid():return generation==main.generation and not main.closed and getattr(main,'_muted_voice_generation',None)!=generation
    def translate(text):
        service=main.rooms.service(capture['room'])
        # Reuse the same model after its current generation; never deadlock the
        # SSE reader on a phrase queue while this request lock is held.
        deadline=time.monotonic()+90
        while service.request_lock.locked() and valid() and time.monotonic()<deadline:time.sleep(.02)
        if not valid():raise ValueError('speech_cancelled')
        if time.monotonic()>=deadline:raise TimeoutError('translator_wait_timeout')
        result=service.ask(text,'local',gpu,local_model=model,acceleration='plain',keep_warm=True,purpose='translate')
        if not valid() or result.get('cancelled'):raise ValueError('speech_cancelled')
        return result['response']
    host=getattr(main,'_web_host',None)
    pipeline=LiveSpeechPipeline(pack,capture['language'],'personal' if capture['room'] in ('secret','companion_avatar') else 'assistant',tts,
        translate=translate if capture['language']=='ja' else None,authorized=valid,
        audio_callback=host.bridge.publish_audio if host else None,reference_callback=main.local_mic.reference,
        output_device=main.preferences.get('output_device_name'),output_hostapi=main.preferences.get('output_hostapi'),
        native_stream=main.preferences.get('native_voice_stream') is True,pool=pool if main.preferences.get('keep_models_warm') else None)
    if not valid():pipeline.cancel();return
    capture['pipeline']=main.live_speech=pipeline

def receive(main,capture,event):
    if capture['generation']!=main.generation:return
    if event['kind']=='model_event':
        metrics={k:event[k] for k in ('load_seconds','ttft_ms','total_ms') if event.get(k) is not None}
        usage=event.get('usage',{});metrics.update({k:usage[k] for k in ('prompt_tokens','completion_tokens') if k in usage})
        speed=event.get('timings',{}).get('predicted_per_second')
        if speed is not None:metrics['tokens_per_second']=speed
        main.process_trace.emit(event['event_type'],'local_model_backend',metrics)
        return
    delta=event.get('text','');capture['text']+=delta
    if len(capture['text'])>24000:raise ValueError('stream_text_limit')
    pipeline=capture['pipeline']
    if pipeline:pipeline.feed(delta)
    main.events.put((capture['generation'],{'_stream_text':delta,'_stream_room':capture['room']}))

def finish(main,capture,reply):
    pipeline=capture['pipeline']
    if pipeline:
        if not capture['text']:pipeline.feed(reply)
        elif capture['text'].strip()!=reply.strip():pipeline.cancel();return False
        pipeline.feed('',final=True)
    return pipeline is not None

def display(main,result):
    room=result['_stream_room']
    if room!=main.workspace:return
    value=main._web_stream;value['text']=(value['text']+result['_stream_text'])[:24000];value['active']=True
    view=main.history;view.configure(state='normal')
    if not getattr(main,'_stream_mark',False):
        view.mark_set('stream_start','end-1c');view.mark_gravity('stream_start','left');main._stream_mark=True
        view.insert('end','Leva\n',('assistant_align',))
        view.mark_set('stream_end','end-1c');view.mark_gravity('stream_end','left')
    follow=view.yview()[1]>.97
    index=view.index('stream_end');delta=result['_stream_text'];view.insert(index,delta,('assistant_align',));view.mark_set('stream_end',index+'+'+str(len(delta))+'c');view.configure(state='disabled')
    if follow:view.see('end')

def clear_display(main):
    value=getattr(main,'_web_stream',None)
    if isinstance(value,dict):value['active']=False;value['text']=''
    if getattr(main,'_stream_mark',False):
        view=main.history;view.configure(state='normal');view.delete('stream_start','stream_end');view.mark_unset('stream_start','stream_end');view.configure(state='disabled');main._stream_mark=False
