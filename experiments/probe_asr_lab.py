"""Real HTTP -> owned Qwen ASR -> persisted metrics. Synthetic file, no microphone."""
import base64
import json
from pathlib import Path
import re
import time
import sys
import urllib.request

BASE='http://127.0.0.1:8771';DATA=Path('D:/AI/AI Lokal Asisten/Leva')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
html=opener.open(BASE).read().decode();token=re.search(r'name="lab-token" content="([^"]+)"',html).group(1)
def get(path):return json.load(opener.open(BASE+path,timeout=10))
def post(path,body):return json.load(opener.open(urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Leva-Lab':token}),timeout=15))
source=DATA/'verification/adaptive-voice-v014/final/higgs_leva_id_assistant.wav'
reference='Aku di sini. Mau kita lanjutkan pekerjaanmu, atau kamu ingin bercerita sebentar?'
proof={'source':'synthetic_fixture','microphone_opened':False,'agent_called':False,'runs':[]}
ident=None
try:
    for gpu in (('dual','dual') if '--dual' in sys.argv else ('rtx4050',) if '--single' in sys.argv else ('rtx4050','rtx4050','rtx5070')):
        payload={'prompt_id':'custom','reference':reference,'reference_confirmed':True,'gpu':gpu,'language':'id',
                 'condition':'quiet','equipment':'synthetic file (technical verification)',
                 'audio_origin':'synthetic','capture':{'technical_probe':True},'use_context':True}
        if ident:payload['replay_id']=ident
        else:payload['audio']=base64.b64encode(source.read_bytes()).decode()
        row=post('/api/run',payload)
        deadline=time.monotonic()+210
        while time.monotonic()<deadline:
            latest=get('/api/run/'+row['id'])
            if latest['status']!='running':break
            time.sleep(.5)
        if latest['status']!='done':raise RuntimeError(json.dumps(latest))
        ident=ident or row['id'];r=latest['result']
        proof['runs'].append({'id':row['id'],'gpu':gpu,'actual_gpu':r['gpu_name'],'warm':r['model_reused'],
            'wer':latest['metrics']['wer'],'asr_ms':r['asr_ms'],'server_total_ms':latest['server_total_ms'],
            'resource_samples':len(latest['resources']['samples']),'audio_sha256':latest['audio_sha256'],
            'torch_peak_allocated_mib':r['torch_peak_allocated_mib'],'torch_device_memory':r.get('torch_device_memory'), 'execution_ms':r.get('module_forward_cuda_ms'),'runtime':r['runtime']})
        print(json.dumps(proof['runs'][-1]),flush=True)
    # HTTP persisted review, restart-independent database, both exports.
    post('/api/review',{'id':ident,'reference':reference,'reference_confirmed':True,'review':'unreviewed','notes':'Uji integrasi audio sintetis; bukan suara pemilik.'})
    proof['csv_bytes']=len(opener.open(BASE+'/api/export.csv').read())
    proof['json_run_count']=len(get('/api/export.json')['runs'])
    proof['same_audio_across_gpus']=len({r['audio_sha256'] for r in proof['runs']})==1
finally:
    post('/api/release',{})
    out=DATA/'verification/asr-lab';out.mkdir(parents=True,exist_ok=True)
    (out/('http-dual-v021.json' if '--dual' in sys.argv else 'http-integration-final.json' if '--single' in sys.argv else 'http-integration.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
