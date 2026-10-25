"""Start the pinned local gateway on demand; never terminate an external gateway."""
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from paths import DATA
from windows_runtime import ProcessJob

RUNTIME=DATA/'runtime/9router'
SERVER=RUNTIME/'inspected/package/app/custom-server.js'


def reachable(url='http://127.0.0.1:20128/v1'):
    from router_provider import base_url,NoRedirect
    try:
        request=urllib.request.Request(base_url(url)+'/models')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=2):return True
    except urllib.error.HTTPError as error:
        ready=error.code in (401,403);error.close();return ready
    except (ValueError,OSError,urllib.error.URLError):return False


class RouterGateway:
    def __init__(self):self.process=None;self.job=None;self.lock=threading.Lock()
    @property
    def owned(self):return self.process is not None and self.process.poll() is None
    def start(self,url):
        from router_provider import base_url
        url=base_url(url)
        with self.lock:
            if reachable(url):return 'Gateway tersedia · '+('dimiliki Leva' if self.owned else 'proses terpisah')
            if url!='http://127.0.0.1:20128/v1':raise ValueError('Mulai otomatis hanya untuk endpoint standar 127.0.0.1:20128.')
            node=shutil.which('node')
            if not node or not SERVER.is_file():raise ValueError('Runtime 9Router/Node belum tersedia.')
            env=os.environ.copy();env.update(DATA_DIR=str(RUNTIME/'data'),HOSTNAME='127.0.0.1',PORT='20128',NEXT_TELEMETRY_DISABLED='1')
            p=subprocess.Popen([node,str(SERVER)],cwd=SERVER.parent,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:job=ProcessJob(p)
            except OSError:p.terminate();raise
            self.process=p;self.job=job
        until=time.monotonic()+8
        while time.monotonic()<until and self.process is p and p.poll() is None:
            if reachable(url):return 'Gateway siap di 127.0.0.1:20128 · dimiliki Leva'
            time.sleep(.15)
        if self.process is not p:raise ValueError('Gateway dibatalkan.')
        raise ValueError('Gateway belum siap; periksa runtime 9Router.')
    def stop(self):
        with self.lock:
            if self.job:self.job.close();self.job=None
            p=self.process;self.process=None
            if p:
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.terminate()
