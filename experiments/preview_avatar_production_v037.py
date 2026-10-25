"""Loopback UI fixture. Synthetic state only; no production imports, mic or executor."""
import json
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit

WEB=Path(__file__).resolve().parents[1]/'app'/'leva_web'
state={'workspace':'companion_avatar','phase':'idle','activity':'PREVIEW TERISOLASI · tidak terhubung ke laptop agent',
 'verification_mode':True,'route_choices':['Tanpa AI'],'route':'Tanpa AI','language':'ja','busy':False,
 'experimental_models_enabled':False,'avatar':{'enabled':True,'display_name':'Leva ♡','state':'idle','expression':'neutral','generation_id':1,'mic_authorized':False,'asset':'pixiv_sample','renderer_gpu':'rtx4050','asset_choices':{'placeholder':'Placeholder 2D','pixiv_sample':'Pixiv VRM 1.0 · sumber berlisensi','pixiv_polished':'Pixiv VRM · layer toon · uji'},'realtime_speech':False,'native_stream':False},
 'hardware':{},'rooms':{'companion_avatar':{'model':'fixture','gpu':'fixture','models':{'fixture':'Preview · tanpa inferensi'},'gpus':{'fixture':'Tidak memuat GPU'}}}}
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(WEB),**kw)
 def log_message(self,*a):pass
 def send_json(self,value):
  body=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=='/mobile-preview':
   body=b'<html><title>Leva mobile viewport fixture</title><body style="margin:0;background:#080e16;display:grid;place-items:center"><iframe title="Leva 390px viewport" src="/" style="width:390px;height:844px;border:1px solid #496173;border-radius:24px"></iframe></body></html>'
   self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/state':return self.send_json({'revision':1,'instance':'isolated-fixture','state':state,'session':{'remote':False},'commands':[],
    'messages':[{'id':1,'speaker':'Leva · Preview','text':'Hai, Raizei. Ini panggung avatar percobaan; mikrofon dan model belum diaktifkan.'}],
    'audio':{'epoch':1,'latest':0,'clips':[]}})
  if path=='/api/avatar-model/pixiv_polished.vrm':
   body=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\pixiv-toon-layer.vrm').read_bytes();self.send_response(200);self.send_header('Content-Type','model/gltf-binary');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/avatar-model/pixiv_sample.vrm':
   body=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets\pixiv-vrm1-sample.vrm').read_bytes();self.send_response(200);self.send_header('Content-Type','model/gltf-binary');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/graph':return self.send_json({'nodes':[],'edges':[]})
  if path.startswith('/api/'):return self.send_json({})
  return super().do_GET()
 def do_POST(self):
  n=min(int(self.headers.get('Content-Length',0)),65536);raw=self.rfile.read(n)
  if urlsplit(self.path).path=='/api/commands':
   row=json.loads(raw or '{}');kind=row.get('kind');value=row.get('value')
   if kind=='workspace' and value in ('assistant','chat','secret','companion_avatar'):state['workspace']=value
   if kind=='companion_stop':state['avatar']['state']='interrupted';state['avatar']['generation_id']+=1
   if kind=='companion_settings':state['avatar'].update(enabled=bool(value['enabled']),display_name=value['label'],asset=value.get('asset','pixiv_sample'),renderer_gpu=value.get('renderer_gpu','rtx4050'))
  self.send_json({'status':'completed','fixture':True})
if __name__=='__main__':
 print('Isolated companion fixture: http://127.0.0.1:20286',flush=True)
 ThreadingHTTPServer(('127.0.0.1',20286),Handler).serve_forever()
