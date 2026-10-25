"""Serve only the self-contained listening HTML on local loopback."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PAGE=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-bilingual-v3\comparison.html')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/','/comparison.html'):
            self.send_error(404)
            return
        data=PAGE.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)

if __name__=='__main__':
    print('Leva voice review: http://127.0.0.1:8766/',flush=True)
    HTTPServer(('127.0.0.1',8766),Handler).serve_forever()
