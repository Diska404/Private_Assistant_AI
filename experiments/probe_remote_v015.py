"""Integration proof on an owned headless browser and local fixture; never personal tabs."""
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from browser_runtime import BrowserRuntime
from file_workspace import FileWorkspace
from spoken_text import prepare_spoken_text
from system_controls import control

HTML=b'''<!doctype html><html><head><title>Leva local verification</title></head><body><h1>Local test</h1><label>Name<input name="name" aria-label="Name"></label><label>Password<input type="password" value="fixture-private"></label><button type="button" onclick="document.getElementById('result').textContent='Saved '+document.querySelector('input').value">Save local preview</button><form><button>Submit external</button></form><p id="result">Not saved</p></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(HTML)
    def log_message(self,*args):pass

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\remote-v015');out.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    proof={'date':datetime.now().astimezone().isoformat(),'scope':'owned headless Edge, loopback fixture, temporary files; no personal browser/session input','checks':{}}
    start=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='leva-v015-') as folder:
            browser=BrowserRuntime(headless=True,profile=Path(folder)/'edge')
            try:
                opened=browser.run({'action':'open','browser':'edge','url':f'http://127.0.0.1:{server.server_port}/'})
                tab=opened['tab'];proof['checks']['browser_open']=opened['status']=='done'
                proof['checks']['password_omitted']=not any(r['type']=='password' for r in opened['elements']) and 'fixture-private' not in opened['content']
                field=next(r for r in opened['elements'] if r['tag']=='input')
                typed=browser.run({'action':'fill','tab':tab,'element':field['element'],'text':'Leva verification'})
                proof['checks']['fill_dispatched']=typed['status']=='dispatched'
                observed=browser.run({'action':'inspect','tab':tab})
                proof['checks']['fill_verified']=any(r.get('value')=='Leva verification' for r in observed['elements'])
                button=next(r for r in observed['elements'] if r['label']=='Save local preview')
                browser.run({'action':'click','tab':tab,'element':button['element']})
                observed=browser.run({'action':'inspect','tab':tab});proof['checks']['click_verified']='Saved Leva verification' in observed['content']
                submit=next(r for r in observed['elements'] if r['label']=='Submit external')
                proof['checks']['submission_not_automatic']=browser.run({'action':'click','tab':tab,'element':submit['element']})['status']=='needs_input'
                proof['checks']['tabs_observed']=bool(browser.run({'action':'tabs'})['tabs'])
            finally:browser.stop()
            root=Path(folder)/'files';root.mkdir();files=FileWorkspace(Path(folder)/'history');files.observed.add(str(root))
            path=root/'study.txt';row=files.run({'action':'write','path':str(path),'text':'Discrete mathematics 19:00'},str(root))
            proof['checks']['real_file_write_read']='19:00' in files.run({'action':'read','path':str(path)},str(root))['content']
            files.undo(row['operation_id'],lambda:True);proof['checks']['real_file_undo']=not path.exists()
        for action in ('audio_status','display_status'):
            try:proof['device_readings' if 'device_readings' in proof else 'device_readings']=proof.get('device_readings',{})|{action:control({'action':action})}
            except Exception as error:proof.setdefault('device_readings',{})[action]={'status':'unavailable','error':type(error).__name__}
        spoken=prepare_spoken_text('Siap 😊. Baca [artikel](https://example.com). Sumber https://example.com/detail. Jam 19:00 WIB.')
        proof['checks']['speech_clean']='http' not in spoken and '😊' not in spoken and '19:00' in spoken
        proof['speech_example']=spoken
        proof['elapsed_seconds']=round(time.perf_counter()-start,3)
        (out/'integration.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(proof,ensure_ascii=True),flush=True)
        if not all(proof['checks'].values()):raise SystemExit(1)
    finally:server.shutdown();server.server_close()

if __name__=='__main__':main()
