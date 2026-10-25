"""Isolated phone-layout fixture; never connects to real models, audio or user data."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/leva_web'
OUT = Path('D:/AI/AI Lokal Asisten/Leva/verification/mobile-neural-v0241')
OUT.mkdir(parents=True, exist_ok=True)
STOP = OUT / 'stop-preview'
STOP.unlink(missing_ok=True)
lock = threading.RLock()
revision = 1
phase = 'idle'
jobs = []
messages = [
    {'speaker': 'Info', 'text': 'UJI TAMPILAN · DATA CONTOH. Tidak menjalankan model atau mengontrol laptop.'},
    {'speaker': 'Leva', 'text': 'Aku siap menemanimu. Neural Interface dan percakapan kini bisa dilihat bersama dari HP.'},
]


def snapshot():
    return {
        'revision': revision, 'instance': 'mobile-neural-qa-only',
        'session': {'device': 'Android · contoh', 'remote': True},
        'state': {
            'verification_mode': True, 'phase': phase, 'busy': phase == 'thinking',
            'route_choices': ['Tanpa AI', 'RTX 4050', 'Dual GPU'], 'route': 'Dual GPU',
            'dual': True, 'spoken': True, 'language': 'ja',
            'activity': 'Siap menerima tugas · data uji',
            'mic': {'rms_db': -44, 'text': 'Contoh telemetri mikrofon laptop'},
            'output_level': .12 if phase == 'speaking' else 0,
            'hardware': {'cpu_percent': 12, 'ram_used_gib': 18.4, 'gpus': [
                {'name': 'NVIDIA GeForce RTX 4050 Laptop GPU', 'used_mib': 1600, 'total_mib': 6141},
                {'name': 'NVIDIA GeForce RTX 5070', 'used_mib': 2100, 'total_mib': 12227},
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
        if path == '/api/state':
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
            if name not in {'index.html', 'style.css', 'app.js', 'mobile.js', 'graph.js', 'physics.js', 'icon.svg', 'manifest.webmanifest'}:
                self.send_error(404)
                return
            mime = 'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'image/svg+xml' if name.endswith('.svg') else 'application/manifest+json' if name.endswith('.webmanifest') else 'text/javascript'
            self.send((ASSETS / name).read_bytes(), mime)

    def do_POST(self):
        global revision, phase
        data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path != '/api/commands':
            self.send_error(404)
            return
        with lock:
            job = {'id': data['id'], 'kind': data['kind'], 'goal': data.get('value'), 'status': 'completed', 'detail': 'Diterima fixture tampilan, bukan agent laptop.'}
            if data['kind'] == 'chat':
                messages.extend([{'speaker': 'Anda', 'text': data['value']}, {'speaker': 'Leva · Uji', 'text': 'Pesan uji diterima. Tidak ada inferensi atau tindakan PC.'}])
                jobs.insert(0, job)
            elif data['kind'] == 'pause':
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
