"""Real, isolated GPU/RPC vs replica benchmark. No desktop tools or cloud upload.

All endpoints and RPC workers created here bind only to loopback. The same model,
prompts, sampling, context and token limits are used within each comparison.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import statistics
import subprocess
import threading
import time
import urllib.request

RUNTIME=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4')
MODELS=Path(r'D:\AI\AI Lokal Asisten\AI Models')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\topology-benchmark-20261023')
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def acquire_gpu_lock(path):
    """OS-held lock prevents two benchmark coordinators sharing the same GPUs."""
    import msvcrt
    path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b')
    if path.stat().st_size==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        handle.close();raise RuntimeError('another_gpu_benchmark_is_running') from None
    return handle
CASES=[
    ('math','Hitung 17 dikali 24. Balas hanya JSON dengan key hasil.',{'hasil':408}),
    ('intent','Ubah perintah menjadi JSON, jangan jalankan: buka Chrome profil Diska ke https://chatgpt.com . Gunakan key aplikasi (chrome), profil, url.',{'aplikasi':'chrome','profil':'Diska','url':'https://chatgpt.com'}),
    ('schedule','Balas hanya JSON: ingatkan belajar matematika dua menit lagi. Key delay_detik dan tugas. Tugas bernilai matematika.',{'delay_detik':120,'tugas':'matematika'}),
    ('long_context','Baca catatan berikut. '+('Catatan umum ini tidak memiliki kode rahasia. '*55)+' Kode pengujian yang benar adalah LEVA-7319. Balas hanya JSON dengan key kode.',{'kode':'LEVA-7319'}),
    ('explanation','Jelaskan dalam bahasa Indonesia tiga langkah memeriksa hasil website lokal. Tepat tiga kalimat, total sekitar 50 kata. Jangan mengaku telah menjalankan tugas.',None),
]

def percentile(values,p):
    if not values:return None
    xs=sorted(values);i=(len(xs)-1)*p;lo=int(i);hi=min(lo+1,len(xs)-1)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)

def exact_check(text,expected):
    if expected is None:return None
    try:
        match=re.search(r'\{.*\}',text,re.S)
        return json.loads(match.group() if match else text)==expected
    except (ValueError,TypeError):return False

def parse_buffers(log):
    return [{'device':m[1],'mib':float(m[2])} for m in re.finditer(r'load_tensors:\s*(\S+) model buffer size\s*=\s*([\d.]+) MiB',log)]

def rpc_placement_proven(buffers,endpoints):
    gpu=[b for b in buffers if b['mib']>0 and ('CUDA' in b['device'] or 'RPC' in b['device'])]
    return bool(gpu) and not any('CUDA' in b['device'] for b in gpu) and all(any('['+endpoint+']' in b['device'] for b in gpu) for endpoint in endpoints)

def snapshot():
    result=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu,clocks.sm','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,creationflags=FLAGS)
    rows=[]
    for line in result.stdout.splitlines():
        v=[s.strip() for s in line.split(',')]
        if len(v)==8:rows.append(dict(zip(('uuid','name','total_mib','free_mib','used_mib','utilization','temperature_c','clock_mhz'),[v[0],v[1],*[int(x) for x in v[2:]]])))
    if len(rows)!=2:raise RuntimeError('expected_two_gpus')
    return rows

def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def environment(uuids):
    # Inference subprocesses do not inherit unrelated provider credentials.
    env=os.environ.copy()
    for name in list(env):
        if any(s in name.upper() for s in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN')):env.pop(name,None)
    env['CUDA_VISIBLE_DEVICES']=','.join(uuids) if uuids else '-1'
    return env

class OwnedProcesses:
    def __init__(self,folder):self.folder=folder;self.processes=[];self.logs=[]
    def spawn(self,args,env,name):
        log=(self.folder/(name+'.log')).open('w',encoding='utf8');self.logs.append(log)
        p=subprocess.Popen([str(x) for x in args],stdout=log,stderr=log,env=env,creationflags=FLAGS)
        self.processes.append(p);return p
    def close(self):
        for p in reversed(self.processes):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=12)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        for log in self.logs:log.close()

class Monitor:
    def __init__(self,owned):self.owned=owned;self.rows=[];self.event=threading.Event()
    def run(self):
        import psutil
        psutil.cpu_percent()
        while not self.event.is_set():
            try:
                rss=0
                for proc in self.owned.processes:
                    try:rss+=psutil.Process(proc.pid).memory_info().rss if proc.poll() is None else 0
                    except psutil.Error:pass
                self.rows.append({'at':time.time(),'gpus':snapshot(),'system_cpu_percent':psutil.cpu_percent(),'system_ram_used_gib':psutil.virtual_memory().used/1024**3,'owned_rss_mib':rss/1024**2})
            except Exception as error:self.rows.append({'error':type(error).__name__})
            self.event.wait(1)
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def stop(self):self.event.set();self.thread.join(timeout=10)

def discover(env,rpc=''):
    args=[str(RUNTIME/'llama-server.exe')]
    if rpc:args+=['--rpc',rpc]
    args+=['--list-devices']
    result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=30,creationflags=FLAGS)
    if result.returncode:raise RuntimeError('device_discovery_failed')
    text=result.stdout+'\n'+result.stderr
    devices=[]
    for line in text.splitlines():
        match=re.match(r'\s*(\S+): (.+?) \((\d+) MiB, (\d+) MiB free\)',line)
        if match:devices.append({'device':match[1],'name':match[2],'free_mib':int(match[4])})
    if not devices:raise RuntimeError('no_accelerator_devices')
    return devices,text

def start_rpc(owned,uuid,label):
    p=port();proc=owned.spawn([RUNTIME/'ggml-rpc-server.exe','--host','127.0.0.1','--port',p,'--device','CUDA0','--threads','4'],environment([uuid]),label)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise RuntimeError('rpc_exited')
        try:
            with socket.create_connection(('127.0.0.1',p),timeout=.3):return '127.0.0.1:'+str(p)
        except OSError:time.sleep(.2)
    raise RuntimeError('rpc_start_timeout')

def start_server(owned,model,uuids,label,rpc='',parallel=1):
    env=environment(uuids);key=secrets.token_urlsafe(32);env['LLAMA_API_KEY']=key
    if rpc:
        # This pinned version's --list-devices prints before RPC registration.
        # RPC indices follow endpoint order; derive remote memory from worker logs.
        devices=[];raw='RPC devices from live worker announcements\n'
        for i,worker in enumerate(('rpc4050','rpc5070')):
            text=(owned.folder/(worker+'.log')).read_text('utf8',errors='replace')
            match=re.search(r'CUDA0: (.+?) \((\d+) MiB, (\d+) MiB free\)',text)
            if not match:raise RuntimeError('rpc_worker_device_unproven')
            devices.append({'device':'RPC'+str(i),'name':match[1],'free_mib':int(match[3])})
            raw+=match.group()+'\n'
    else:devices,raw=discover(env)
    (owned.folder/(label+'-devices.txt')).write_text(raw,encoding='utf8')
    p=port();url='http://127.0.0.1:'+str(p)
    ids=[d['device'] for d in devices]
    # Logically explicit budgets, kept below the live free VRAM of every device.
    budgets=[max(1,d['free_mib']-640) for d in devices]
    args=[RUNTIME/'llama-server.exe',*(['--rpc',rpc] if rpc else []),'--model',model,'--host','127.0.0.1','--port',p,
        '--device',','.join(ids),'--gpu-layers','auto','--fit','on','--fit-target','640','--fit-ctx','2048',
        '--split-mode','layer' if len(ids)>1 else 'none','--ctx-size',str(2048*parallel),'--parallel',parallel,
        '--threads','4','--threads-batch','4','--batch-size','256','--ubatch-size','128',
        '--cache-type-k','q8_0','--cache-type-v','q8_0','--reasoning-budget','0',
        '--cache-ram','0','--no-webui','-lv','4']
    if len(ids)>1:args+=['--tensor-split',','.join(map(str,budgets))]
    proc=owned.spawn(args,env,label)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise RuntimeError('inference_server_exited')
        try:
            with OPENER.open(urllib.request.Request(url+'/health',headers={'Authorization':'Bearer '+key}),timeout=.7) as response:
                if json.load(response).get('status')=='ok':
                    log=(owned.folder/(label+'.log')).read_text('utf8',errors='replace')
                    buffers=parse_buffers(log)
                    gpu_buffers=[b for b in buffers if ('CUDA' in b['device'] or 'RPC' in b['device']) and b['mib']>0]
                    if len(gpu_buffers)<len(ids):raise RuntimeError('requested_gpu_placement_not_proven')
                    if rpc and not rpc_placement_proven(buffers,rpc.split(',')):
                        raise RuntimeError('rpc_requested_but_local_cuda_used')
                    return {'url':url,'key':key,'pid':proc.pid,'devices':devices,'model_buffers':buffers,'rpc':bool(rpc)}
        except (OSError,ValueError):pass
        time.sleep(.2)
    raise RuntimeError('inference_start_timeout')

def request(server,case,index=0,round_number=0):
    name,prompt,expected=case
    started=time.perf_counter();first=None;answer='';reasoning='';timings={};usage={};finish=None;chunks=0
    payload={'messages':[{'role':'system','content':'Kamu Leva. Ikuti format yang diminta. Ini hanya benchmark teks tanpa alat.'},
        {'role':'user','content':prompt}], 'max_tokens':192,'temperature':0,'seed':1234,'stream':True,
        'stream_options':{'include_usage':True},'cache_prompt':False,'chat_template_kwargs':{'enable_thinking':False}}
    row={'case':name,'index':index,'round':round_number}
    try:
        req=urllib.request.Request(server['url']+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+server['key']})
        with OPENER.open(req,timeout=100) as response:
            for line in response:
                if time.perf_counter()-started>100:raise TimeoutError('request_total_deadline')
                if not line.startswith(b'data:'):continue
                data=line[5:].strip()
                if data==b'[DONE]':break
                item=json.loads(data);timings=item.get('timings') or timings;usage=item.get('usage') or usage
                for choice in item.get('choices',[]):
                    delta=choice.get('delta',{});text=delta.get('content') or ''
                    reasoning+=delta.get('reasoning_content') or ''
                    if text:
                        if first is None:first=time.perf_counter()-started
                        answer+=text;chunks+=1
                    finish=choice.get('finish_reason') or finish
        total=time.perf_counter()-started
        row.update(status='ok' if answer and finish=='stop' else 'incomplete',answer=answer,reasoning_characters=len(reasoning),finish_reason=finish,
            ttft_ms=round(first*1000,3) if first is not None else None,total_ms=round(total*1000,3),timings=timings,usage=usage,
            sse_content_chunks=chunks,exact_pass=exact_check(answer,expected),completed_tokens=usage.get('completion_tokens') or timings.get('predicted_n'))
    except Exception as error:row.update(status='error',error=type(error).__name__,total_ms=round((time.perf_counter()-started)*1000,3),answer=answer,exact_pass=False if expected else None)
    return row

def summarize(row):
    requests=row.get('requests',[]);ok=[r for r in requests if r.get('status')=='ok']
    exact=[r['exact_pass'] for r in requests if r.get('exact_pass') is not None]
    decode=[r['timings'].get('predicted_per_second') for r in ok if r.get('timings',{}).get('predicted_per_second') is not None]
    return {'n':len(requests),'complete':len(ok),'exact_checks_passed':sum(exact),'exact_checks_total':len(exact),
        'ttft_p50_ms':percentile([r['ttft_ms'] for r in ok if r.get('ttft_ms') is not None],.5),
        'ttft_p95_ms':percentile([r['ttft_ms'] for r in ok if r.get('ttft_ms') is not None],.95),
        'total_p50_ms':percentile([r['total_ms'] for r in ok],.5),'decode_tps_p50':percentile(decode,.5),
        'batch_makespan_p50_ms':percentile(row.get('batch_makespan_ms',[]),.5)}

def run_profile(model,name,folder,gpus,repeats,workload):
    folder.mkdir(parents=True,exist_ok=True);owned=OwnedProcesses(folder);monitor=Monitor(owned)
    row={'name':name,'status':'starting','requests':[],'batch_makespan_ms':[],'workload':workload,'loopback_only':True,'cloud':False}
    exceeded=threading.Event()
    def watchdog():
        exceeded.set()
        for proc in list(owned.processes):
            try:
                if proc.poll() is None:proc.terminate()
            except OSError:pass
    guard=threading.Timer(240,watchdog);guard.daemon=True;guard.start()
    def checkpoint():
        (folder/'progress.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    started=time.perf_counter();monitor.start()
    try:
        g4050=next(g['uuid'] for g in gpus if '4050' in g['name']);g5070=next(g['uuid'] for g in gpus if '5070' in g['name'])
        if name=='rpc_dual':
            endpoints=[start_rpc(owned,g4050,'rpc4050'),start_rpc(owned,g5070,'rpc5070')]
            servers=[start_server(owned,model,[],'main',rpc=','.join(endpoints),parallel=2 if workload=='batch' else 1)]
        elif name=='replicas':
            # Concurrent startup; allocation pinned to one physical GPU per worker.
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(start_server,owned,model,[gpu],'replica'+str(i)) for i,gpu in enumerate([g4050,g5070])]
                servers=[f.result() for f in futures]
        else:servers=[start_server(owned,model,[g5070] if name=='gpu5070' else [g4050,g5070],'main',parallel=2 if workload=='batch' else 1)]
        row['startup_s']=time.perf_counter()-started
        row['placement']=[{k:v for k,v in server.items() if k not in ('url','key')} for server in servers]
        row['first_request_excluded']=request(servers[-1],CASES[0],round_number=-1)
        checkpoint()
        if row['first_request_excluded']['status']!='ok':raise RuntimeError('warmup_failed')
        if len(servers)>1:
            row['second_worker_warmup_excluded']=request(servers[0],CASES[0],round_number=-1)
            checkpoint()
            if row['second_worker_warmup_excluded']['status']!='ok':raise RuntimeError('second_warmup_failed')
        for repeat in range(repeats):
            if workload=='serial':
                for i,case in enumerate(CASES):
                    result=request(servers[-1],case,i,repeat);row['requests'].append(result);checkpoint()
                    if exceeded.is_set():raise TimeoutError('profile_watchdog_240_seconds')
                    if result['status']=='error':raise RuntimeError('request_failed_stop_profile')
            else:
                # Equal two in-flight requests: two slots in one shared model,
                # or one slot on each replica. Same per-slot context budget.
                pending=list(enumerate(CASES));lock=threading.Lock();results=[]
                def worker(server):
                    while True:
                        with lock:
                            if not pending:return
                            i,case=pending.pop(0);queued=time.perf_counter()
                        result=request(server,case,i,repeat)
                        result['queue_wait_ms']=(queued-batch_start)*1000
                        result['end_to_end_ms']=result['queue_wait_ms']+result['total_ms']
                        with lock:results.append(result)
                batch_start=time.perf_counter()
                lanes=servers if len(servers)>1 else [servers[0],servers[0]]
                with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,lanes))
                row['batch_makespan_ms'].append((time.perf_counter()-batch_start)*1000)
                row['requests'].extend(sorted(results,key=lambda r:r['index']))
                checkpoint()
                if exceeded.is_set():raise TimeoutError('profile_watchdog_240_seconds')
        row['status']='completed';row['summary']=summarize(row)
    except Exception as error:row.update(status='failed',error=type(error).__name__+': '+str(error)[:180])
    finally:
        guard.cancel();owned.close();monitor.stop();row['telemetry']=monitor.rows
        row['summary']=summarize(row)
        row['all_owned_processes_released']=all(p.poll() is not None for p in owned.processes)
        row['elapsed_s']=time.perf_counter()-started
        (folder/'result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    return row

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--label',required=True)
    parser.add_argument('--out',type=Path,default=OUT);parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--profiles',nargs='+',choices=['gpu5070','native_dual','rpc_dual','replicas'],default=['rpc_dual','gpu5070','native_dual','replicas'])
    parser.add_argument('--workloads',nargs='+',choices=['serial','batch'],default=['serial','batch']);args=parser.parse_args()
    if args.repeats<1 or args.repeats>10:parser.error('repeats 1..10')
    if not args.model.is_file():parser.error('model missing')
    gpu_lock=acquire_gpu_lock(OUT/'exclusive-gpu.lock')
    run=args.out/args.label
    run.mkdir(parents=True,exist_ok=False)
    with args.model.open('rb') as f:model_hash=hashlib.file_digest(f,'sha256').hexdigest()
    with (RUNTIME/'llama-server.exe').open('rb') as f:runtime_hash=hashlib.file_digest(f,'sha256').hexdigest()
    proof={'created_utc':datetime.now(timezone.utc).isoformat(),'model':str(args.model),'model_sha256':model_hash,
        'runtime':'b11721-cuda13.4','runtime_sha256':runtime_hash,'context_per_slot':2048,'batch_concurrency':2,'max_tokens':192,'seed':1234,
        'temperature':0,'cache_prompt':False,'speculative_decoding':False,'repeats':args.repeats,'gpus_before':snapshot(),
        'scope':'real loopback RPC; no WAN measurements; existing background applications remain running',
        'cloud_status':{'colab':'blocked_free_tier_distributed_worker','kaggle':'not_connected'},'profiles':[]}
    def save():(run/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    save()
    try:
        for profile in args.profiles:
            for workload in args.workloads:
                print(json.dumps({'phase':'starting','profile':profile,'workload':workload}),flush=True)
                row=run_profile(args.model,profile,run/(profile+'-'+workload),snapshot(),args.repeats,workload)
                proof['profiles'].append(row);save()
                print(json.dumps({'phase':row['status'],'profile':profile,'workload':workload,'summary':row.get('summary'),'error':row.get('error')}),flush=True)
    finally:
        try:proof['gpus_after']=snapshot();save()
        finally:gpu_lock.close()

if __name__=='__main__':main()
