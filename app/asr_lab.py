"""Loopback evaluation server. Audio/reference data persists locally; no agent actions."""
import argparse
import base64
import csv
from datetime import datetime,timezone
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import wave

from paths import DATA
from asr_lab_metrics import PROMPTS,CONTEXT,score,summary
from speech_asr import ASR_PYTHON,ready

ROOT=DATA/'evaluation/asr-lab'
WEB=Path(__file__).resolve().parent/'asr_lab_web'
def now():return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self,root=ROOT):
        self.root=Path(root);self.audio=self.root/'audio';self.audio.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'evaluations.sqlite3';self.lock=threading.RLock()
        self.db=sqlite3.connect(self.path,check_same_thread=False);self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,data TEXT NOT NULL);CREATE TABLE IF NOT EXISTS reviews(id TEXT,at TEXT,data TEXT);')
    def save(self,row):
        with self.lock,self.db:self.db.execute('INSERT INTO runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(row['id'],json.dumps(row,ensure_ascii=False)))
    def __enter__(self):return self
    def __exit__(self,*args):self.db.close()
    def get(self,ident):
        with self.lock:row=self.db.execute('SELECT data FROM runs WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('run_not_found')
        return json.loads(row[0])
    def rows(self):
        with self.lock:return sorted([json.loads(r[0]) for r in self.db.execute('SELECT data FROM runs')],key=lambda r:r.get('created_at',''),reverse=True)
    def audit(self):
        with self.lock:return [{'id':r[0],'at':r[1],'change':json.loads(r[2])} for r in self.db.execute('SELECT id,at,data FROM reviews ORDER BY rowid')]
    def recover(self):
        for row in self.rows():
            if row['status']=='running':row.update(status='interrupted',error='Server berhenti sebelum hasil tersimpan.',finished_at=now());self.save(row)
    def audio_path(self,row):
        path=(self.audio/row['audio_file']).resolve()
        if not path.is_relative_to(self.audio.resolve()) or not path.is_file():raise ValueError('audio_missing')
        return path
    def review(self,ident,values):
        row=self.get(ident)
        if row['status']!='done':raise ValueError('result_not_ready')
        reference=values.get('reference',row['reference'])
        if not isinstance(reference,str) or len(reference)>1200:raise ValueError('reference_too_long')
        review=values.get('review','unreviewed');notes=values.get('notes','')
        if review not in ('unreviewed','correct','miss','uncertain') or not isinstance(notes,str) or len(notes)>2000:raise ValueError('invalid_review')
        with self.lock,self.db:self.db.execute('INSERT INTO reviews VALUES(?,?,?)',(ident,now(),json.dumps({'previous_reference':row['reference'],'submitted':values},ensure_ascii=False)))
        row.update(reference=reference,reference_confirmed=values.get('reference_confirmed') is True,review=review,notes=notes,
                   metrics=score(reference,row['result']['text'],row['critical']),reviewed_at=now())
        self.save(row);return row

def hardware():
    import psutil
    ram=psutil.virtual_memory();gpus=[];error=None
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,clocks.current.sm','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=0x08000000)
        if p.returncode:raise OSError('nvidia-smi failed')
        for row in csv.reader(p.stdout.splitlines()):
            if len(row)!=8:continue
            def number(x):
                try:return float(x.strip())
                except ValueError:return None
            gpus.append(dict(zip(('uuid','name','used_mib','total_mib','utilization_percent','temperature_c','power_watts','sm_clock_mhz'),[row[0].strip(),row[1].strip(),*[number(x) for x in row[2:]]])))
    except (OSError,subprocess.TimeoutExpired) as e:error=type(e).__name__
    return {'at':now(),'cpu_system_percent':psutil.cpu_percent(),'ram_system_used_mib':round(ram.used/2**20,1),
            'ram_system_total_mib':round(ram.total/2**20,1),'gpus':gpus,'gpu_query_error':error}

class Monitor:
    def __init__(self,manager):
        self.manager=manager;self.samples=[];self.stop_event=threading.Event();self.phase='startup';self.started=time.perf_counter()
    def sample(self):
        import psutil
        t=time.perf_counter();row=hardware();row['elapsed_ms']=round((t-self.started)*1000,1);row['phase']=self.phase
        row['worker_rss_mib']=None;row['worker_cpu_percent_cores']=None
        process=self.manager.process
        if process:
            try:
                p=psutil.Process(process.pid);row['worker_rss_mib']=round(p.memory_info().rss/2**20,1)
                cpu=p.cpu_times();current=cpu.user+cpu.system
                old=getattr(self,'last_cpu',None)
                if old and old[0]==process.pid:row['worker_cpu_percent_cores']=round((current-old[1])/max(.001,t-old[2])*100,1)
                self.last_cpu=(process.pid,current,t)
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        row['sample_cost_ms']=round((time.perf_counter()-t)*1000,2);self.samples.append(row)
    def start(self):
        self.sample()
        def loop():
            while not self.stop_event.wait(1):self.sample()
        self.thread=threading.Thread(target=loop,daemon=True);self.thread.start()
    def finish(self):
        self.stop_event.set();self.thread.join(timeout=4);self.sample()
        def values(key):return [r[key] for r in self.samples if isinstance(r.get(key),(float,int))]
        stats={}
        for key in ('cpu_system_percent','worker_cpu_percent_cores','worker_rss_mib','ram_system_used_mib'):
            v=values(key);stats[key]={'mean':sum(v)/len(v) if v else None,'peak':max(v) if v else None}
        cards={}
        for r in self.samples:
            for gpu in r['gpus']:cards.setdefault(gpu['uuid'],[]).append(gpu)
        gpu_stats=[]
        for rows in cards.values():
            stat={'uuid':rows[0]['uuid'],'name':rows[0]['name'],'baseline_used_mib':rows[0]['used_mib']}
            for key in ('used_mib','utilization_percent','temperature_c','power_watts','sm_clock_mhz'):
                v=[r[key] for r in rows if r[key] is not None]
                stat[key]={'mean':sum(v)/len(v) if v else None,'peak':max(v) if v else None}
            gpu_stats.append(stat)
        return {'samples':self.samples,'summary':stats,'gpus':gpu_stats,'interval_seconds':1,
            'note':'GPU/utilisasi/daya/RAM sistem mencakup aplikasi lain. RSS/CPU worker khusus proses ASR; CPU worker 100% = satu logical core. Sampling dapat melewatkan puncak singkat; torch peak VRAM diukur engine terpisah. Monitoring menambah overhead.'}

class Worker:
    def __init__(self):self.process=None;self.job=None;self.gpu=None;self.lock=threading.RLock();self.events=queue.Queue()
    def stop(self):
        with self.lock:
            process,job=self.process,self.job;self.process=self.job=None;self.gpu=None
            if job:job.close()
            if process:
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
                for stream in (process.stdin,process.stdout):
                    try:stream.close()
                    except (OSError,ValueError):pass
    def run(self,row,path,cold=False,on_phase=lambda phase:None):
        with self.lock:
            if cold or self.gpu!=row['gpu'] or (self.process and self.process.poll() is not None):self.stop()
            if self.process is None:
                from windows_runtime import ProcessJob
                self.events=queue.Queue();events=self.events
                self.log=(ROOT/'worker.log').open('a',encoding='utf-8')
                try:
                    self.process=subprocess.Popen([str(ASR_PYTHON),'-B','-u',str(Path(__file__).with_name('asr_lab_worker.py'))],
                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,encoding='utf-8',creationflags=0x08000000)
                    self.job=ProcessJob(self.process)
                except Exception:self.stop();raise
                finally:self.log.close()
                process=self.process
                def read():
                    try:
                        for line in process.stdout:
                            try:events.put(json.loads(line))
                            except ValueError:pass
                    except (OSError,ValueError):pass
                    events.put({'ok':False,'error':'asr_worker_stopped'})
                threading.Thread(target=read,daemon=True).start();self.gpu=row['gpu']
            self.process.stdin.write(json.dumps({'id':row['id'],'gpu':row['gpu'],'path':str(path),'language':row['language'],'context':row['context']})+'\n');self.process.stdin.flush()
            until=time.monotonic()+180
            while time.monotonic()<until:
                try:
                    event=self.events.get(timeout=1)
                    if event.get('phase'):on_phase(event['phase']);continue
                    return event
                except queue.Empty:pass
            self.stop();raise TimeoutError('ASR melewati 180 detik')

class Lab:
    def __init__(self,store=None,worker=None):
        self.store=store or Store();self.store.recover();self.worker=worker or Worker();self.lock=threading.Lock();self.active=None
    def start(self,payload):
        if not self.lock.acquire(blocking=False):raise ValueError('lab_busy')
        try:
            prompt=next((p for p in PROMPTS if p['id']==payload.get('prompt_id','custom')),None)
            if not prompt:raise ValueError('unknown_prompt')
            reference=payload.get('reference',prompt['text'])
            if not isinstance(reference,str) or len(reference)>1200:raise ValueError('invalid_reference')
            gpu=payload.get('gpu','rtx4050');language=payload.get('language','id');condition=payload.get('condition','quiet')
            if gpu not in ('rtx4050','rtx5070','auto','dual') or language not in ('id','ja','auto') or condition not in ('quiet','fan','music','conversation','other'):raise ValueError('invalid_settings')
            ident=secrets.token_hex(12);source=None
            if payload.get('replay_id'):
                source=self.store.get(payload['replay_id']);audio=self.store.audio_path(source);raw=audio.read_bytes()
            else:
                encoded=payload.get('audio','')
                if not isinstance(encoded,str) or len(encoded)>17*1024*1024:raise ValueError('invalid_audio_size')
                raw=base64.b64decode(encoded,validate=True)
                audio=self.store.audio/(ident+'.wav')
            if len(raw)>12*1024*1024:raise ValueError('audio_too_large')
            with wave.open(io.BytesIO(raw),'rb') as wav:
                if wav.getsampwidth()!=2 or wav.getnchannels()!=1 or not 8000<=wav.getframerate()<=96000 or not .2<=wav.getnframes()/wav.getframerate()<=45 or len(wav.readframes(wav.getnframes()))!=wav.getnframes()*2:raise ValueError('invalid_wav')
            if source:
                reference=source['reference'];prompt=next(p for p in PROMPTS if p['id']==source['prompt_id']);condition=source['condition']
            else:audio.write_bytes(raw)
            metadata=payload.get('capture',{}) if not source else source.get('capture',{})
            if not isinstance(metadata,dict) or len(json.dumps(metadata))>8000:raise ValueError('invalid_capture_metadata')
            row={'id':ident,'created_at':now(),'status':'running','model':'qwen_asr_06b','gpu':gpu,'language':language,
                'prompt_id':prompt['id'],'reference':reference,'critical':prompt['critical'],
                'reference_confirmed':bool(source.get('reference_confirmed')) if source else payload.get('reference_confirmed') is True,
                'condition':condition,'equipment':source.get('equipment','headset') if source else str(payload.get('equipment','headset'))[:100],
                'audio_origin':source['audio_origin'] if source else payload.get('audio_origin','human'),
                'audio_file':audio.name,'audio_sha256':hashlib.sha256(raw).hexdigest(),'replay_of':source['id'] if source else None,
                'context':CONTEXT if payload.get('use_context',True) else '', 'cold_requested':payload.get('cold') is True,
                'capture':metadata,'review':'unreviewed','notes':''}
            if row['audio_origin'] not in ('human','synthetic','imported'):raise ValueError('invalid_audio_origin')
            self.store.save(row);self.active=ident
            def run():
                monitor=Monitor(self.worker);started=time.perf_counter()
                try:
                    monitor.start();monitor.phase='asr-worker'
                    result=self.worker.run(row,audio,row['cold_requested'],on_phase=lambda phase:setattr(monitor,'phase',phase))
                    row['result']=result
                    if not result.get('ok'):raise RuntimeError(result.get('error','asr_failed'))
                    from local_audio_core import WakePolicy
                    wake=WakePolicy().accept(result['text'],now=1000)
                    result['wake_diagnostic']={**wake,'lab_requires_wake':False,'simulation_only':True,
                        'note':'Simulasi tanpa sesi follow-up sebelumnya; tidak menjalankan perintah atau membuktikan wake word akustik.'}
                    row.update(status='done',metrics=score(reference,result['text'],prompt['critical']))
                except Exception as error:row.update(status='failed',error=str(error)[:500])
                finally:
                    try:row['resources']=monitor.finish()
                    except Exception as error:row['monitor_error']=str(error)[:200]
                    row['server_total_ms']=round((time.perf_counter()-started)*1000,2);row['finished_at']=now()
                    self.store.save(row);self.active=None;self.lock.release()
            threading.Thread(target=run,daemon=True).start();return row
        except Exception:self.lock.release();raise

def server(lab,port):
    token=secrets.token_urlsafe(32);host='127.0.0.1:'+str(port)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value,kind='application/json; charset=utf-8',extra=None):
            data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; worker-src 'self'; frame-ancestors 'none'")
            for k,v in (extra or {}).items():self.send_header(k,v)
            self.end_headers();self.wfile.write(data)
        def allowed(self):return self.headers.get('Host')==host
        def do_GET(self):
            if not self.allowed():return self.reply(403,{'error':'loopback_host_required'})
            path=self.path.split('?',1)[0]
            try:
                static={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/recorder.js':'recorder.js'}
                if path in static:
                    name=static[path];data=(WEB/name).read_bytes()
                    if name=='index.html':data=data.replace(b'__TOKEN__',token.encode())
                    kind='text/html; charset=utf-8' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'application/javascript'
                    return self.reply(200,data,kind)
                if path=='/api/state':return self.reply(200,{'active':lab.active,'loaded':bool(lab.worker.process and lab.worker.process.poll() is None),'selected_gpu':lab.worker.gpu,'model_ready':ready('qwen_asr_06b'),'prompts':PROMPTS,'context':CONTEXT,'storage':str(lab.store.root)})
                if path=='/api/runs':
                    rows=lab.store.rows();compact=[]
                    for row in rows:
                        public={**row}
                        if row.get('resources'):public['resources']={k:v for k,v in row['resources'].items() if k!='samples'}
                        compact.append(public)
                    return self.reply(200,{'runs':compact,'summary':summary(rows)})
                match=re.fullmatch(r'/api/run/([0-9a-f]{24})',path)
                if match:return self.reply(200,lab.store.get(match[1]))
                if path=='/api/export.json':return self.reply(200,{'exported_at':now(),'runs':lab.store.rows(),'reference_revisions':lab.store.audit(),'summary':summary(lab.store.rows())},extra={'Content-Disposition':'attachment; filename="leva-asr-evaluations.json"'})
                if path=='/api/export.csv':
                    output=io.StringIO();fields=['id','created_at','status','model','gpu','gpu_name','model_reused','audio_sha256','replay_of','audio_origin','condition','equipment','reference_confirmed','reference','hypothesis','wer','cer','substitution','deletion','insertion','critical_missing','asr_ms','model_init_total_ms','preprocess_ms','server_total_ms','real_time_factor','torch_peak_allocated_mib','review','notes']
                    writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
                    for row in lab.store.rows():
                        flat={**row,**row.get('metrics',{}),**row.get('result',{}),'hypothesis':row.get('result',{}).get('text','')}
                        safe={k:flat.get(k,'') for k in fields}
                        for k,v in safe.items():
                            if isinstance(v,str) and v.startswith(('=','+','-','@')):safe[k]="'"+v
                        writer.writerow(safe)
                    return self.reply(200,('\ufeff'+output.getvalue()).encode(),'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="leva-asr-evaluations.csv"'})
                match=re.fullmatch(r'/api/audio/([0-9a-f]{24})',path)
                if match:return self.reply(200,lab.store.audio_path(lab.store.get(match[1])).read_bytes(),'audio/wav')
                return self.reply(404,{'error':'not_found'})
            except (OSError,ValueError):return self.reply(404,{'error':'not_found'})
        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Leva-Lab')!=token or self.headers.get('Origin') not in (None,'http://'+host):return self.reply(403,{'error':'local_session_required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<18*1024*1024 or not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('invalid_body')
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict):raise ValueError('invalid_payload')
                if self.path=='/api/run':return self.reply(202,lab.start(payload))
                if self.path=='/api/review':return self.reply(200,lab.store.review(payload['id'],payload))
                if self.path=='/api/release':
                    if lab.active:raise ValueError('lab_busy')
                    lab.worker.stop();return self.reply(200,{'released':True})
                return self.reply(404,{'error':'not_found'})
            except (ValueError,KeyError,TypeError) as error:return self.reply(400,{'error':str(error)[:200]})
    http=ThreadingHTTPServer(('127.0.0.1',port),Handler);http.daemon_threads=True;return http

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8771);args=parser.parse_args()
    lab=Lab();http=server(lab,args.port)
    print('Leva ASR Lab: http://127.0.0.1:'+str(args.port),flush=True)
    try:http.serve_forever()
    finally:lab.worker.stop();http.server_close()

if __name__=='__main__':main()
