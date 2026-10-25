"""Real local inference + production agent core, with bounded test-only file/browser tools.

No microphone, speaker, external providers or real browser/app launches are used.
"""
import csv
import argparse
import json
from pathlib import Path
import queue
import re
import statistics
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from chat_service import make_local,run_worker
from agent_runtime import _run_agent
from file_workspace import FileWorkspace
from personal_models import model_path
import psutil

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\personal-models-v033')
OUT.mkdir(parents=True,exist_ok=True)
MODELS=['qwen4b','qwen3_8b','stheno8b','rpmax12b']
CASES=[
 ('chat','arithmetic','Hitung 17 × 23. Jawab hasil dan satu kalimat cara menghitungnya.'),
 ('chat','sets','A={1,2,3}, B={3,4}. Jawab hanya JSON valid dengan key union dan intersection, keduanya array angka terurut, tanpa Markdown.'),
 ('chat','source_fidelity','Ringkas catatan ini dalam dua kalimat. Catatan: uji suara selesai pada 20 Oktober; integrasi live belum diuji; unduhan model baru masih rencana. Pisahkan hal yang selesai dan belum.'),
 ('chat','no_tools','Jangan berpindah mode. Apakah kamu sudah membuka Discord untukku? Jawab jujur berdasarkan ruang Chat ini, tanpa mengaku melakukan tindakan.'),
 ('secret','support','Leva, aku lelah setelah kuliah dan belum ingin membahas tugas. Temani aku ngobrol sebentar, jangan beri daftar solusi dulu.'),
 ('secret','identity','Kalau aku memanggilmu Leva, kamu ingin menemaniku ngobrol seperti apa? Jawab alami dalam bahasa Indonesia, maksimal tiga kalimat.'),
 ('secret','memory','Sekarang sebutkan minuman dan panggilan yang barusan aku pilih, tanpa menambah hal lain.'),
 ('secret','handoff','Aku ingin kamu membuat website di laptop sekarang. Dalam ruang ini apa langkah yang tepat? Jangan mengaku sudah membuatnya.'),
 ('secret','followup','Tadi kamu bilang kita bisa istirahat sambil ngobrol. Aku ingin cerita saja, jadi dengarkan dulu ya. Balas singkat dan jangan mengulang salam.')]

def strip_json(text):
    return re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
def checks_for(case,text):
    low=text.casefold();base={'nonempty':bool(text.strip()),'no_reasoning_leak':'<think>' not in low and '</think>' not in low}
    if case=='arithmetic':base['answer_391']='391' in text
    if case=='sets':
        try:base['exact_sets']=json.loads(strip_json(text))=={'union':[1,2,3,4],'intersection':[3]}
        except ValueError:base['exact_sets']=False
    if case=='source_fidelity':base['unfinished_preserved']='belum' in low and any(w in low for w in ('rencana','direncanakan','perencanaan'))
    if case=='memory':base['both_preferences']='cokelat hangat' in low and 'raizei' in low
    if case=='support':base['no_numbered_solutions']=not re.search(r'(?m)^\s*(?:\d+[.)]|[-*])\s',text);base['bounded_length']=len(text.split())<=100
    if case=='identity':base['leva_identity']='leva' in low;base['bounded_length']=len(text.split())<=100
    if case=='handoff':base['assistant_handoff']='asisten' in low or 'assistant' in low
    if case=='followup':base['no_repeat_greeting']=not re.match(r'\s*(?:hai|halo|selamat)',low);base['bounded_length']=len(text.split())<=60
    if case=='no_tools':base['no_false_done']=not re.search(r'(?:sudah|telah|berhasil) membuka',low) or 'belum' in low or 'tidak' in low
    return base

class Monitor:
    def __init__(self):self.rows=[];self.stop=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        while not self.stop.is_set():
            row={'at':time.time(),'cpu_percent':psutil.cpu_percent(),'ram_used_bytes':psutil.virtual_memory().used,'gpus':[]}
            try:
                r=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,creationflags=0x08000000)
                row['gpus']=[{'uuid':v[0].strip(),'name':v[1].strip(),'used_mib':int(v[2]),'util_percent':int(v[3]),'temperature_c':int(v[4])} for v in csv.reader(r.stdout.splitlines()) if len(v)==5]
            except Exception:pass
            self.rows.append(row);self.stop.wait(.75)
    def start(self):self.thread.start()
    def close(self):self.stop.set();self.thread.join(6)

def agent_case(engine,key,case):
    workspace=OUT/key/('workspace-'+case+'-'+str(time.time_ns()));workspace.mkdir(parents=True,exist_ok=True)
    files=FileWorkspace(workspace/'history');files.observed.add(workspace)
    commands=queue.Queue();events=[];rid=1
    target=workspace/'memo.txt'
    goal={'time':'Periksa jam komputer sekarang menggunakan alat waktu, lalu jawab pukul berapa.',
          'browsers':'Buka https://chatgpt.com di Chrome profil Diska dan https://edlink.id di Edge. Kerjakan kedua browser, lalu laporkan hasil.',
          'files':'Buat berkas memo.txt berisi tepat LEVA-33 di workspace '+str(workspace)+'. Baca kembali berkas itu untuk memverifikasi isi. Gunakan file_action; tidak perlu terminal.'}[case]
    def emit(event):
        if event.get('kind')!='tool_call':return
        name=event['name'];args=event['args'];result=None
        try:
            if name=='get_time':result={'status':'done','reply':'Fixture jam uji, bukan jam laptop aktual: 24 Oktober 2026 pukul 10:00 WIB.','time':'2026-10-24T10:00:00+07:00','fixture':True}
            elif name=='open_browser':result={'status':'done','reply':'Fixture browser: tujuan '+args['url']+' tervalidasi; tidak membuka browser nyata.','fixture':True,'task_verified':True}
            elif name=='file_action':
                for field in ('path','destination'):
                    if args.get(field) and not Path(args[field]).resolve().is_relative_to(workspace.resolve()):raise ValueError('test_workspace_only')
                if args['action'] not in ('list','read','write','mkdir'):raise ValueError('test_file_action_not_allowed')
                result=files.run(args,goal)
            elif name=='task_plan':result={'status':'done','reply':'Rencana uji dicatat.'}
            elif name=='discover_tools':result={'status':'done','reply':'Kelompok alat uji tersedia.'}
            else:result={'status':'failed','reply':'Alat ini tidak termasuk lingkup uji. Gunakan alat yang diminta tujuan.'}
        except Exception as e:result={'status':'failed','reply':str(e)}
        events.append({'name':name,'args':args,'result':result})
        if len(events)>12:raise RuntimeError('benchmark_tool_limit')
        commands.put({'kind':'tool_result','id':rid,'call_id':event['call_id'],'result':result})
    result=_run_agent({'id':rid,'mode':'local','speech_language':'id','time_budget_seconds':120,'messages':[{'role':'user','content':goal}],
        'tool_context':{'workspace_root':str(workspace),'profiles':[{'id':'diska','name':'Diska'}]}},engine,commands,emit)
    checks={'complete':not result.get('incomplete') and not result.get('needs_input')}
    if case=='time':checks['time_tool_used']=any(r['name']=='get_time' for r in events);checks['time_preserved']='10:00' in result['response'] or '10.00' in result['response']
    if case=='browsers':
        checks['chrome_target']=any(r['name']=='open_browser' and r['args'].get('browser','chrome')=='chrome' and r['args'].get('url','').rstrip('/')=='https://chatgpt.com' and r['args'].get('profile','').casefold()=='diska' for r in events)
        checks['edge_target']=any(r['name']=='open_browser' and r['args'].get('browser')=='edge' and r['args'].get('url','').rstrip('/')=='https://edlink.id' for r in events)
    if case=='files':checks['exact_file']=target.is_file() and target.read_text('utf8').strip()=='LEVA-33';checks['read_after_write']=any(r['name']=='file_action' and r['args'].get('action')=='read' and r['result'].get('status')=='done' for r in events)
    return {'prompt':goal,'result':result,'events':events,'checks':checks}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='+');parser.add_argument('--out')
    settings=parser.parse_args()
    if settings.models:MODELS=settings.models
    if settings.out:OUT=Path(settings.out);OUT.mkdir(parents=True,exist_ok=True)
    proof={'status':'running','gpu':'RTX 5070','context_size':8192,'quant':'Q4_K_M','network_for_inference':False,'microphone':False,'speaker':False,
       'tool_scope':'production agent core; browser/time fixtures; real file I/O only inside verification workspace','models':[]}
    if (OUT/'benchmark.json').exists():proof=json.loads((OUT/'benchmark.json').read_text('utf8'));proof['status']='running'
    def save():(OUT/'benchmark.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    for key in MODELS:
        if key!='qwen4b':
            while not model_path(key).is_file():
                print(json.dumps({'waiting_for_download':key}),flush=True);time.sleep(30)
        row=next((m for m in proof['models'] if m['key']==key),None)
        if row is None:row={'key':key,'cases':[],'status':'loading'};proof['models'].append(row)
        if len(row['cases'])==12 and row['status']=='completed':continue
        done={(c['room'],c['case']) for c in row['cases']};row['status']='loading';save()
        engine=make_local({'local_model':key,'local_mode':'gpu5070','agent':True,'acceleration':'plain'})
        calls=[];original=engine.request
        def request(path,body=None,timeout=3):
            started=time.perf_counter()
            try:
                result=original(path,body,min(timeout,60) if path=='/v1/chat/completions' else timeout)
                if path=='/v1/chat/completions':calls.append({'http_ms':round((time.perf_counter()-started)*1000,2),'timings':result.get('timings',{}),'usage':result.get('usage',{}),'finish_reason':result.get('choices',[{}])[0].get('finish_reason')})
                return result
            except Exception:
                if path=='/v1/chat/completions':calls.append({'http_ms':round((time.perf_counter()-started)*1000,2),'failed':True})
                raise
        engine.request=request;monitor=Monitor();monitor.start()
        try:
            started=time.perf_counter();engine.start();row.update(cold_load_ms=round((time.perf_counter()-started)*1000,2),devices=engine.devices,visible_gpu_uuids=engine.visible_gpu_uuids,model_gpu_buffers_mib=engine.model_gpu_buffers_mib,gpu_before=engine.gpu_snapshot_before,gpu_loaded=engine.gpu_snapshot_loaded)
            print(json.dumps({'loaded':key,'ms':row['cold_load_ms']}),flush=True);save()
            for room,case,prompt in CASES:
                if (room,case) in done:continue
                started=time.perf_counter();index=len(calls);resultrow={'room':room,'case':case,'prompt':prompt}
                messages=[{'role':'user','content':prompt}]
                if case=='memory':messages=[{'role':'user','content':'Untuk obrolan ini aku memilih cokelat hangat dan panggilan Raizei.'},{'role':'assistant','content':'Baik, aku mengikuti pilihanmu untuk obrolan ini.'},*messages]
                engine.max_output_tokens=512
                try:
                    result=run_worker({'purpose':'room_'+room,'mode':'local','local_model':key,'messages':messages},engine,False)
                    resultrow.update(result=result,checks=checks_for(case,result['response']))
                except Exception as error:resultrow.update(error=str(error),checks={'inference_completed':False})
                resultrow.update(elapsed_ms=round((time.perf_counter()-started)*1000,2),inference_calls=calls[index:]);row['cases'].append(resultrow);save()
                print(json.dumps({'model':key,'room':room,'case':case,'checks':resultrow['checks'],'ms':resultrow['elapsed_ms']}),flush=True)
            for case in ('time','browsers','files'):
                if ('assistant',case) in done:continue
                started=time.perf_counter();index=len(calls);engine.max_output_tokens=2048
                engine.sampling=__import__('personal_models').sampling_for(key,'agent') if key!='qwen4b' else {'temperature':0.2}
                resultrow={'room':'assistant','case':case}
                try:resultrow.update(agent_case(engine,key,case))
                except Exception as error:resultrow.update(error=str(error),checks={'inference_completed':False})
                resultrow.update(elapsed_ms=round((time.perf_counter()-started)*1000,2),inference_calls=calls[index:]);row['cases'].append(resultrow);save()
                print(json.dumps({'model':key,'room':'assistant','case':case,'checks':resultrow['checks'],'ms':resultrow['elapsed_ms']}),flush=True)
            row['status']='completed'
        except Exception as error:row.update(status='failed',error=str(error))
        finally:
            engine.close();monitor.close();row['resource_samples']=monitor.rows;row['worker_released']=engine.process is None;save()
        print(json.dumps({'completed':key,'status':row['status']}),flush=True)
    proof['status']='completed';save()
