"""Serial, bounded local trials. All prompts/executors are synthetic; no production data."""
import ast
import csv
import json
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from hybrid_engine import LocalEngine
from benchmark_personal_models_v033 import Monitor
from vtuber_trial_cases import PERSONA,CASES,dialogue_turns
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
SERVER=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4\llama-server.exe')
IDS={'HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive':'hauhau_qwen35_4b',
     'HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive':'hauhau_qwen35_9b',
     'bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF':'rocinante_x_12b'}

def json_text(text):return re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
def code_test(text,name):
    text=re.sub(r'^```(?:python)?\s*|\s*```$','',text.strip())
    try:
        tree=ast.parse(text)
        permitted=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Return,ast.BinOp,ast.Name,ast.Load,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.UnaryOp,ast.USub,ast.Constant)
        if any(not isinstance(n,permitted) for n in ast.walk(tree)):return False
        if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!=name or tree.body[0].decorator_list:return False
        if len(tree.body[0].body)!=1 or not isinstance(tree.body[0].body[0],ast.Return):return False
        if any(isinstance(n,ast.Constant) and (not isinstance(n.value,(int,float)) or abs(n.value)>10000) for n in ast.walk(tree)):return False
        if any(isinstance(n,ast.Name) and n.id not in ('a','b') for n in ast.walk(tree)):return False
        namespace={'__builtins__':{}};exec(compile(tree,'synthetic-math-only','exec'),namespace)
        return all(namespace[name](a,b)==(a+b if name=='add' else a*b) for a,b in [(1,2),(-2,8),(0,0),(9,-4)])
    except Exception:return False

def checks(case,text):
    low=text.casefold();result={'nonempty':bool(text.strip()),'no_template_leak':not any(t in low for t in ('<think>','</think>','[inst]','[system_prompt]','<|im_start|>'))}
    for key,value in case['checks'].items():
        if key=='json':
            try:result[key]=json.loads(json_text(text))==value
            except ValueError:result[key]=False
        elif key=='python':result[key]=code_test(text,value)
        elif key=='exact':result[key]=text.strip()==value
        elif key=='must_all':result[key]=all(v.casefold() in low for v in value)
        elif key=='must_any':result[key]=any(v.casefold() in low for v in value)
        elif key=='must_not':result[key]=all(v.casefold() not in low for v in value)
        elif key=='max_words':result[key]=len(text.split())<=value
        elif key=='min_words':result[key]=len(text.split())>=value
        elif key=='max_sentences':result[key]=len([s for s in re.split(r'[.!?。！？]+',text) if s.strip()])<=value
        elif key=='no_list':result[key]=not bool(re.search(r'(?m)^\s*(?:\d+[.)]|[-*])\s',text))
        elif key=='no_greeting':result[key]=not bool(re.match(r'\s*(?:hai|halo|selamat)',low))
        elif key=='japanese':result[key]=bool(re.search(r'[\u3040-\u30ff\u4e00-\u9fff]',text))
        elif key=='no_false_action':result[key]=not bool(re.search(r'\b(?:sudah|telah|berhasil)\s+(?:membuka|menghapus|membuat|menjalankan)\b',low)) or bool(re.search(r'\b(?:belum|tidak)\b',low))
    return result

def stream(engine,messages,mode,max_tokens=256):
    system=PERSONA+'\nRuang saat ini: '+mode+'. '
    system+=('Dalam Asisten ini hanya rencana/fixture; tidak ada tool yang benar-benar dijalankan.' if mode=='assistant' else 'Tidak ada alat komputer. Jangan klaim aksi nyata.')
    started=time.perf_counter();first=None;text='';timings={};finish=None
    payload={'messages':[{'role':'system','content':system}]+messages,'max_tokens':max_tokens,
        'temperature':.25 if mode in ('assistant','chat') else .7,'top_p':.8,'top_k':20,
        'stream':True,'chat_template_kwargs':{'enable_thinking':False}}
    req=urllib.request.Request(engine.endpoint+'/v1/chat/completions',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+engine.api_key})
    with engine.opener.open(req,timeout=55) as response:
        for line in response:
            if not line.startswith(b'data: '):continue
            raw=line[6:].strip()
            if raw==b'[DONE]':break
            row=json.loads(raw);timings=row.get('timings',timings)
            for choice in row.get('choices',[]):
                token=choice.get('delta',{}).get('content') or ''
                if token and first is None:first=(time.perf_counter()-started)*1000
                text+=token;finish=choice.get('finish_reason') or finish
    reasoning_leak='<think>' in text or '</think>' in text
    if reasoning_leak:text=re.sub(r'<think>.*?</think>','[INTERNAL_REASONING_REDACTED]',text,flags=re.S)
    return {'text':text,'ttft_ms':round(first,2) if first is not None else None,'total_ms':round((time.perf_counter()-started)*1000,2),
        'finish_reason':finish,'timings':timings,'reasoning_leak_detected':reasoning_leak}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    proof={'status':'waiting_for_acquisition','context':8192,'quant':'Q4_K_M','gpu':'gpu5070','max_output_tokens':256,
        'model_order':[],'models':[],'microphone':False,'speaker':False,'real_tools_executed':False}
    def save():(OUT/'benchmark-status.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    save();wait_started=time.monotonic()
    while True:
        acquisition=json.loads((OUT/'acquisition.json').read_text('utf8'))
        if acquisition['status']=='verified':break
        if acquisition['status']=='acquisition_incomplete':raise RuntimeError('acquisition_failed')
        if time.monotonic()-wait_started>2400:raise TimeoutError('acquisition_wait_limit')
        time.sleep(10)
    sources=list(acquisition['assets']);random.Random(2410).shuffle(sources)
    proof['model_order']=[IDS[s['repo']] for s in sources];proof['status']='running';save()
    for source in sources:
        key=IDS[source['repo']];row={'id':key,'source':source,'cases':[],'dialogues':[],'native_tools':[],'status':'starting'}
        proof['models'].append(row);save()
        if psutil.virtual_memory().available<10*1024**3:row['status']='insufficient_ram_headroom';save();continue
        engine=LocalEngine(SERVER,Path(source['path']),OUT/key,mode='gpu5070',context_size=8192,
            max_output_tokens=256,thinking_budget=0,startup_timeout=100,
            extra_server_args=('--cache-type-k','q8_0','--cache-type-v','q8_0','--no-context-shift'))
        monitor=Monitor();monitor.start();done=threading.Event();start=time.monotonic()
        def guard():
            while not done.wait(1):
                if psutil.virtual_memory().available<4*1024**3 or time.monotonic()-start>1200:
                    row['guard']='ram_below_4GiB' if psutil.virtual_memory().available<4*1024**3 else 'model_time_limit';engine.close();return
                if monitor.rows and any(g['temperature_c']>=82 for g in monitor.rows[-1]['gpus']):
                    row['guard']='temperature_limit';engine.close();return
        thread=threading.Thread(target=guard,daemon=True);thread.start()
        try:
            engine.start()
            try:psutil.Process(engine.process.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            except (psutil.AccessDenied,psutil.NoSuchProcess,AttributeError):pass
            row.update(status='loaded',load_seconds=engine.load_seconds,devices=engine.devices,gpu_buffers_mib=engine.model_gpu_buffers_mib);save()
            (OUT/(key+'-template.json')).write_text(json.dumps(engine.request('/props',timeout=5),indent=2),encoding='utf8')
            errors=0
            for trial in range(3):
                ordered=list(CASES);random.Random(2410+trial).shuffle(ordered)
                for case in ordered:
                    result={'case_id':case['id'],'trial':trial,'mode':case['mode'],'prompt':case['prompt']}
                    try:
                        result.update(stream(engine,[{'role':'user','content':case['prompt']}],case['mode']))
                        result['checks']=checks(case,result['text'])
                    except Exception as error:
                        result['error']=type(error).__name__+':'+str(error)[:240];errors+=1
                    row['cases'].append(result)
                    with (OUT/'results.jsonl').open('a',encoding='utf8') as file:file.write(json.dumps({'model':key,**result},ensure_ascii=False)+'\n')
                    save()
                    if errors>=3 or row.get('guard'):raise RuntimeError('request_failures_or_resource_guard')
                    time.sleep(.15)
                print(json.dumps({'model':key,'trial_completed':trial,'cases':len(row['cases'])}),flush=True)
                time.sleep(2)
            for session in range(3):
                history=[];dialogue={'session':session,'turns':[]};row['dialogues'].append(dialogue)
                for turn,prompt in enumerate(dialogue_turns(session)):
                    history.append({'role':'user','content':prompt})
                    result=stream(engine,history,'companion_avatar',max_tokens=128)
                    dialogue['turns'].append({'turn':turn+1,'prompt':prompt,**result})
                    history.append({'role':'assistant','content':result['text']})
                    save();time.sleep(.15)
                print(json.dumps({'model':key,'dialogue_completed':session,'turns':40}),flush=True)
            # Native tool gates are proposals only. There is no computer executor.
            engine.system=PERSONA+' Dalam uji ini gunakan alat fixture yang disediakan.'
            for name,prompt,properties in [('get_time','Gunakan get_time untuk membaca waktu fixture.',{}),
                ('open_browser','Gunakan open_browser untuk profil Work dan URL https://youtube.com.',{'profile':{'type':'string'},'url':{'type':'string'}})]:
                tool={'type':'function','function':{'name':name,'description':'Synthetic fixture only','parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}}
                try:
                    proposal=engine.propose_tool([{'role':'user','content':prompt}],[tool])
                    passed=not proposal.get('error') and len(proposal.get('tool_calls',[]))==1 and proposal['tool_calls'][0]['function']['name']==name
                    row['native_tools'].append({'name':name,'proposal':proposal,'passed':passed,'executor':'NOT EXECUTED'})
                except Exception as error:row['native_tools'].append({'name':name,'passed':False,'error':str(error)[:240]})
                save()
            row['status']='completed'
        except Exception as error:row.update(status='incomplete',error=type(error).__name__+':'+str(error)[:240])
        finally:
            done.set();thread.join(2);engine.close();monitor.close()
            row['resource_samples']=monitor.rows;row['owned_worker_released']=engine.process is None
            row['elapsed_seconds']=round(time.monotonic()-start,2);save()
        time.sleep(3)
    proof['status']='completed';save()
    print(json.dumps({'status':'completed','models':[{k:m.get(k) for k in ('id','status','elapsed_seconds')} for m in proof['models']]}),flush=True)

if __name__=='__main__':main()
