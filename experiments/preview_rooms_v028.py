"""Isolated phone-layout fixture; never connects to real models, audio or user data."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/leva_web'
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from web_audio import WebAudio
from task_reactions import cached_reaction
from profile_avatar import ProfileAvatar
AUDIO=WebAudio()
VOICE=cached_reaction('higgs_leva','ja')
if VOICE is None:raise RuntimeError('voice_fixture_cache_missing')
OUT = Path('D:/AI/AI Lokal Asisten/Leva/verification/conversation-rooms-v028/visual-fixture')
OUT.mkdir(parents=True, exist_ok=True)
AVATAR=ProfileAvatar(OUT/'fixture-profile')
STOP = OUT / 'stop-preview'
STOP.unlink(missing_ok=True)
lock = threading.RLock()
from preferences import Preferences
from speech_configuration import configuration_snapshot,apply_pipeline_settings,AGENT_ROUTES
from pipeline_routing import route_spec
from types import SimpleNamespace
from unittest.mock import Mock
PREFS=Preferences(OUT/'preview-preferences.sqlite3')
PREFS.set_many({'asr_gpu':'rtx5070','agent_provider':'Dual GPU','agent_gpu':'auto'})
MAIN=SimpleNamespace(preferences=PREFS,busy=False,local_mic=Mock(),cancel_inference=Mock(),stop_reply_voice=Mock())
revision = 1
workspace='assistant'
phase = 'idle'
jobs = []
messages = [
    {'speaker':'Anda','text':'Leva, bantu aku melanjutkan proyek hari ini.'},
    {'speaker': 'Info', 'text': 'UJI TAMPILAN · DATA CONTOH. Tidak menjalankan model atau mengontrol laptop.'},
    {'speaker': 'Leva', 'text': 'Aku siap menemanimu. Tarik jaringan untuk memutar bola, atau buka layar penuh.'},
]


def snapshot():
    return {
        'revision': revision, 'instance': 'mobile-neural-qa-only','avatar':AVATAR.metadata(),
        'session': {'device': 'Android · contoh', 'remote': True}, 'audio': AUDIO.manifest(),
        'state': {
            'workspace':workspace,'rooms':__import__('conversation_rooms').ConversationRooms.snapshot(None,PREFS),'handoff':None,
            'pipeline': configuration_snapshot(PREFS,route_spec('RTX 5070')),
            'clients': [{'kind':'android','name':'Android contoh'}], 'desktop_mic_suspended':True, 'verification_mode': True, 'phase': phase, 'busy': phase == 'thinking',
            'route_choices':['Tanpa AI','RTX 4050','RTX 5070','Dual GPU'], 'route': 'RTX 5070',
            'dual': False, 'spoken': True, 'language': 'ja',
            'activity': 'Siap menerima tugas · data uji',
            'mic': {'rms_db': -44, 'text': 'Contoh telemetri mikrofon laptop'},
            'output_level': .12 if phase == 'speaking' else 0,
            'hardware_age_s': 0,
            'hardware': {'cpu_percent': 12, 'ram_used_gib': 18.4, 'ram_total_gib':63.7, 'gpus': [
                {'name': 'NVIDIA GeForce RTX 4050 Laptop GPU', 'used_mib': 1600, 'total_mib': 6141, 'utilization':23, 'temperature_c':56},
                {'name': 'NVIDIA GeForce RTX 5070', 'used_mib': 2100, 'total_mib': 12227, 'utilization':6, 'temperature_c':42},
            ]},
        }, 'messages': messages, 'commands': jobs, 'queue': 0,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, mime='application/json'):
        raw = json.dumps(value, ensure_ascii=False).encode() if mime == 'application/json' else value
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path=='/api/avatar':
            raw=AVATAR.read()
            if raw:self.send(raw,'image/png')
            else:self.send_error(404)
        elif path.startswith('/api/audio/'):
            import re
            match=re.fullmatch(r'/api/audio/([a-f0-9]{24})/([0-9]+)\.wav',path)
            raw=AUDIO.read(match[1],int(match[2])) if match else None
            if raw is None:self.send_error(404)
            else:self.send(raw,'audio/wav')
        elif path == '/api/state':
            with lock:
                self.send(snapshot())
        elif path == '/api/requests':
            self.send({'requests': jobs})
        elif path == '/api/graph':
            self.send({'nodes': [
                {'id': 'note', 'label': 'Rencana suara live · contoh', 'category': 'document', 'detail': {'path': 'Rencana.md'}, 'source': {'kind': 'fixture'}},
                {'id': 'task', 'label': 'Uji antarmuka Android', 'category': 'task', 'detail': {'id': 'fixture-only'}, 'source': {'kind': 'fixture'}},
            ], 'edges': [], 'errors': []})
        elif path == '/api/panel':
            self.send({'title': 'Panel contoh', 'detail': 'Uji antarmuka lokal. Data pribadi tidak dimuat.'})
        elif path == '/health':
            self.send({'fixture': True})
        else:
            name = 'index.html' if path == '/' else path.lstrip('/')
            if name not in {'index.html', 'style.css', 'app.js', 'mobile.js', 'graph.js', 'physics.js','camera.js','engines.js','rooms.js', 'icon.svg', 'manifest.webmanifest','audio.js','mic.js','mic-worklet.js'}:
                self.send_error(404)
                return
            mime = 'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'image/svg+xml' if name.endswith('.svg') else 'application/manifest+json' if name.endswith('.webmanifest') else 'text/javascript'
            self.send((ASSETS / name).read_bytes(), mime)

    def do_POST(self):
        global revision, phase,workspace
        if self.path=='/api/avatar':
            raw=self.rfile.read(int(self.headers.get('Content-Length',0)));result=AVATAR.save(raw);revision+=1;self.send(result);return
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path != '/api/commands':
            self.send_error(404)
            return
        with lock:
            job = {'id': data['id'], 'kind': data['kind'], 'goal': data.get('value'), 'status': 'completed', 'detail': 'Diterima fixture tampilan, bukan agent laptop.'}
            if data['kind']=='workspace':
                workspace=data['value'];jobs.insert(0,job)
            elif data['kind']=='room_settings':
                v=data['value'];PREFS.set_many({v['workspace']+'_model':v['model'],v['workspace']+'_gpu':v['gpu']});jobs.insert(0,job)
            elif data['kind'] == 'pipeline_settings':
                apply_pipeline_settings(MAIN,data['value']);jobs.insert(0,job)
            elif data['kind'] == 'chat':
                messages.extend([{'speaker': 'Anda', 'text': data['value']['text'] if isinstance(data['value'],dict) else data['value']}, {'speaker': 'Leva · Uji', 'text': 'Pesan uji diterima. Tidak ada inferensi atau tindakan PC.'}])
                jobs.insert(0, job)
            elif data['kind'] == 'test_audio':
                AUDIO.publish(VOICE,{'pack':'higgs_leva','language':'ja'})
            elif data['kind'] == 'pause':
                AUDIO.cancel()
                phase = 'paused'
            elif data['kind'] == 'resume':
                phase = 'idle'
            revision += 1
            self.send(job)


server = ThreadingHTTPServer(('127.0.0.1', 8777), Handler)
server.daemon_threads = True
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
print(json.dumps({'origin': 'http://127.0.0.1:8777', 'fixture_only': True}), flush=True)
try:
    began = time.monotonic()
    while not STOP.exists() and time.monotonic() - began < 1800:
        time.sleep(.25)
finally:
    server.shutdown()
    server.server_close()
    (OUT / 'preview-check.json').write_text(json.dumps({'fixture_only': True, 'commands': len(jobs), 'server_stopped': True}), encoding='utf8')
