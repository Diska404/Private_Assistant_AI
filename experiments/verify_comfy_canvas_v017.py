"""Targeted final packaged frontend check using the already prepared example; no new workflow/job."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'program/0.17.0/Leva/_internal/assistant_runtime'),str(ROOT/'app')]
from comfy_service import ComfyService
from browser_runtime import BrowserRuntime


def main():
    data=Path(r'D:\AI\AI Lokal Asisten\Leva');out=data/'verification/comfy-v017'
    deployment=json.loads((out/'deployment-check.json').read_text('utf-8'));ident=deployment['example_workflow_id']
    service=ComfyService(r'F:\AI\ComfyUI_windows_portable');browser=BrowserRuntime(headless=True,profile=out/'final-browser-profile')
    proof={}
    try:
        service.start()
        for _ in range(60):
            if service.status()['status']=='done':break
            time.sleep(2)
        folder=service.storage/ident
        result=browser.comfy_canvas({'url':service.client.base,'workflow':json.loads((folder/'workflow.json').read_text('utf-8')),'expected':json.loads((folder/'api.json').read_text('utf-8'))})
        proof.update(result);page=browser.page(result['tab'])
        page.screenshot(path=str(out/'final-workflow-canvas.png'))
        if not result['task_verified']:raise ValueError('final_canvas_mismatch')
    finally:
        browser.stop();service.stop()
        if service.process:service.process.wait(timeout=15)
        (out/'final-canvas-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
