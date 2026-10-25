"""Optional local VTube Studio backend. No PC tools, tracking devices or generic RPC exposed."""
import json,math,secrets,threading,time
from pathlib import Path
from paths import DATA

PLUGIN={'pluginName':'Leva Avatar Bridge','pluginDeveloper':'Leva AI Personal'}
FRAME_KEYS={'headX','headY','headZ','gazeX','gazeY','mouth','happy','sad','angry','blink','blinkLeft','blinkRight'}

def validate_frame(value):
    if not isinstance(value,dict) or set(value)-FRAME_KEYS:raise ValueError('invalid_avatar_frame')
    if any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1 for x in value.values()):raise ValueError('invalid_avatar_frame')
    return {key:float(value.get(key,0)) for key in FRAME_KEYS}

def tracking_parameters(frame):
    f=validate_frame(frame)
    values={'FaceAngleX':f['headY']*180/math.pi,'FaceAngleY':-f['headX']*180/math.pi,'FaceAngleZ':f['headZ']*180/math.pi,
        'EyeOpenLeft':max(0,1-max(f['blink'],f['blinkLeft'])),'EyeOpenRight':max(0,1-max(f['blink'],f['blinkRight'])),
        'EyeRightX':f['gazeX']*5,'EyeRightY':f['gazeY']*5,'MouthOpen':max(0,f['mouth']),
        'MouthSmile':max(0,min(1,f['happy']*1.5)),'Brows':max(0,min(1,.5+f['happy']*.2-f['sad']*.3-f['angry']*.3))}
    return [{'id':key,'value':value,'weight':1.0} for key,value in values.items()]

class VTSClient:
    def __init__(self,port=8001,token_file=None,connector=None):
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('invalid_vts_port')
        self.port=port;self.token_file=Path(token_file) if token_file else DATA/'credentials/vts-token.dpapi';self.connector=connector;self.socket=None
    def connect(self):
        from websockets.sync.client import connect
        self.socket=(self.connector or connect)('ws://127.0.0.1:'+str(self.port),open_timeout=3,close_timeout=1,proxy=None,max_size=1000000)
        return self.request('APIStateRequest')
    def request(self,kind,data=None,timeout=3):
        if self.socket is None:raise ValueError('vts_not_connected')
        ident=secrets.token_hex(8);self.socket.send(json.dumps({'apiName':'VTubeStudioPublicAPI','apiVersion':'1.0','requestID':ident,'messageType':kind,'data':data or {}}))
        deadline=time.monotonic()+timeout
        for _ in range(12):
            row=json.loads(self.socket.recv(timeout=max(.01,deadline-time.monotonic())))
            if row.get('requestID')!=ident:continue
            if row.get('messageType')=='APIError':raise ValueError('vts_api_error_'+str(row.get('data',{}).get('errorID','unknown')))
            return row.get('data',{})
        raise ValueError('vts_response_mismatch')
    def authenticate(self,authorize=False):
        from router_provider import save_key,load_key
        token=load_key(self.token_file) if self.token_file.is_file() else ''
        if authorize:
            token=self.request('AuthenticationTokenRequest',PLUGIN,timeout=60).get('authenticationToken','')
            if not isinstance(token,str) or not 1<=len(token)<=64:raise ValueError('invalid_vts_token')
            save_key(token,self.token_file)
        elif not token:raise ValueError('vts_authorization_required')
        result=self.request('AuthenticationRequest',{**PLUGIN,'authenticationToken':token})
        if result.get('authenticated') is not True:raise ValueError('vts_authentication_failed')
        return self.request('CurrentModelRequest')
    def close(self):
        if self.socket:self.socket.close();self.socket=None

class VTSService:
    def __init__(self,client_factory=VTSClient,clock=time.monotonic):
        self.factory=client_factory;self.clock=clock;self.lock=threading.RLock();self.thread=None;self.stop_event=threading.Event();self.client=None
        self.status={'state':'off','frames_sent':0,'model_name':'','backend':'external_vtube_studio','native_web_renderer':False}
        self.owner=None;self.last_seen=0;self.latest=validate_frame({});self.last_frame=0
    def snapshot(self):
        with self.lock:return dict(self.status)
    def start(self,owner,authorize=False,port=8001):
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('invalid_vts_port')
        if self.thread and self.thread.is_alive():raise ValueError('vts_session_already_active')
        self.stop_event.clear();self.owner=owner;self.last_seen=self.clock();self.status.update(state='connecting',error='',frames_sent=0)
        def run():
            client=self.factory(port=port);self.client=client
            try:
                state=client.connect()
                if not state.get('active'):raise ValueError('vts_api_disabled')
                with self.lock:self.status['state']='awaiting_authorization' if authorize else 'authenticating'
                model=client.authenticate(authorize=authorize)
                if not model.get('modelLoaded'):raise ValueError('vts_load_a_model_first')
                with self.lock:self.status.update(state='connected',model_name=str(model.get('modelName',''))[:100],model_id=str(model.get('modelID',''))[:64])
                while not self.stop_event.is_set():
                    with self.lock:frame=dict(self.latest);age=self.clock()-self.last_seen
                    if age>10:
                        with self.lock:self.status['state']='client_disconnected'
                        break
                    if age>.6:frame=validate_frame({})
                    start=self.clock();client.request('InjectParameterDataRequest',{'faceFound':False,'mode':'set','parameterValues':tracking_parameters(frame)})
                    with self.lock:self.status['frames_sent']+=1;self.status['request_ms']=round((self.clock()-start)*1000,2);self.status['client_stale']=age>.6
                    self.stop_event.wait(1/30)
            except Exception as e:
                with self.lock:self.status.update(state='error',error=str(e)[:100] if isinstance(e,ValueError) else type(e).__name__)
            finally:
                try:client.close()
                except Exception:pass
                self.client=None
        self.thread=threading.Thread(target=run,name='Leva-VTS-bridge',daemon=True);self.thread.start()
        return self.snapshot()
    def feed(self,owner,value):
        frame=validate_frame(value);now=self.clock()
        with self.lock:
            if owner!=self.owner or self.status['state']!='connected':raise ValueError('vts_owner_or_connection_required')
            if now-self.last_frame<1/60:return False
            self.latest=frame;self.last_seen=now;self.last_frame=now
        return True
    def close(self,owner=None):
        if owner is not None and self.owner!=owner:raise ValueError('vts_owner_required')
        self.stop_event.set()
        if self.client:
            try:self.client.close()
            except Exception:pass
        if self.thread:self.thread.join(timeout=1.2)
        with self.lock:self.owner=None;self.status.update(state='off',model_name='',model_id='');self.latest=validate_frame({})
