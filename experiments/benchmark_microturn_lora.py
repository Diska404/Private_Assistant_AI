"""Real matched-model LoRA replay; text only, no microphone or speaker."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from microturn_backend import MicroTurnEngine,LISTEN,NO_VOICE
from duplex_core import parse_decision
from hybrid_engine import EngineError

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\microturn-lora')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cpu-moe',type=int,default=24)
    parser.add_argument('--mode',choices=['gpu5070','dual'],default='gpu5070')
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--load-mode',choices=['mmap','none'],default='mmap')
    parser.add_argument('--short',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    engine=MicroTurnEngine(OUT/f'runtime-{args.mode}-cpu{args.cpu_moe}-t{args.threads}-{args.load_mode}',
        cpu_moe_layers=args.cpu_moe,mode=args.mode,threads=args.threads,load_mode=args.load_mode)
    result={'status':'starting','lora_loaded':False,'microphone_opened':False,'speaker_opened':False,
            'network':'loopback inference only; no prompts sent externally','cpu_moe_layers':args.cpu_moe,
            'gpu_mode':args.mode,'cpu_threads':args.threads,'load_mode':args.load_mode,
            'context_size':8192,'tick_budget_ms':600,'rows':[],'scenarios':[]}
    def save(): (OUT/'proof.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    save()
    try:
        started=time.perf_counter()
        engine.start()
        result.update(status='loaded',lora_loaded=True,load_seconds=engine.load_seconds,
            verification_and_load_seconds=round(time.perf_counter()-started,3),adapter_status=engine.adapter_status,
            assets=engine.asset_records,devices=engine.devices,gpu_snapshot_before=engine.gpu_snapshot_before,
            gpu_snapshot_loaded=engine.gpu_snapshot_loaded,runtime_path=str(engine.server))
        save()
        print(json.dumps({'loaded':True,'seconds':result['verification_and_load_seconds'],'devices':engine.devices}),flush=True)
        scenarios=[
            ('english_greeting','en',['Hello.']+[NO_VOICE]*7),
            ('english_pause_and_question','en',['I was wondering',NO_VOICE,'whether I should','learn the piano.',
                 NO_VOICE,'What is one','good first step?']+[NO_VOICE]*7),
            ('indonesian_exploratory','id',['Halo Leva,',NO_VOICE,'saya ingin bertanya.',
                 'Apa langkah pertama','untuk belajar piano?']+[NO_VOICE]*8),
        ]
        if args.short:scenarios=scenarios[1:2]
        for name,lang,fragments in scenarios:
            history=[]
            for i,heard in enumerate(fragments,1):
                response=engine.tick(history,heard)
                try: decision=parse_decision(response['text'])[0]; grammar=True
                except ValueError: decision='invalid'; grammar=False
                row={'scenario':name,'language':lang,'tick':i,'heard':heard,**response,
                     'policy_grammar_valid':grammar,'decision':decision,'within_600ms':response['backend_ms']<=600}
                result['rows'].append(row)
                history.append((heard,response['text']))
                save()
                print(json.dumps({'scenario':name,'tick':i,'heard':heard,'said':response['text'],
                      'ms':response['backend_ms'],'p_listen':response['listen_probability']},ensure_ascii=True),flush=True)
            outputs=[r for r in result['rows'] if r['scenario']==name]
            result['scenarios'].append({'id':name,'language':lang,'ticks':len(outputs),
                'spoken_chunks':sum(r['decision']=='speak' for r in outputs),
                'grammar_invalid':sum(not r['policy_grammar_valid'] for r in outputs),
                'assembled_response':' '.join(r['text'] for r in outputs if r['text']!=LISTEN)})
        times=sorted(row['backend_ms'] for row in result['rows'])
        import math
        result['metrics']={'measured_ticks':len(times),'p50_ms':times[math.ceil(len(times)*.5)-1],
            'p95_ms':times[math.ceil(len(times)*.95)-1],'over_600ms':sum(t>600 for t in times),
            'decoding_retries':sum(row['decoding_retry'] for row in result['rows'])}
        result['status']='inference_completed_text_only'
    except Exception as error:
        result['status']='failed'
        result['error']=str(error) if isinstance(error,EngineError) else type(error).__name__
    finally:
        engine.close()
        result['owned_runtime_stopped']=engine.process is None
        save()
    print(json.dumps({'status':result['status'],'error':result.get('error'),'metrics':result.get('metrics'),'proof':str(OUT/'proof.json')}),flush=True)
    return 0 if result['status']=='inference_completed_text_only' else 1

if __name__=='__main__': raise SystemExit(main())
