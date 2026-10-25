"""Real installed ComfyUI probe: live catalog, two-LoRA graph, canvas, tiny model-free queue job."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
if '--packaged-runtime' in sys.argv:sys.path.insert(0,str(ROOT/'program/0.17.0/Leva/_internal/assistant_runtime'))
from comfy_service import ComfyService
from browser_runtime import BrowserRuntime


def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\comfy-v017');out.mkdir(parents=True,exist_ok=True)
    service=ComfyService(r'F:\AI\ComfyUI_windows_portable',storage=out/'workflows')
    browser=BrowserRuntime(headless=True,profile=out/'browser-profile')
    proof={'scope':'actual installed ComfyUI and Edge, no diffusion weights loaded, no model downloads','packaged_browser_runtime':'--packaged-runtime' in sys.argv}
    started=time.perf_counter()
    try:
        proof['launch']=service.start();print(json.dumps({'launch':proof['launch']}),flush=True)
        for index in range(90):
            status=service.status()
            if status['status']=='done':break
            if index%10==0:print(json.dumps({'waiting':index*2,'status':status['status']}),flush=True)
            time.sleep(2)
        if status['status']!='done':raise RuntimeError('real_server_not_ready')
        proof['status']=status
        catalog=service.catalog();proof['catalog_counts']={k:v['total'] for k,v in catalog['catalog'].items()}
        checkpoint=next(name for name in catalog['catalog']['checkpoints']['matches'] if name.startswith('juggernautXL_v8'))
        loras=[name for name in catalog['catalog']['loras']['matches'] if name in ('SDXL_FILM_PHOTOGRAPHY_STYLE_V1.safetensors','sd_xl_offset_example-lora_1.0.safetensors')]
        if len(loras)!=2:raise RuntimeError('two_compatible_named_loras_not_in_catalog')
        prepared=service.prepare(checkpoint,'A wooden desk with a notebook and a warm reading lamp, realistic photography','blurry, low quality',[{'name':name,'strength':0.3} for name in loras],width=768,height=768,steps=20)
        ident=prepared['workflow_id'];proof['prepared']=prepared;proof['published']=service.publish(ident)
        folder=service.storage/ident
        proof['canvas']=browser.comfy_canvas({'url':service.client.base,'workflow':json.loads((folder/'workflow.json').read_text('utf-8')),'expected':json.loads((folder/'api.json').read_text('utf-8'))})
        page=browser.page(proof['canvas']['tab']);page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(out/'workflow-canvas.png'))
        if not proof['canvas']['task_verified']:raise RuntimeError('canvas_roundtrip_mismatch')
        exported=page.evaluate("""async graph => {const {app}=await import('/scripts/app.js');await app.loadGraphData(graph,true,true);return (await app.graphToPrompt()).output;}""",json.loads((folder/'workflow.json').read_text('utf-8')))
        expected=json.loads((folder/'api.json').read_text('utf-8'))
        proof['published_ui_roundtrip']=len(exported)==len(expected) and all(exported.get(key,{}).get('class_type')==row['class_type'] and exported[key].get('inputs')==row['inputs'] for key,row in expected.items())
        if not proof['published_ui_roundtrip']:raise RuntimeError('published_ui_roundtrip_mismatch')
        # Actual queue/history validation with an unambiguous deterministic test image, no diffusion inference.
        tiny={'1':{'class_type':'EmptyImage','inputs':{'width':64,'height':64,'batch_size':1,'color':0x203040}},
              '2':{'class_type':'SaveImage','inputs':{'images':['1',0],'filename_prefix':'Leva/connector-verification'}}}
        job=service.prepare_graph(tiny,'Connector model-free smoke test');job_id=job['workflow_id']
        proof['submit']=service.submit(job_id)
        for _ in range(30):
            result=service.poll(job_id)
            if result['status']!='running':break
            time.sleep(.5)
        proof['job']=result
        if result['status']!='done' or not result['outputs']:raise RuntimeError('real_queue_output_not_verified')
        reopened=ComfyService(r'F:\AI\ComfyUI_windows_portable',storage=service.storage)
        proof['reopened_job']=reopened.poll(job_id)
        proof['no_duplicate_submit']=reopened.submit(job_id)['workflow_state']=='completed'
        proof['diffusion_job_submitted']=bool(service._record(ident).get('submission_attempted'))
    except Exception as error:
        proof['error']=str(error);print(json.dumps({'error':str(error)}),flush=True)
        if browser.context and browser.context.pages:
            page=browser.context.pages[-1]
            page.screenshot(path=str(out/'canvas-error.png'))
            proof['frontend_debug']=page.evaluate("""async () => {const {app}=await import('/scripts/app.js');return {url:location.href,graph:!!app.graph,root:!!app.rootGraph,canvas:!!app.canvas,windowRoot:!!window.comfyAPI.app.app.rootGraph,keys:Object.keys(app).slice(0,45),body:document.body.innerText.slice(0,1500)};}""")
    finally:
        browser.stop();service.stop();proof['owned_server_stopped']=service.process is None or service.process.wait(timeout=15) is not None
        proof['elapsed_seconds']=round(time.perf_counter()-started,3)
        (out/'real-comfy-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)
    return 1 if proof.get('error') else 0


if __name__=='__main__':raise SystemExit(main())
