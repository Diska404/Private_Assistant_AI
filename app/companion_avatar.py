"""Asset-independent avatar contract. No model, microphone, network or executor."""
import math
import secrets
import time

ROOM='companion_avatar'
STATES={'idle','listening','thinking','speaking','interrupted','sleeping','error'}
EXPRESSIONS={'neutral','happy','curious','thinking','shy','surprised','sad','soft_smile','laugh','confused','embarrassed','playful','angry','sleepy','attentive','excited'}

class AvatarDirector:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.session=secrets.token_hex(8);self.generation=0;self.seq=0
        self.state='idle';self.expression='neutral';self.mouth=0.;self.until=0.;self.last_expression=-10.
    def cancel(self):
        self.generation+=1;self.state='interrupted';self.expression='neutral';self.mouth=0.;self.until=0.;self.seq+=1
        return self.snapshot()
    def apply(self,event):
        if not isinstance(event,dict) or set(event)-{'generation','state','expression','intensity','duration_ms','mouth'}:raise ValueError('invalid_avatar_event')
        if event.get('generation',self.generation)!=self.generation:return False
        if 'state' in event and event['state'] not in STATES:raise ValueError('invalid_avatar_state')
        if 'expression' in event and event['expression'] not in EXPRESSIONS:raise ValueError('invalid_avatar_expression')
        for key in ('mouth','intensity'):
            if key in event and (type(event[key]) not in (int,float) or not math.isfinite(event[key]) or not 0<=event[key]<=1):raise ValueError('invalid_avatar_level')
        duration=event.get('duration_ms',1200)
        if type(duration) is not int or not 100<=duration<=5000:raise ValueError('invalid_avatar_duration')
        if 'state' in event:self.state=event['state']
        if 'expression' in event and self.clock()-self.last_expression>=.2:
            self.expression=event['expression'];self.last_expression=self.clock();self.until=self.clock()+duration/1000
        self.mouth=event.get('mouth',self.mouth) if self.state=='speaking' else 0.
        self.seq+=1;return True
    def snapshot(self):
        if self.until and self.clock()>=self.until:self.expression='neutral';self.until=0
        return {'schema_version':1,'session_id':self.session,'generation_id':self.generation,'seq':self.seq,
            'state':self.state,'expression':self.expression,'mouth':self.mouth if self.state=='speaking' else 0.,
            'provider':'placeholder','asset_id':'leva_procedural_placeholder_v1','avatar_final':False}

def enabled(preferences):return preferences.get('companion_enabled') is True

def validate_settings(value):
    if not isinstance(value,dict) or not value or set(value)-{'enabled','label','experimental_models','asset','renderer_gpu','realtime_speech','native_stream'}:raise ValueError('invalid_companion_settings')
    from preferences import validate_setting
    keys={'enabled':'companion_enabled','label':'companion_label','experimental_models':'experimental_models_enabled','asset':'companion_avatar_asset','renderer_gpu':'companion_renderer_gpu','realtime_speech':'realtime_speech','native_stream':'native_voice_stream'}
    for key,val in value.items():validate_setting(keys[key],val)
    if value.get('asset') not in (None,'placeholder'):__import__('avatar_assets').manifest(value['asset'])
    return dict(value)

def configure(main,value):
    value=validate_settings(value)
    if main.busy or getattr(main,'_translation_pending',False):raise ValueError('Tunggu jawaban selesai atau hentikan percakapan terlebih dahulu.')
    if any(k in value for k in ('realtime_speech','native_stream')):
        main.stop_reply_voice();main.cancel_inference()
    keys={'enabled':'companion_enabled','label':'companion_label','experimental_models':'experimental_models_enabled','asset':'companion_avatar_asset','renderer_gpu':'companion_renderer_gpu','realtime_speech':'realtime_speech','native_stream':'native_voice_stream'}
    main.preferences.set_many({keys[k]:v for k,v in value.items()})
    frame=getattr(main,'room_frames',{}).get(ROOM)
    if frame:
        if enabled(main.preferences):
            main.hud.tabs.insert(3,frame,text='  '+main.preferences.get('companion_label')+'  ')
            main.hud.tabs.tab(frame,state='normal')
        else:
            if getattr(main,'workspace','assistant')==ROOM:
                from room_ui import switch_workspace
                switch_workspace(main,'assistant')
            main.hud.tabs.hide(frame)
    if 'experimental_models' in value:
        from conversation_rooms import model_choices
        for room,(model,gpu,choices) in getattr(main,'room_controls',{}).items():
            fresh=model_choices(room,include_trials=value['experimental_models'] is True)
            selected=main.preferences.get(room+'_model')
            if selected not in fresh:
                from model_registry import TRIALS
                if selected in TRIALS:fresh[selected]=TRIALS[selected]['label']+' · aktifkan model eksperimen untuk memakai'
            choices.clear();choices.update(fresh)
            if selected in choices:model.set(choices[selected])
            picker=getattr(main,'room_model_pickers',{}).get(room)
            if picker:picker.configure(values=list(choices.values()))
    return {'enabled':enabled(main.preferences),'display_name':main.preferences.get('companion_label')}

def interrupt(main):
    if getattr(main,'workspace','assistant')!=ROOM:raise ValueError('companion_not_active')
    main.generation+=1;main.stop_reply_voice();main.cancel_inference();main.cancel_voice_queue()
    main.companion_mic_consent=False;main.local_mic.stop();main.set_busy(False)
    main._companion_interrupted_until=time.monotonic()+1.5
    director=getattr(main,'avatar_director',None)
    if isinstance(director,AvatarDirector):director.cancel()

def presentation(main,phase,output_level):
    director=getattr(main,'avatar_director',None)
    if not isinstance(director,AvatarDirector):director=main.avatar_director=AvatarDirector()
    generation=getattr(main,'generation',0)
    if isinstance(generation,int) and generation!=director.generation:
        director.generation=generation;director.mouth=0.;director.expression='neutral'
    state={'paused':'sleeping','tool':'thinking','memory':'thinking'}.get(phase,phase)
    if state not in STATES:state='idle'
    until=getattr(main,'_companion_interrupted_until',0)
    if getattr(main,'workspace',None)==ROOM and state=='idle' and isinstance(until,(int,float)) and time.monotonic()<until:state='interrupted'
    director.apply({'state':state,'mouth':float(max(0,min(1,output_level)))})
    hint=getattr(main,'_avatar_reply_emotion',None)
    if getattr(main,'workspace',None)==ROOM and isinstance(hint,dict) and hint.get('generation')==generation:
        if getattr(main,'_avatar_emotion_seen',None) is not hint:
            director.apply({'expression':hint['expression'],'duration_ms':3500});main._avatar_emotion_seen=hint
    return {**director.snapshot(),'enabled':enabled(main.preferences),'display_name':main.preferences.get('companion_label'),
        'mic_authorized':getattr(main,'companion_mic_consent',False) is True,'tools':'none',
        'history':'session_only','cloud':'disabled','asset':main.preferences.get('companion_avatar_asset'),
        'asset_choices':__import__('avatar_assets').choices(),'renderer_gpu':main.preferences.get('companion_renderer_gpu'),
        'realtime_speech':main.preferences.get('realtime_speech'),'native_stream':main.preferences.get('native_voice_stream'),
        'providers':{'placeholder':'available','vrm':'available','live2d':'not_configured'}}
