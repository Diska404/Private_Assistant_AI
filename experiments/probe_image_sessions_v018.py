"""Real installed frontends and persisted generation result; no second diffusion generation."""
import json
from pathlib import Path
import queue
import sys
import time
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'program/0.18.0/Leva/_internal/assistant_runtime'),str(ROOT/'app'),str(ROOT/'experiments')]
from fooocus_service import FooocusService
from comfy_service import ComfyService
from browser_runtime import BrowserRuntime
from assistant_tools import AssistantTools
from task_journal import TaskJournal
from agent_runtime import run_agent
from image_jobs import ImageJobs

def main():
    out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\images-v018');first=json.loads((out/'real-fooocus-proof.json').read_text('utf-8'))
    foo=FooocusService(r'F:\AI\Fooocus_win64_2-5-0',storage=out/'fooocus');comfy=ComfyService(r'F:\AI\ComfyUI_windows_portable',storage=out/'comfy')
    original_command=foo.server_command
    def packaged_command(*args):
        command=original_command(*args);command[3]=str(ROOT/'program/0.18.0/Leva/_internal/assistant_runtime/fooocus_worker.py');return command
    foo.server_command=packaged_command
    browser=BrowserRuntime(headless=True,profile=out/'browser-profile');proof={'decision_source':'deterministic model fixture; actual host tools, servers and packaged frontend adapters'}
    tools=AssistantTools.__new__(AssistantTools);tools._comfy=comfy;tools._fooocus=foo;tools._resume_goal='';tools._image_submissions={}
    class Bridge:
        def run(self,action,args,*extra,**kwargs):
            if action=='comfy_open':return browser.comfy_canvas(args)
            if action=='comfy_canvas':return browser.comfy_canvas(args)
            if action=='comfy_current':return browser.comfy_current()
            if action=='fooocus_open':return browser.fooocus_open(args)
            raise ValueError('probe_unexpected_action')
    tools._bridge=Bridge();journal=TaskJournal(out/'session-tasks.sqlite3')
    try:
        foo.start();comfy.start()
        for i in range(80):
            if foo.status()['status']=='done' and comfy.status()['status']=='done':break
            if i%10==0:print('Waiting for image backends '+str(i*2)+'s',flush=True)
            time.sleep(2)
        proof['fooocus_ui']=browser.fooocus_open({'url':foo.client.base})
        proof['persisted_generation']=foo.poll(first['submitted']['job_id'])
        monitor=ImageJobs(out/'monitor.sqlite3');monitor.track('fooocus',first['submitted']['job_id']);proof['observer_notification']=monitor.observe(tools)
        for update in proof['observer_notification']:monitor.acknowledge(update['engine'],update['id'])
        proof['observer_no_duplicate']=monitor.observe(tools)==[]
        commands=queue.Queue();model=Mock();model.propose_tool.return_value={'action':'comfy_action','args':{'action':'open'}}
        def emit(event):
            result=tools.execute(event['name'],event['args'],'Leva buka comfyui')
            commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
        with patch('task_journal.TaskJournal',return_value=journal):
            opened=run_agent({'id':1,'mode':'local','messages':[{'role':'user','content':'Leva buka comfyui'}]},model,commands,emit)
        proof['followup_question']=opened['response'];continued=journal.continuation('buat baru saja, gunakan checkpoint juggernautXL_v8Rundiffusion.safetensors')
        proof['new_reply_resumes']=continued['id']==opened['task_id']
        workflow=comfy.prepare('juggernautXL_v8Rundiffusion.safetensors','A warm reading room with books and plants',width=768,height=768)
        ident=workflow['workflow_id'];proof['new_workflow']=comfy.publish(ident)
        folder=comfy.storage/ident
        proof['new_canvas']=browser.comfy_canvas({'url':comfy.client.base,'workflow':json.loads((folder/'workflow.json').read_text('utf-8')),'expected':json.loads((folder/'api.json').read_text('utf-8'))})
        current=browser.comfy_current();proof['current_models']={key:row['inputs'] for key,row in current['graph'].items() if row['class_type']=='CheckpointLoaderSimple'}
        assert proof['fooocus_ui']['task_verified'] and proof['persisted_generation']['task_verified'] and proof['new_reply_resumes'] and proof['new_canvas']['task_verified'] and proof['observer_no_duplicate']
    except Exception as error:proof['error']=str(error);print(json.dumps({'error':str(error)}),flush=True)
    finally:
        browser.stop();foo.stop();comfy.stop()
        for service in (foo,comfy):
            if service.process:service.process.wait(timeout=15)
        (out/'real-session-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
