"""Bounded companion presence; suggestions only, no autonomous PC actions or cold LLM/TTS."""
from collections import deque
import random
import re
import threading
import time

KEYS=('companion_idle','companion_playful','companion_idle_delay')

def validate_settings(value):
    if not isinstance(value,dict) or set(value)!=set(KEYS):raise ValueError('invalid_companion_settings')
    if any(type(value[k]) is not bool for k in KEYS[:2]) or value[KEYS[2]] not in ('120','300','600'):
        raise ValueError('invalid_companion_settings')
    return dict(value)

def settings(main):
    from preferences import DEFAULTS
    rows={}
    for key in KEYS:
        try:rows[key]=main.preferences.get(key)
        except (AttributeError,KeyError,ValueError):rows[key]=DEFAULTS[key]
    try:return validate_settings(rows)
    except ValueError:return {k:DEFAULTS[k] for k in KEYS}

class CompanionPolicy:
    def __init__(self,clock=time.monotonic,rng=None):
        self.clock=clock;self.rng=rng or random.SystemRandom();self.lock=threading.RLock()
        self.playful_context=True
        self.epoch=0;self.pending=False;self.emissions=deque();self.count=0;self.room_visits={}
        self.last_activity=self.clock();self.next_at=self.last_activity+120;self.suspended=False
    def touch(self,delay=120):
        with self.lock:
            self.epoch+=1;self.pending=False;self.count=0;self.last_activity=self.clock();self.suspended=False
            self.next_at=self.last_activity+float(delay)*self.rng.uniform(.75,1.25)
    def suspend(self):
        with self.lock:self.epoch+=1;self.pending=False;self.suspended=True
    def reserve(self,allowed):
        with self.lock:
            now=self.clock()
            while self.emissions and now-self.emissions[0]>=3600:self.emissions.popleft()
            if not allowed or self.suspended or self.pending or self.count>=2 or len(self.emissions)>=4 or now<self.next_at:return None
            self.pending=True;return self.epoch
    def valid(self,token):
        with self.lock:return self.pending and not self.suspended and token==self.epoch
    def commit(self,token,allowed=True):
        with self.lock:
            if not self.valid(token):return False
            self.pending=False
            if not allowed:self.next_at=self.clock()+30;return False
            self.count+=1;self.emissions.append(self.clock());self.next_at=self.clock()+self.rng.uniform(600,900)
            return True
    def enter(self,room):
        with self.lock:
            now=self.clock();last=self.room_visits.get(room)
            if last is not None and now-last<1200:return False
            self.room_visits[room]=now;return True

def policy(main):
    item=getattr(main,'companion_policy',None)
    if not isinstance(item,CompanionPolicy):item=CompanionPolicy();main.companion_policy=item
    return item

def touch(main,text=None,force=False):
    state=policy(main)
    if state.suspended and text is None and not force:return
    state.touch(int(settings(main)['companion_idle_delay']))
    if isinstance(text,str):state.playful_context=not bool(re.search(r'\b(sedih|duka|sakit|panik|cemas|stres|stress|gagal|error|rusak|debug|deadline|rekaman|rapat|meeting)\b',text,re.I))

def apply_settings(main,value):
    values=validate_settings(value);main.preferences.set_many(values);touch(main,force=True)
    if not values['companion_idle']:policy(main).suspend()
    return values

def available(main):
    if getattr(main,'closed',False) or main.busy or main.desktop.paused or main.desktop.sleeping:return False
    if not settings(main)['companion_idle']:return False
    if getattr(main,'_translation_pending',False) or getattr(main,'_tts_waiting',False) or main.reply_voice.active:return False
    if getattr(main,'_image_gpu_active',False) or getattr(main,'dictation_active',False):return False
    if main.entry.get().strip():return False
    if getattr(main,'_voice_frontend_pending',False):return False
    # Never speak over live voice, capture, an unfinished utterance, or a queued task.
    for name in ('voice_window','duplex_window','voice_pack_window'):
        view=getattr(main,name,None)
        if view and view.service.active:return False
    mic=main.local_mic.telemetry.snapshot(main.local_mic.active)
    if mic.get('rms_db',-80)>-40 or str(mic.get('text','')).strip() and getattr(main,'active_voice',None):return False
    inbox=getattr(main,'_speech_inbox',None)
    if inbox and inbox.pending():return False
    host=getattr(main,'_web_host',None)
    if host and (host.bridge.speech.pending() or not host.bridge.commands.empty() or time.monotonic()<getattr(host.bridge,'ui_draft_until',0)):return False
    browser_visible=host and time.monotonic()-getattr(host.bridge,'ui_last_seen',0)<5
    try:desktop_visible=main.root.state()=='normal' and main.root.focus_displayof() is not None
    except Exception:desktop_visible=False
    return bool(desktop_visible or browser_visible)

def observed_apps(result,process_name=None):
    """PID/executable evidence only; a browser title mentioning Discord is insufficient."""
    if result.get('status')!='done':return {}
    if process_name is None:
        import psutil
        process_name=lambda pid:psutil.Process(pid).name()
    apps={}
    for row in result.get('windows',[]):
        try:name=process_name(int(row['pid'])).casefold()
        except Exception:continue
        if name in ('discord.exe','chrome.exe','msedge.exe'):
            apps[{'discord.exe':'discord','chrome.exe':'chrome','msedge.exe':'edge'}[name]]=True
    return apps

def speak_if_cached(main,row):
    """Reuse only exact pack/language/text clips; never load a GPU model during AFK."""
    if not main.spoken_replies.get() or main.reply_voice.active:return False
    from task_reactions import cached_reaction
    language=main.preferences.get('speech_language');pack=main.preferences.get('target_voice_pack')
    spoken=row['speech_text'] if language=='ja' else row['text']
    path=cached_reaction(pack,language,speech=spoken)
    if not path:return False
    service=main.reply_voice.service
    service.output_device_name=main.preferences.get('output_device_name');service.output_hostapi=main.preferences.get('output_hostapi')
    service.reference_callback=main.local_mic.reference;main.local_mic.spoken_text=spoken
    main.reply_voice.speak_cached(path,pack,language);return True

def greet(main,room=None,force=False):
    from leva_persona import DELIVERY
    room=room or getattr(main,'workspace','assistant')
    if force:policy(main).room_visits.pop(room,None)
    if not policy(main).enter(room):return False
    row=DELIVERY.greeting(room=room,playful=settings(main)['companion_playful'] and policy(main).playful_context)
    main.add('Leva',row['text']);main.companion_last={'kind':'greeting','room':room,'evidence':{}}
    touch(main)
    return True

def sync_web_interaction(main):
    host=getattr(main,'_web_host',None)
    if host:
        seen=getattr(host.bridge,'ui_interaction_seen',0)
        if isinstance(seen,(float,int)) and seen>getattr(main,'_companion_web_seen',0):
            main._companion_web_seen=seen;touch(main)

def tick(main):
    sync_web_interaction(main)
    state=policy(main);token=state.reserve(available(main))
    if token is None:return
    room=getattr(main,'workspace','assistant');generation=main.generation
    def authorized():return state.valid(token) and not main.closed and not main.busy and generation==main.generation and room==main.workspace
    def run():
        apps={};observed=False
        if room=='assistant' and authorized():
            from feature_bridge import FeatureBridge
            bridge=FeatureBridge()
            try:
                result=bridge.run('list_windows',{},authorized=authorized,timeout=6)
                if authorized():apps=observed_apps(result);observed=result.get('status')=='done'
            except Exception:pass
            finally:bridge.stop()
        if authorized():main.events.put((generation,{'_companion':{'token':token,'room':room,'apps':apps,'observed':observed}}))
    threading.Thread(target=run,daemon=True).start()

def deliver(main,event):
    sync_web_interaction(main)
    room=event['room'];state=policy(main)
    if room!=getattr(main,'workspace','assistant') or not state.commit(event['token'],available(main)):return False
    from leva_persona import DELIVERY
    row=DELIVERY.standby(room,event.get('apps',{}),settings(main)['companion_playful'] and state.playful_context)
    main.add('Leva · Sapaan',row['text'])
    main.companion_last={'kind':'standby','room':room,'evidence':row['evidence'],'inspection':'read_only_windows' if event.get('observed') else 'not_available'}
    try:
        if speak_if_cached(main,row) and main.preferences.get('speech_language')=='ja':main.add('Ucapan · 日本語',row['speech_text'])
    except (ValueError,OSError,RuntimeError):pass
    return True
