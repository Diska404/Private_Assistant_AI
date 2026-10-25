"""Owned asynchronous processes, bounded output and crash-visible receipts. No admin elevation."""
import base64
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime,timezone
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from conversation_memory import redact
from file_workspace import checked_path
from paths import DATA
from windows_runtime import ProcessJob


class TerminalService:
    def __init__(self,storage=None):
        self.storage=Path(storage) if storage else DATA/'terminal'
        self.storage.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.jobs={}
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS processes(id TEXT PRIMARY KEY,cwd TEXT,shell TEXT,code TEXT,state TEXT,exit_code INTEGER,started TEXT,output TEXT,reason TEXT)')
            db.execute("UPDATE processes SET state='interrupted',reason='Host restarted; command not replayed.' WHERE state='running'")

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.storage/'processes.sqlite3',timeout=3)
        try:
            db.row_factory=sqlite3.Row
            with db:yield db
        finally:db.close()

    def start(self,shell,code,cwd,timeout=120):
        cwd=checked_path(str(cwd))
        if not cwd.is_dir():raise ValueError('terminal_cwd_not_directory')
        if not isinstance(code,str) or not code.strip() or len(code)>3000:raise ValueError('invalid_terminal_code')
        if redact(code)!=code:raise ValueError('terminal_credentials_disallowed')
        timeout=int(timeout)
        if not 1<=timeout<=1800:raise ValueError('terminal_timeout_range_1_1800')
        if shell=='python':
            local=cwd/'.venv/Scripts/python.exe'
            python=str(local) if local.is_file() else shutil.which('python') or (sys.executable if not getattr(sys,'frozen',False) else None)
            if not python:raise ValueError('python_runtime_unavailable')
            command=[python,'-u','-c',code]
        elif shell=='powershell':
            executable=shutil.which('powershell.exe') or shutil.which('pwsh')
            if not executable:raise ValueError('powershell_unavailable')
            script="[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $OutputEncoding = [Console]::OutputEncoding; $ErrorActionPreference = 'Stop';\n"+code
            command=[executable,'-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(script.encode('utf-16-le')).decode('ascii')]
        else:raise ValueError('unsupported_terminal_shell')
        ident=uuid.uuid4().hex[:12]
        with self.lock:
            for old in list(self.jobs)[:-20]:
                if self.jobs[old]['done'].is_set():self.jobs.pop(old,None)
            if sum(job['process'].poll() is None for job in self.jobs.values())>=3:raise ValueError('terminal_process_limit_3')
            process=subprocess.Popen(command,cwd=str(cwd),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'})
            try:owner=ProcessJob(process)
            except OSError:
                process.terminate();process.wait(timeout=5);raise
            record={'process':process,'owner':owner,'output':'','reason':'','done':threading.Event(),'reader_done':threading.Event()}
            self.jobs[ident]=record
            with self.connection() as db:db.execute('INSERT INTO processes VALUES(?,?,?,?,?,?,?,?,?)',(ident,str(cwd),shell,redact(code),'running',None,datetime.now(timezone.utc).isoformat(),'',''))
        def read_output():
            import codecs
            decoder=codecs.getincrementaldecoder('utf-8')('replace')
            try:
                while True:
                    chunk=process.stdout.read1(1024)
                    if not chunk:break
                    with self.lock:record['output']=(record['output']+decoder.decode(chunk))[:8000]
                with self.lock:record['output']=(record['output']+decoder.decode(b'',final=True))[:8000]
            finally:
                process.stdout.close();record['reader_done'].set()
        def monitor():
            try:exit_code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                with self.lock:record['reason']='timeout'
                owner.close();exit_code=process.wait(timeout=5)
            finally:
                owner.close()
            record['reader_done'].wait(3)
            with self.lock:
                state='cancelled' if record['reason']=='cancelled' else 'timed_out' if record['reason']=='timeout' else 'completed' if exit_code==0 else 'failed'
                with self.connection() as db:db.execute('UPDATE processes SET state=?,exit_code=?,output=?,reason=? WHERE id=?',(state,exit_code,redact(record['output']),record['reason'],ident))
                record['done'].set()
        threading.Thread(target=read_output,daemon=True).start();threading.Thread(target=monitor,daemon=True).start()
        return {'status':'running','reply':'Proses dimulai. Poll process_id untuk hasil dan exit code; belum dinyatakan selesai.','process_id':ident,'cwd':str(cwd),'shell':shell}

    def poll(self,ident,cursor=0,wait=0):
        with self.lock:job=self.jobs.get(ident)
        if job:job['done'].wait(max(0,min(2,float(wait))))
        with self.lock:
            with self.connection() as db:row=db.execute('SELECT * FROM processes WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('terminal_process_not_owned')
            output=redact(job['output']) if job else row['output']
            cursor=max(0,min(len(output),int(cursor)));chunk=output[cursor:cursor+6000]
            state=row['state'];status='running' if state=='running' else 'done' if state=='completed' else 'cancelled' if state in ('cancelled','interrupted') else 'failed'
            identity=row['code']
            if row['shell']=='python':
                import ast
                try:identity=ast.dump(ast.parse(identity),include_attributes=False)
                except SyntaxError:pass
            command_id=hashlib.sha256((row['cwd']+'\0'+row['shell']+'\0'+identity).encode()).hexdigest()[:16]
            from development_diagnostics import diagnose
            return {'diagnostics':diagnose(output,row['exit_code']), 'status':status,'reply':'Proses '+state+'.','process_id':ident,'command_id':command_id,'state':state,'exit_code':row['exit_code'],'output':chunk,'cursor':cursor+len(chunk),'output_capped':len(output)>=8000,'reason':row['reason'],'task_verified':state=='completed','retryable':state in ('failed','timed_out'),'untrusted_data':True}

    def serve(self,cwd):
        """Owned loopback static preview; readiness is an actual byte-for-byte HTTP read."""
        import urllib.request
        cwd=checked_path(str(cwd));entry=cwd/'index.html'
        if not entry.is_file():raise ValueError('preview_index_html_missing')
        expected=entry.read_bytes()
        if len(expected)>5_000_000:raise ValueError('preview_index_html_too_large')
        code=('import http.server,json\n'
              'class Handler(http.server.SimpleHTTPRequestHandler):\n'
              '    def list_directory(self,path):\n'
              '        self.send_error(403);return None\n'
              'server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)\n'
              'print(json.dumps({"preview_url":"http://127.0.0.1:%d/index.html"%server.server_port}),flush=True)\n'
              'server.serve_forever()\n')
        started=self.start('python',code,cwd,1800);ident=started['process_id']
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                result=self.poll(ident,wait=.2)
                for line in result['output'].splitlines():
                    try:url=json.loads(line).get('preview_url','')
                    except (ValueError,AttributeError):continue
                    if not url:continue
                    import re
                    if not re.fullmatch(r'http://127\.0\.0\.1:\d+/index\.html',url):raise ValueError('preview_url_invalid')
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(url,timeout=3) as response:
                        status=response.status;body=response.read(5_000_001)
                    if status!=200 or body!=expected:raise ValueError('preview_http_content_mismatch')
                    return {'status':'done','reply':'Pratinjau statis aktif di localhost; HTTP 200 dan isi index.html cocok. Server aktif maksimal 30 menit atau sampai Leva ditutup.',
                        'url':url,'process_id':ident,'server_running':True,'http_status':status,'content_sha256':hashlib.sha256(body).hexdigest(),
                        'lifetime_seconds':1800,'task_verified':True,'cwd':str(cwd)}
                if result['status']!='running':raise ValueError('preview_process_exited')
            raise ValueError('preview_start_timeout')
        except Exception:
            self.stop(ident);raise

    def stop(self,ident):
        with self.lock:
            job=self.jobs.get(ident)
            if job and not job['done'].is_set():job['reason']='cancelled';job['owner'].close()
        return self.poll(ident,wait=2)

    def stop_all(self,wait=True):
        with self.lock:
            jobs=list(self.jobs.values())
            for job in jobs:
                if not job['done'].is_set():job['reason']='cancelled';job['owner'].close()
        if wait:
            for job in jobs:job['done'].wait(2)

    def recent(self):
        with self.connection() as db:rows=db.execute('SELECT id,cwd,shell,state,exit_code,started,reason FROM processes ORDER BY started DESC LIMIT 20').fetchall()
        return {'status':'done','reply':'Proses milik Leva; proses host lama tidak dijalankan ulang.','processes':[dict(r) for r in rows]}
