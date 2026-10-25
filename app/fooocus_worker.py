"""Owned Fooocus session, importing the installed engine; local-only authenticated job API."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from urllib.parse import urlparse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--storage',required=True);parser.add_argument('--port',type=int,required=True)
    settings=parser.parse_args();root=Path(settings.root).resolve();storage=Path(settings.storage).resolve()
    if not (root/'webui.py').is_file():raise ValueError('fooocus_source_required')
    config=storage/'session-config.json';token=(storage/'session-token').read_text('utf-8')
    os.environ.update(config_path=str(config),config_example_path=str(storage/'config-tutorial.txt'),GRADIO_ANALYTICS_ENABLED='False')
    os.chdir(root);sys.path.insert(0,str(root))
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from image_tensor_io import install_stream_reader
    install_stream_reader()
    print('Leva: streaming CPU checkpoint reader enabled (no private whole-file mmap).',flush=True)
    sys.argv=['launch.py','--listen','127.0.0.1','--port',str(settings.port),'--disable-in-browser','--disable-analytics','--disable-preset-download']
    # This session never runs pip, updater, launcher generation, or downloads.
    util=importlib.import_module('modules.launch_util')
    util.requirements_met=lambda *args,**kwargs:True
    def no_install(*args,**kwargs):raise RuntimeError('fooocus_dependency_missing_no_automatic_install')
    util.run_pip=no_install;util.run=no_install
    launcher=importlib.import_module('build_launcher');launcher.build_launcher=lambda:None
    loader=importlib.import_module('modules.model_loader')
    def local_only(url,model_dir,file_name=None,**kwargs):
        filename=file_name or Path(urlparse(url).path).name
        path=(Path(model_dir)/filename).resolve()
        if not path.is_file():raise RuntimeError('fooocus_required_local_asset_missing:'+filename)
        return str(path)
    loader.load_file_from_url=local_only
    import gradio as gr
    original_launch=gr.Blocks.launch
    jobs=storage/'engine-jobs';jobs.mkdir(exist_ok=True);lock=threading.Lock()
    # Old unfinished receipts are observations of an interruption, never requeued.
    for path in jobs.glob('*.json'):
        row=json.loads(path.read_text('utf-8'))
        if row.get('state') in ('running','queued'):
            row.update(state='interrupted',error='Fooocus worker restarted; generation not replayed.');path.write_text(json.dumps(row),encoding='utf-8')

    def write_job(row):
        path=jobs/(row['id']+'.json');temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

    def execute(row):
        started=time.perf_counter();row['state']='running';write_job(row)
        try:
            ui=sys.modules['webui'];payload=row['request'];values=[component.value for component in ui.ctrls]
            overrides={'generate_image_grid':False,'prompt':payload['positive'],'negative_prompt':payload['negative'],'style_selections':[],
                       'base_model':payload['model'],'refiner_model':'None','image_number':1,'image_seed':str(payload['seed']),
                       'overwrite_step':payload['steps'],'overwrite_width':payload['width'],'overwrite_height':payload['height'],
                       'enhance_checkbox':False,'input_image_checkbox':False,'output_format':'png'}
            for name,value in overrides.items():
                component=getattr(ui,name,None)
                if component is None:raise ValueError('fooocus_component_missing:'+name)
                index=next(i for i,c in enumerate(ui.ctrls) if c is component);values[index]=value
            # Disable optional LoRAs; selecting one explicitly can be added separately.
            for index in range(0,len(ui.lora_ctrls),3):
                component=ui.lora_ctrls[index];values[next(i for i,c in enumerate(ui.ctrls) if c is component)]=False
            task=ui.get_task(*values)
            for _ in ui.generate_clicked(task):pass
            from PIL import Image
            outputs=[];allowed=(storage/'outputs').resolve()
            for item in task.results:
                if not isinstance(item,str):continue
                path=Path(item).resolve()
                if not path.is_relative_to(allowed):raise ValueError('fooocus_output_outside_session')
                with Image.open(path) as image:
                    image.verify()
                outputs.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            if not outputs:raise RuntimeError('fooocus_finished_without_verified_image')
            row.update(state='completed',outputs=outputs)
        except Exception as error:row.update(state='failed',error=str(error)[:700])
        finally:row['elapsed_seconds']=round(time.perf_counter()-started,3);write_job(row)

    def launch_with_api(blocks,*args,**kwargs):
        kwargs['prevent_thread_lock']=True
        result=original_launch(blocks,*args,**kwargs);app=result[0]
        from fastapi import Request,HTTPException
        globals()['Request']=Request
        def authorize(request):
            if not secrets.compare_digest(request.headers.get('X-Leva-Token',''),token):raise HTTPException(403,'Local session token required')
        async def status(request:Request):
            authorize(request)
            import torch
            device=torch.cuda.current_device();prop=torch.cuda.get_device_properties(device);free,_=torch.cuda.mem_get_info(device)
            return {'devices':[{'name':prop.name,'vram_total':prop.total_memory,'vram_free':free}],'engine':'Fooocus','version':sys.modules['fooocus_version'].version}
        async def queue(request:Request):
            authorize(request);rows=[json.loads(p.read_text('utf-8')) for p in jobs.glob('*.json')]
            return {'queue_running':[[0,r['id']] for r in rows if r['state']=='running'],'queue_pending':[[0,r['id']] for r in rows if r['state']=='queued']}
        async def inspect(request:Request):
            authorize(request);ident=request.path_params['ident']
            if not re.fullmatch('[0-9a-f]{12}',ident):raise HTTPException(400,'Invalid job ID')
            path=jobs/(ident+'.json')
            if not path.exists():raise HTTPException(404,'Job unknown')
            row=json.loads(path.read_text('utf-8'));row.pop('request',None);return row
        async def generate(request:Request):
            authorize(request);payload=await request.json();ident=payload.get('id','')
            if not re.fullmatch('[0-9a-f]{12}',ident):raise HTTPException(400,'Invalid job ID')
            ui=sys.modules['webui']
            ui.modules.config.update_files()
            if payload.get('model') not in ui.modules.config.model_filenames:raise HTTPException(400,'Model unavailable')
            if not isinstance(payload.get('positive'),str) or not payload['positive'].strip() or len(payload['positive'])>3000:raise HTTPException(400,'Prompt required')
            if not isinstance(payload.get('negative'),str) or len(payload['negative'])>3000:raise HTTPException(400,'Invalid negative prompt')
            for key,low,high in (('steps',1,60),('width',256,1536),('height',256,1536),('seed',0,2**32-1)):
                if type(payload.get(key)) is not int or not low<=payload[key]<=high:raise HTTPException(400,'Parameter range')
            if payload['width']%8 or payload['height']%8:raise HTTPException(400,'Size must be multiple of eight')
            with lock:
                path=jobs/(ident+'.json')
                if path.exists():return {'id':ident,'state':json.loads(path.read_text('utf-8'))['state']}
                if any(json.loads(p.read_text('utf-8'))['state'] in ('queued','running') for p in jobs.glob('*.json')):raise HTTPException(409,'Another Fooocus job is active')
                row={'id':ident,'state':'queued','request':payload,'outputs':[]};write_job(row)
                threading.Thread(target=execute,args=(row,),daemon=True).start()
                return {'id':ident,'state':'queued'}
        app.add_api_route('/leva/status',status,methods=['GET']);app.add_api_route('/leva/queue',queue,methods=['GET'])
        app.add_api_route('/leva/jobs/{ident}',inspect,methods=['GET']);app.add_api_route('/leva/generate',generate,methods=['POST'])
        return result
    gr.Blocks.launch=launch_with_api
    importlib.import_module('launch')
    while True:time.sleep(1)


if __name__=='__main__':main()
