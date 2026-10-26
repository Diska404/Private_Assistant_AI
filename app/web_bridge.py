"""Loopback companion UI. Commands enter the existing Tk host queue, never a second agent."""
from collections import deque
import copy
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import socket
import sys
import threading
import time
from urllib.parse import urlparse,parse_qs

from paths import ROOT
from web_store import WebStore,PairingGate
from web_audio import WebAudio
from web_presence import WebPresence
from remote_speech import RemoteSpeech,MAX_WAV
from profile_avatar import ProfileAvatar,MAX_UPLOAD

def remote_origin(value):
    import re
    if value=='' or value is None:return ''
    if not isinstance(value,str) or not re.fullmatch(r'https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z0-9-]+\.ts\.net',value):raise ValueError('invalid_private_remote_origin')
    return value

ASSETS=Path(sys._MEIPASS)/'leva_web' if getattr(sys,'frozen',False) else ROOT/'app/leva_web'
KINDS={'chat','pause','resume','release','stop_voice','arm','dictation_start','dictation_commit','new_conversation','route','dual','language','spoken','navigate','test_audio','pipeline_settings','workspace','room_settings','handoff','persona_settings','companion_settings','companion_stop'}

class WebBridge:
    def __init__(self,reader,port=8769,assets=None,store=None,remote='',avatar=None):
        self.reader=reader;self.port=int(port);self.assets=Path(assets) if assets else ASSETS
        self.lock=threading.RLock();self.commands=queue.Queue(maxsize=20);self.controls=queue.Queue(maxsize=20)
        self.logs=deque(maxlen=120);self.jobs={};self.state={};self.revision=0;self.server=None;self.thread=None
        self.bootstrap=secrets.token_urlsafe(32);self.cookie=secrets.token_urlsafe(32);self.stopped=False
        self.store=store or WebStore();self.pairing=PairingGate();self.remote=remote_origin(remote);self.instance=secrets.token_hex(12);self.audio=WebAudio()
        from conversation_attachments import ConversationUploads
        self.uploads=ConversationUploads()
        self.presence=WebPresence();self.speech=RemoteSpeech();self.avatar=avatar or ProfileAvatar()
        from vts_bridge import VTSService
        self.vts=VTSService()
    def publish_audio(self,path,metadata=None):
        with self.lock:self.audio.publish(path,metadata);self.revision+=1
    def cancel_audio(self):
        with self.lock:self.audio.cancel();self.revision+=1
    def update(self,state):
        with self.lock:
            if self.state!=state:self.state=copy.deepcopy(state);self.revision+=1
    def log(self,speaker,text):
        with self.lock:
            self.logs.append({'id':self.revision+1,'speaker':str(speaker)[:100],'text':str(text)[:8000]});self.revision+=1
    def snapshot(self,since=None,instance=None,messages_since=None):
        with self.lock:
            # Compare before copying state or querying the delivery ledger. The
            # authenticated HTTP path already returned 204 for this exact case.
            if since is not None and str(self.revision)==str(since) and instance==self.instance:return None
            value={'revision':self.revision,'instance':self.instance,'state':copy.deepcopy(self.state),'messages':list(self.logs),
                'queue':sum(j['status']=='queued' for j in self.jobs.values()),'commands':self.store.recent(),'audio':self.audio.manifest(),'avatar':self.avatar.metadata()}
            # Opt-in delta protocol. A missing cursor (trim/reset/new room) always
            # sends the complete retained history, including an empty history.
            if messages_since is not None:
                rows=value['messages'];cursor=str(messages_since)
                matched=instance==self.instance and any(str(row['id'])==cursor for row in rows)
                value['messages_mode']='append' if matched else 'replace'
                value['messages_first_id']=rows[0]['id'] if rows else 0
                if matched:value['messages']=[row for row in rows if row['id']>int(cursor)]
            return value
    def submit(self,data,owner='desktop',client=None):
        if not isinstance(data,dict) or set(data)-{'id','kind','value'}:raise ValueError('invalid_command')
        ident=data.get('id');kind=data.get('kind');value=data.get('value')
        if not isinstance(ident,str) or not 8<=len(ident)<=100 or kind not in KINDS:raise ValueError('invalid_command')
        if kind=='chat':
            if isinstance(value,str):
                if not value.strip() or len(value)>3000:raise ValueError('invalid_message')
                # Bind the execution space at enqueue time, including older clients.
                value={'text':value,'workspace':self.state.get('workspace','assistant'),'attachments':[]}
            if not isinstance(value,dict) or set(value)!={'text','workspace','attachments'} or not isinstance(value['text'],str) or not value['text'].strip() or len(value['text'])>3000:raise ValueError('invalid_message')
            from conversation_rooms import room_id
            room_id(value['workspace'])
            self.uploads.resolve(owner,value['attachments'])
        if kind=='handoff' and value not in ('chat','assistant'):raise ValueError('invalid_handoff')
        if kind=='workspace':
            from conversation_rooms import room_id
            room_id(value)
        if kind=='room_settings':
            from conversation_rooms import validate_room_settings
            value=validate_room_settings(value)
        if kind in ('dual','spoken') and type(value) is not bool:raise ValueError('invalid_setting')
        if kind=='language' and value not in ('id','ja'):raise ValueError('invalid_setting')
        if kind=='persona_settings':
            from presence_companion import validate_settings
            value=validate_settings(value)
        if kind=='companion_settings':value=__import__('companion_avatar').validate_settings(value)
        if kind=='pipeline_settings':
            from speech_configuration import validate_pipeline_settings
            value=validate_pipeline_settings(value)
        if kind=='navigate' and value not in ('center','skills','memory','voice','settings'):raise ValueError('invalid_navigation')
        if kind=='route':
            from pipeline_routing import VOICE_SINGLE,VOICE_DUAL
            if value not in VOICE_SINGLE+VOICE_DUAL:raise ValueError('invalid_route')
        with self.lock:
            if not self.store.active(owner):raise ValueError('device_revoked_or_expired')
            if ident in self.jobs:
                old=self.jobs[ident]
                if old['kind']!=kind or old.get('value')!=value or old.get('owner','desktop')!=owner:raise ValueError('idempotency_conflict')
                return {k:v for k,v in old.items() if k!='value'}
            if len(self.jobs)>400:
                for key in list(self.jobs)[:100]:
                    if self.jobs[key]['status']!='queued':self.jobs.pop(key)
            job={'id':ident,'kind':kind,'value':value,'status':'queued','owner':owner}
            if client:job['client']=client
            old=self.store.reserve(job,owner)
            if old:return old
            try:(self.commands if kind=='chat' else self.controls).put_nowait(job)
            except queue.Full:
                self.store.finish(ident,'failed','Antrean penuh; permintaan ini belum dijalankan.')
                raise ValueError('desktop_queue_full') from None
            self.jobs[ident]=job;self.revision+=1
            return {k:v for k,v in job.items() if k!='value'}
    def finish(self,job,status,detail='',task_id=''):
        with self.lock:
            job.update(status=status,detail=detail[:200],task_id=task_id);self.store.finish(job['id'],status,detail,task_id);self.revision+=1
    def start(self):
        with self.lock:
            if self.server:return self.url
            if not (self.assets/'index.html').is_file():raise OSError('web_assets_missing')
            bridge=self
            class Handler(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup();self.connection.settimeout(5)
                def log_message(self,*args):pass
                def send(self,status,data=None,mime='application/json',cookie=False):
                    raw=data if isinstance(data,bytes) else (json.dumps(data,ensure_ascii=False).encode('utf8') if mime=='application/json' else data) if data is not None else b''
                    self.send_response(status);self.send_header('Content-Type',mime if mime.startswith('audio/') else mime+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self' blob:; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'")
                    if cookie:self.send_header('Set-Cookie','leva_session='+(bridge.cookie if cookie is True else cookie)+'; HttpOnly; SameSite=Strict; Path=/'+('; Secure; Max-Age=2592000' if self.request_origin()==bridge.remote and bridge.remote else ''))
                    self.end_headers()
                    try:self.wfile.write(raw)
                    except (BrokenPipeError,ConnectionResetError):pass
                def request_origin(self):
                    # Serve terminates TLS and sets these headers. Never trust an
                    # arbitrary forwarded hostname or an unconfigured proxy.
                    forwarded=self.headers.get('X-Forwarded-Host','')
                    if forwarded or self.headers.get('X-Forwarded-Proto'):
                        if bridge.remote and forwarded==bridge.remote[8:] and self.headers.get('X-Forwarded-Proto')=='https' and self.client_address[0]=='127.0.0.1':return bridge.remote
                        return ''
                    return bridge.origin if self.headers.get('Host')==bridge.origin[7:] else ''
                def valid_origin(self):
                    origin=self.headers.get('Origin');expected=self.request_origin()
                    return bool(expected) and (not origin or origin==expected) and self.headers.get('Sec-Fetch-Site','same-origin') not in ('cross-site','same-site')
                def session(self):
                    if not self.valid_origin():return None
                    cookies=dict(v.strip().split('=',1) for v in self.headers.get('Cookie','').split(';') if '=' in v)
                    token=cookies.get('leva_session','')
                    if self.request_origin()==bridge.origin and hmac.compare_digest(token,bridge.cookie):return {'id':'desktop','name':'Desktop'}
                    return bridge.store.authenticate(token) if token else None
                def authenticated(self):
                    return self.session() is not None
                def do_GET(self):
                    if not self.valid_origin():self.send(403,{'error':'origin_denied'});return
                    parsed=urlparse(self.path)
                    if parsed.path=='/health':self.send(200,{'service':'leva-web','desktop_bridge':True});return
                    if parsed.path.startswith('/api/'):
                        if not self.authenticated():self.send(401,{'error':'open_from_desktop'});return
                        try:
                            if parsed.path=='/api/avatar':
                                raw=bridge.avatar.read()
                                self.send(200,raw,'image/png') if raw else self.send(404,{'error':'avatar_not_set'})
                                return
                            if parsed.path in ('/api/avatar-model/leva_original.vrm','/api/avatar-model/pixiv_sample.vrm','/api/avatar-model/pixiv_polished.vrm','/api/avatar-model/custom.vrm'):
                                from avatar_assets import read
                                self.send(200,read(parsed.path.rsplit('/',1)[1].split('.')[0]),'model/gltf-binary');return
                            if parsed.path.startswith('/api/live2d/') and parsed.path!='/api/live2d/status':
                                from live2d_assets import read
                                raw,mime=read(parsed.path[len('/api/live2d/'):]);self.send(200,raw,mime);return
                            if parsed.path=='/api/transcribe':
                                row=bridge.speech.get(parse_qs(parsed.query).get('id',[''])[0],self.session()['id'])
                                self.send(200,row) if row else self.send(404,{'error':'recording_not_found'});return
                            if parsed.path.startswith('/api/audio/'):
                                import re
                                match=re.fullmatch(r'/api/audio/([a-f0-9]{24})/([0-9]{1,12})\.wav',parsed.path)
                                raw=bridge.audio.read(match[1],int(match[2])) if match else None
                                if raw is None:self.send(404,{'error':'audio_expired_or_cancelled'});return
                                self.send(200,raw,'audio/wav');return
                            if parsed.path=='/api/state':
                                bridge.ui_last_seen=time.monotonic()
                                with bridge.lock:bridge.presence.touch(self.session(),self.headers.get('User-Agent',''),self.request_origin()==bridge.remote and bool(bridge.remote))
                                query=parse_qs(parsed.query)
                                value=bridge.snapshot(query.get('since',[None])[0],query.get('instance',[None])[0],query.get('messages_since',[None])[0])
                                if value is None:self.send(204);return
                                value['session']={'device':self.session()['name'],'remote':self.request_origin()==bridge.remote}
                            elif parsed.path=='/api/conversation':
                                provider=getattr(bridge,'transcript_provider',None)
                                if not provider:self.send(503,{'error':'conversation_export_unavailable'});return
                                value=provider(parse_qs(parsed.query).get('workspace',[bridge.state.get('workspace','assistant')])[0])
                            elif parsed.path=='/api/requests':value={'requests':bridge.store.recent()}
                            elif parsed.path=='/api/trace':
                                room=bridge.state.get('workspace','assistant')
                                if room not in ('assistant','chat'):value={'events':[],'runs':[],'workspace':room}
                                else:
                                    from trace_store import TraceStore
                                    provider=getattr(bridge,'trace_store_provider',None)
                                    store=getattr(bridge,'trace_store',None) or (provider() if provider else None)
                                    if not isinstance(store,TraceStore):store=None
                                    query=parse_qs(parsed.query)
                                    run=query.get('run_id',[''])[0]
                                    if run and store:value=store.replay(room,run,int(query.get('after',['0'])[0]))
                                    else:value={'events':bridge.state.get('trace_events',[]),'runs':store.runs(room) if store else [],'health':store.health() if store else {}}
                                    if room!=bridge.state.get('workspace','assistant'):raise ValueError('workspace_changed_retry')
                                    value['workspace']=room
                            elif parsed.path=='/api/live2d/status':value=__import__('live2d_assets').status()
                            elif parsed.path=='/api/vts/status':value=bridge.vts.snapshot()
                            elif parsed.path=='/api/graph':value=bridge.reader.graph()
                            elif parsed.path=='/api/panel':value=bridge.reader.panel(parse_qs(parsed.query).get('name',[''])[0])
                            else:self.send(404,{'error':'not_found'});return
                            self.send(200,value)
                        except ValueError as error:self.send(409 if str(error)=='workspace_changed_retry' else 400,{'error':str(error)[:160]})
                        except Exception as error:self.send(500,{'error':type(error).__name__})
                        return
                    name={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/graph.js':'graph.js','/physics.js':'physics.js','/camera.js':'camera.js','/engines.js':'engines.js','/rooms.js':'rooms.js','/copy.js':'copy.js','/persona.js':'persona.js','/workspace.js':'workspace.js','/workspace.css':'workspace.css','/style.css':'style.css','/mobile.js':'mobile.js','/audio.js':'audio.js','/mic.js':'mic.js','/mic-worklet.js':'mic-worklet.js','/manifest.webmanifest':'manifest.webmanifest','/icon.svg':'icon.svg'}.get(parsed.path)
                    if parsed.path in ('/messages.js','/trace.js','/avatar.js','/avatar.css','/avatar-vendor.js','/vrm_avatar.js','/avatar_dynamics.js','/avatar_performance.js','/avatar_reactions.js','/avatar_secondary.js','/avatar_timing.js','/vts_avatar.js','/live2d_avatar.js','/live2d_expression.js','/live2d_framing.js','/live2d_rig_controls.js','/live2d_rig_lab.js','/THIRD_PARTY_NOTICES.txt'):name=parsed.path[1:]
                    if not name:self.send(404,b'Not found','text/plain');return
                    mime='text/plain' if name.endswith('.txt') else 'image/svg+xml' if name.endswith('.svg') else 'application/manifest+json' if name.endswith('.webmanifest') else 'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
                    self.send(200,(bridge.assets/name).read_bytes(),mime)
                def do_POST(self):
                    if not self.valid_origin() or self.headers.get('Origin')!=self.request_origin():self.send(403,{'error':'origin_denied'});return
                    if self.path=='/api/session':
                        if self.request_origin()!=bridge.origin:self.send(403,{'error':'desktop_bootstrap_only'});return
                        if not hmac.compare_digest(self.headers.get('X-Leva-Bootstrap',''),bridge.bootstrap):self.send(401,{'error':'invalid_session'});return
                        self.send(200,{'ok':True},cookie=True);return
                    if self.path=='/api/pair':
                        try:
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=1000:raise ValueError('invalid_pairing')
                            data=json.loads(self.rfile.read(length));name=data.get('name','Android')
                            if not isinstance(name,str) or not 1<=len(name.strip())<=40:raise ValueError('invalid_device_name')
                            if not bridge.pairing.consume(data.get('code')):self.send(401,{'error':'pairing_code_invalid_or_expired'});return
                            ident,token=bridge.store.device(name);bridge.revision+=1
                            self.send(200,{'ok':True,'device':name},cookie=token)
                        except (ValueError,TypeError):self.send(400,{'error':'invalid_pairing'})
                        return
                    if not self.authenticated():self.send(401,{'error':'open_from_desktop'});return
                    if self.path in ('/api/vts/connect','/api/vts/frame','/api/vts/disconnect'):
                        try:
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=2000:raise ValueError('invalid_vts_body')
                            value=json.loads(self.rfile.read(length));owner=self.session()['id']
                            if bridge.state.get('workspace')!='companion_avatar':raise ValueError('companion_not_active')
                            if self.path=='/api/vts/connect':
                                if not isinstance(value,dict) or set(value)-{'authorize','port'} or type(value.get('authorize',False)) is not bool:raise ValueError('invalid_vts_connect')
                                if value.get('authorize') and self.request_origin()!=bridge.origin:raise ValueError('vts_authorize_from_laptop_only')
                                result=bridge.vts.start(owner,authorize=value.get('authorize',False),port=value.get('port',8001))
                            elif self.path=='/api/vts/frame':result={'accepted':bridge.vts.feed(owner,value)}
                            else:bridge.vts.close(owner);result=bridge.vts.snapshot()
                            self.send(200,result)
                        except (ValueError,TypeError):self.send(400,{'error':'vts_invalid_request_or_owner'})
                        return
                    if self.path=='/api/avatar-model':
                        try:
                            from avatar_assets import upload,MAX_MODEL
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=MAX_MODEL:raise ValueError('avatar_max_64MiB')
                            self.connection.settimeout(15);raw=self.rfile.read(length)
                            if len(raw)!=length:raise ValueError('avatar_incomplete_upload')
                            self.send(200,upload(raw))
                        except (ValueError,TypeError,OSError):self.send(400,{'error':'avatar_upload_invalid_or_unsupported'})
                        return
                    if self.path=='/api/interaction':
                        try:
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=100:raise ValueError('invalid_interaction')
                            value=json.loads(self.rfile.read(length))
                            if not isinstance(value,dict) or set(value)!={'draft'} or type(value['draft']) is not bool:raise ValueError('invalid_interaction')
                            with bridge.lock:
                                bridge.ui_interaction_seen=time.monotonic()
                                bridge.ui_draft_until=time.monotonic()+8 if value['draft'] else 0
                            self.send(200,{'ok':True})
                        except (ValueError,TypeError):self.send(400,{'error':'invalid_interaction'})
                        return
                    if urlparse(self.path).path=='/api/attachments':
                        try:
                            from conversation_attachments import MAX_BYTES
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=MAX_BYTES:raise ValueError('Lampiran maksimal 6 MB.')
                            name=parse_qs(urlparse(self.path).query).get('name',[''])[0]
                            self.connection.settimeout(15);raw=self.rfile.read(length)
                            if len(raw)!=length:raise ValueError('Lampiran belum lengkap.')
                            self.send(200,bridge.uploads.save(self.session()['id'],name,raw))
                        except (ValueError,TypeError) as error:self.send(400,{'error':str(error)[:200]})
                        return
                    if self.path=='/api/avatar':
                        try:
                            length=int(self.headers.get('Content-Length','0'))
                            if not 0<length<=MAX_UPLOAD:raise ValueError('avatar_max_5mb')
                            raw=self.rfile.read(length)
                            if len(raw)!=length:raise ValueError('avatar_incomplete_upload')
                            crop=self.headers.get('X-Leva-Crop','')
                            if len(crop)>=200:raise ValueError('avatar_invalid_framing')
                            frame=json.loads(crop) if crop else None
                            result=bridge.avatar.save(raw,frame)
                            with bridge.lock:bridge.revision+=1
                            self.send(200,result)
                        except (ValueError,TypeError) as error:self.send(400,{'error':str(error)[:100]})
                        return
                    if self.path=='/api/transcribe/cancel':
                        ident=self.headers.get('X-Leva-Request','')
                        self.send(200,{'cancelled':bridge.speech.cancel(ident,self.session()['id'])});return
                    if self.path=='/api/transcribe':
                        try:
                            if bridge.state.get('phase')=='paused' or bridge.state.get('route')=='Tanpa AI':raise ValueError('speech_disabled_choose_ai_route_and_resume')
                            length=int(self.headers.get('Content-Length','0'))
                            if not 44<length<=MAX_WAV:raise ValueError('invalid_audio_size')
                            if self.headers.get('Content-Type','').split(';')[0]!='audio/wav':raise ValueError('audio_wav_required')
                            self.connection.settimeout(15)
                            raw=self.rfile.read(length)
                            if len(raw)!=length:raise ValueError('incomplete_audio')
                            self.send(202,bridge.speech.submit(self.headers.get('X-Leva-Request',''),self.session()['id'],raw))
                        except (ValueError,TypeError,EOFError,__import__('wave').Error) as error:self.send(400,{'error':str(error)[:100]})
                        return
                    if self.path!='/api/commands':self.send(404,{'error':'not_found'});return
                    try:
                        length=int(self.headers.get('Content-Length','0'))
                        if not 0<length<=16000:raise ValueError('invalid_body_size')
                        data=json.loads(self.rfile.read(length));session=self.session();client=WebPresence.client(session,self.headers.get('User-Agent',''),self.request_origin()==bridge.remote and bool(bridge.remote))
                        job=bridge.submit(data,session['id'],client);self.send(202,job)
                    except (ValueError,TypeError):self.send(400,{'error':'invalid_command_or_queue_full'})
            class LocalServer(ThreadingHTTPServer):
                allow_reuse_address=False
                def server_bind(self):
                    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                    super().server_bind()
            try:self.server=LocalServer(('127.0.0.1',self.port),Handler)
            except OSError:self.server=LocalServer(('127.0.0.1',0),Handler)
            self.origin='http://127.0.0.1:'+str(self.server.server_port);self.url=self.origin+'/#session='+self.bootstrap
            self.server.daemon_threads=True;self.server.timeout=1
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
            return self.url
    def stop(self):
        self.vts.close()
        self.speech.stop()
        self.cancel_audio()
        with self.lock:server=self.server;self.server=None;self.stopped=True
        if server:server.shutdown();server.server_close()
        if self.thread:self.thread.join(timeout=2)
