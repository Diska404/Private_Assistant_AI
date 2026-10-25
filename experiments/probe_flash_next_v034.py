"""Bounded Flash-Next load/decode probe. Only owned model processes are stopped."""
import argparse,json,os,sys,threading,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from hybrid_engine import LocalEngine
from benchmark_personal_models_v033 import Monitor
import psutil
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\model-expansion-v034');OUT.mkdir(parents=True,exist_ok=True)
MODEL=Path(r'Y:\GFL2_AI\models\hf-cache\models--unsloth--Qwen3.8-27B-GGUF\snapshots\4ca720788d1e01f1bff70c033e0d0028fd02e502\Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf')
SERVER=Path(r'D:\AI\AI Lokal Asisten\Leva\runtime\llamacpp-b11721-cuda13.4\llama-server.exe')
def stream(engine,prompt):
    payload={'messages':[{'role':'system','content':'Kamu Leva. Jawab ringkas dalam bahasa Indonesia.'},{'role':'user','content':prompt}],
      'max_tokens':64,'temperature':0.7,'top_p':0.8,'top_k':20,'stream':True,'chat_template_kwargs':{'enable_thinking':False}}
    started=time.perf_counter();first=None;answer='';timings={};finish=None
    req=urllib.request.Request(engine.endpoint+'/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+engine.api_key})
    with engine.opener.open(req,timeout=90) as response:
        for line in response:
            if not line.startswith(b'data: '):continue
            data=line[6:].strip()
            if data==b'[DONE]':break
            item=json.loads(data);timings=item.get('timings',timings)
            for choice in item.get('choices',[]):
                token=choice.get('delta',{}).get('content') or ''
                if token and first is None:first=(time.perf_counter()-started)*1000
                answer+=token;finish=choice.get('finish_reason') or finish
    return {'text':answer,'ttft_ms':round(first,2) if first else None,'total_ms':round((time.perf_counter()-started)*1000,2),'timings':timings,'finish_reason':finish}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--layers',type=int);parser.add_argument('--out')
    settings=parser.parse_args()
    original_out=OUT
    while True:
        try:
            verified=json.loads((OUT/'existing-models-verified.json').read_text('utf8'))
            if len(verified)==4 and all(r['verified'] for r in verified):break
        except (OSError,ValueError):pass
        print('Waiting for full existing-model hash verification',flush=True);time.sleep(15)
    proof={'status':'running','probe_pid':os.getpid(),'microphone':False,'speaker':False,'hermes_observed_error':'unable to allocate CUDA_Host buffer','profiles':[]}
    if settings.out:OUT=Path(settings.out);OUT.mkdir(parents=True,exist_ok=True)
    proof['requested_gpu_layers']=settings.layers
    def save():(OUT/'flash-next-probe.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    os.environ['GGML_CUDA_NO_PINNED']='1' # This owned test process/children only; no user/system setting.
    for mode in ('gpu5070','dual'):
        row={'mode':mode,'cases':[]};proof['profiles'].append(row);save()
        if psutil.virtual_memory().available<6*1024**3:row.update(status='insufficient_free_ram');save();continue
        engine=LocalEngine(SERVER,MODEL,OUT/('flash-'+mode),mode=mode,context_size=2048,max_output_tokens=64,thinking_budget=0,startup_timeout=240,
          extra_server_args=('--load-mode','mmap','--lazy-mode','on','--no-host','--cpu-moe','--override-tensor','per_layer_token_embd=CPU',
                             '--moe-cache-mib','256','--no-repack','--no-warmup','--batch-size','128','--ubatch-size','64','--no-context-shift')+(('--gpu-layers',str(settings.layers)) if settings.layers is not None else ()))
        monitor=Monitor();monitor.start();stop=threading.Event();timer=threading.Timer(420,engine.close);timer.daemon=True;timer.start()
        def guard(stop=stop,engine=engine,row=row):
            while not stop.wait(1):
                if psutil.virtual_memory().available<2*1024**3:row['resource_guard']='available_ram_below_2GiB';engine.close();return
        threading.Thread(target=guard,daemon=True).start()
        try:
            started=time.perf_counter();engine.start();row.update(status='loaded',startup_ms=round((time.perf_counter()-started)*1000,2),devices=engine.devices,
                gpu_buffers_mib=engine.model_gpu_buffers_mib,gpu_before=engine.gpu_snapshot_before,gpu_loaded=engine.gpu_snapshot_loaded);save()
            print(json.dumps({'loaded':mode,'startup_ms':row['startup_ms']}),flush=True)
            for prompt in ('Jawab tepat satu kalimat: Aku Leva, aku siap membantu.','Berapa hasil 17 dikali 23? Jawab hanya angkanya.'):
                result=stream(engine,prompt);row['cases'].append(result);save();print(json.dumps({'mode':mode,**result},ensure_ascii=True),flush=True)
            row['status']='inference_completed' if all(r['text'] for r in row['cases']) else 'empty_response'
        except Exception as e:row.update(status='failed',error=str(e))
        finally:
            stop.set();timer.cancel();engine.close();monitor.close();row['resource_samples']=monitor.rows;row['worker_released']=engine.process is None;save()
        print(json.dumps({'finished':mode,'status':row['status'],'error':row.get('error')}),flush=True)
    proof['status']='completed';save()
