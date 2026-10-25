"""Real Fooocus generation with installed weights; no updater, pip, or model download."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from fooocus_service import FooocusService


def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\images-v018');out.mkdir(parents=True,exist_ok=True)
    service=FooocusService(r'F:\AI\Fooocus_win64_2-5-0',storage=out/'fooocus')
    proof={};started=time.perf_counter()
    try:
        proof['catalog']=service.catalog();print(json.dumps({'models':len(proof['catalog']['models']),'warning':proof['catalog']['warning']}),flush=True)
        proof['start']=service.start();print(json.dumps(proof['start']),flush=True)
        for i in range(75):
            status=service.status()
            if status['status']=='done':break
            if status.get('server_exit_code') is not None:raise ValueError('fooocus_startup_exit:'+str(status['server_exit_code']))
            if i%10==0:print('Waiting for Fooocus '+str(i*2)+'s',flush=True)
            time.sleep(2)
        if status['status']!='done':raise ValueError('fooocus_not_ready')
        proof['status']=status
        job=service.generate('juggernautXL_v8','A cozy wooden cabin beside a lake, soft morning light, natural colors, landscape photography','blurry, low quality',12,512,512)
        proof['submitted']=job;print(json.dumps(job),flush=True)
        for i in range(150):
            result=service.poll(job['job_id'])
            if result['status']!='running':break
            if i%10==0:print('Generation running '+str(i*2)+'s',flush=True)
            time.sleep(2)
        proof['result']=result
        if not result['task_verified']:raise ValueError('fooocus_generation_not_verified')
    except Exception as error:proof['error']=str(error);print(json.dumps({'error':str(error)}),flush=True)
    finally:
        service.stop()
        if service.process:service.process.wait(timeout=15)
        proof['elapsed_seconds']=round(time.perf_counter()-started,3)
        (out/'real-fooocus-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
