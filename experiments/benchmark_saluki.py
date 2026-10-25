"""Compare real Saluki decoding modes sequentially; never starts microphone or tools."""
import json
from pathlib import Path
import statistics
import sys
import time
import threading
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from saluki_backend import SalukiEngine,MODEL_ROOT
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\saluki-v08')

def stream(engine,prompt):
    payload={'messages':[{'role':'system','content':'Kamu Leva. Jawab jelas dan singkat dalam bahasa yang diminta.'},
        {'role':'user','content':prompt}],'max_tokens':160,'temperature':0,'stream':True,
        'chat_template_kwargs':{'enable_thinking':False}}
    request=urllib.request.Request(engine.endpoint+'/v1/chat/completions',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+engine.api_key})
    started=time.perf_counter(); first=None; answer='';timings={};finish=None
    with engine.opener.open(request,timeout=90) as response:
        for line in response:
            if not line.startswith(b'data: '):continue
            data=line[6:].strip()
            if data==b'[DONE]':break
            item=json.loads(data)
            timings=item.get('timings',timings)
            for choice in item.get('choices',[]):
                text=choice.get('delta',{}).get('content') or ''
                if text and first is None:first=(time.perf_counter()-started)*1000
                answer+=text
                if choice.get('finish_reason'):finish=choice['finish_reason']
    return {'text':answer,'ttft_ms':round(first,2) if first else None,
        'total_ms':round((time.perf_counter()-started)*1000,2),'timings':timings,'finish_reason':finish}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    proof={'status':'running','microphone_opened':False,'speaker_opened':False,'profiles':[]}
    def save():(OUT/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    for method in ('plain','mtp','dflash'):
        engine=SalukiEngine(OUT/method,acceleration=method)
        row={'acceleration':method,'status':'starting','requests':[]}
        proof['profiles'].append(row);save()
        timer=None
        try:
            started=time.perf_counter();engine.start()
            row.update(startup_seconds=round(time.perf_counter()-started,3),devices=engine.devices,
                gpu_snapshot_loaded=engine.gpu_snapshot_loaded)
            for prompt in ('Jawab dalam bahasa Indonesia, maksimal dua kalimat: jelaskan apa fungsi eGPU pada laptop.',
                           'Reply in English in two short sentences: how can I start learning piano?'):
                timer=threading.Timer(60,engine.close);timer.daemon=True;timer.start()
                try:result=stream(engine,prompt)
                finally:timer.cancel()
                row['requests'].append(result);save()
                print(json.dumps({'mode':method,**result},ensure_ascii=True),flush=True)
            row['status']='inference_completed'
        except Exception as error:
            row.update(status='failed',error=str(error) if str(error).startswith(('local_','saluki_')) else type(error).__name__)
        finally:
            if timer:timer.cancel()
            engine.close();row['runtime_released']=engine.process is None;save()
    valid=[r for r in proof['profiles'] if r['status']=='inference_completed' and all(q['finish_reason']=='stop' and q['text'] for q in r['requests'])]
    if valid:
        best=min(valid,key=lambda r:statistics.mean(q['total_ms'] for q in r['requests']))
        (MODEL_ROOT/'runtime-profile.json').write_text(json.dumps({'recommended_acceleration':best['acceleration'],
            'measured':True,'evidence':str(OUT/'proof.json'),'note':'Two short requests per mode; limited probe, no claim of universal speedup.'},indent=2),encoding='utf-8')
        proof.update(status='comparison_completed',recommended=best['acceleration'])
    else:proof['status']='no_usable_profile'
    save();print(json.dumps({'status':proof['status'],'recommended':proof.get('recommended')}),flush=True)
