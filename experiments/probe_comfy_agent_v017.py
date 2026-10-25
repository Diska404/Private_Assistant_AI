"""One real selected-router workflow task; isolated history and browser, strict allowed tools."""
import json
from pathlib import Path
import queue
import sys
import time
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from comfy_service import ComfyService
from browser_runtime import BrowserRuntime
from assistant_tools import AssistantTools
from task_journal import TaskJournal
from agent_runtime import run_agent
from hybrid_engine import EngineError
from router_gateway import RouterGateway
from router_provider import configured_client


def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\comfy-v017');out.mkdir(parents=True,exist_ok=True)
    service=ComfyService(r'F:\AI\ComfyUI_windows_portable',storage=out/'agent-workflows');gateway=RouterGateway()
    browser=BrowserRuntime(headless=True,profile=out/'agent-browser-profile');commands=queue.Queue();calls=[]
    journal=TaskJournal(out/'agent-tasks.sqlite3')
    tools=AssistantTools.__new__(AssistantTools);tools._comfy=service;tools._resume_goal=''
    class Bridge:
        def run(self,action,args,*unused,**kwargs):
            if action!='comfy_canvas':raise ValueError('probe_unexpected_bridge_action')
            return browser.comfy_canvas(args)
    tools._bridge=Bridge()
    prompt=('Buka ComfyUI, buat workflow foto meja kerja dengan buku dan lampu hangat memakai checkpoint juggernautXL_v8Rundiffusion.safetensors, '
            'dua LoRA SDXL_FILM_PHOTOGRAPHY_STYLE_V1.safetensors dan sd_xl_offset_example-lora_1.0.safetensors dengan strength masing-masing 0.3, '
            '768x768, 20 langkah. Periksa katalog dulu. Simpan ke pustaka ComfyUI dan tampilkan di canvas lalu periksa hasilnya. Jangan generate atau render gambar.')
    def emit(event):
        if event['name'] not in ('comfy_action','task_plan','discover_tools','list_tasks','resume_task'):raise ValueError('probe_unexpected_tool:'+event['name'])
        if event['name']=='comfy_action' and event['args']['action'] in ('submit','stop_server'):raise ValueError('probe_generation_or_stop_not_requested')
        started=time.perf_counter();result=tools.execute(event['name'],event['args'],prompt)
        row={'name':event['name'],'action':event['args'].get('action'),'status':result.get('status'),'workflow_id':result.get('workflow_id'),'code':result.get('code'),'seconds':round(time.perf_counter()-started,3)}
        calls.append(row);print(json.dumps(row),flush=True)
        commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
    local=Mock();local.propose_tool.side_effect=EngineError('probe_no_local_gpu_inference')
    proof={'scope':'real selected 9Router model, actual ComfyUI API and headless Edge; one specified SDXL planning task'}
    try:
        client=configured_client();proof['router_model']=client.model;proof['gateway']=gateway.start(client.url)
        real_propose=client.propose_tool
        def propose(*args,**kwargs):
            try:return real_propose(*args,**kwargs)
            except EngineError as error:
                proof['router_failure']=getattr(error,'reason',str(error));raise
        client.propose_tool=propose
        service.start()
        for _ in range(75):
            if service.status()['status']=='done':break
            time.sleep(2)
        start=time.perf_counter()
        with patch('task_journal.TaskJournal',return_value=journal),patch('router_provider.configured_client',return_value=client):
            result=run_agent({'id':1,'mode':'router','time_budget_seconds':120,'messages':[{'role':'user','content':prompt}],
                              'tool_context':{'comfyui':{'configured':True,'base':service.client.base}}},local,commands,emit)
        proof.update(provider=result.get('provider'),response=result.get('response'),incomplete=result.get('incomplete'),task_id=result.get('task_id'),agent_seconds=round(time.perf_counter()-start,3))
        if browser.context and len(browser.context.pages)>1:
            browser.context.pages[-1].screenshot(path=str(out/'agent-canvas.png'))
        proof['published_and_canvas_verified']=all(any(row['name']=='comfy_action' and row['action']==action and row['status']=='done' for row in calls) for action in ('publish','canvas'))
    except Exception as error:proof['error']=str(error) if isinstance(error,(ValueError,EngineError)) else type(error).__name__
    finally:
        proof['calls']=calls;proof['generation_submitted']=any(row['action']=='submit' for row in calls)
        browser.stop();service.stop();gateway.stop()
        if service.process:service.process.wait(timeout=15)
        (out/'real-agent-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
