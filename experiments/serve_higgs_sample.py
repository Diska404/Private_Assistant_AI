"""Loopback preview of one self-contained listening artifact, no file browsing."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PAGE=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\higgs-naturalness-20261020\rtx4050-final\comparison.html')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/','/comparison.html'):
            self.send_error(404)
            return
        if not PAGE.is_file():
            self.send_error(503,'Samples are not ready')
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
    print('Higgs sample review: http://127.0.0.1:8767/',flush=True)
    HTTPServer(('127.0.0.1',8767),Handler).serve_forever()
