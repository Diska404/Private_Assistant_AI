"""Same offline WAV on each explicit GPU route; no microphone or speaker."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021')

def child(gpu):
    from speech_asr import SpeechASR
    import soundfile as sf
    import numpy as np
    from scipy.signal import resample_poly
    from math import gcd
    path=Path('D:/AI/AI Lokal Asisten/Leva/evaluation/asr-lab/audio/0da8ff7299eb16b6a0455d9e.wav')
    samples,rate=sf.read(path,dtype='float32')
    if samples.ndim>1:samples=samples.mean(axis=1)
    if rate!=16000:
        g=gcd(rate,16000);samples=resample_poly(samples,16000//g,rate//g)
    start=time.monotonic();engine=SpeechASR(gpu=gpu);init=time.monotonic()-start
    runs=[engine.transcribe(samples,'id') for _ in range(2)]
    import torch,os
    memory=[{'uuid':r['uuid'],'name':torch.cuda.get_device_name(i),'allocated_mib':round(torch.cuda.memory_allocated(i)/2**20,2),
             'reserved_mib':round(torch.cuda.memory_reserved(i)/2**20,2)} for i,r in enumerate(engine.devices)]
    assert torch.cuda.device_count()==len(engine.devices)
    assert all(all(ms>0 for ms in r['module_forward_cuda_ms'].values()) for r in runs)
    result={'gpu':gpu,'visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],'device_count':torch.cuda.device_count(),
            'init_seconds':init,'memory':memory,'runs':runs,'audio_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'audio_duration':len(samples)/16000,'microphone_opened':False,'speaker_opened':False,'agent_called':False}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/(gpu+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'gpu':gpu,'latency_ms':[r['asr_ms'] for r in runs],'devices':memory,'execution_ms':[r['module_forward_cuda_ms'] for r in runs]}),flush=True)

if __name__=='__main__':
    if len(sys.argv)>1:child(sys.argv[1])
    else:
        from speech_asr import ASR_PYTHON
        for gpu in ('rtx4050','rtx5070','dual'):
            p=subprocess.run([str(ASR_PYTHON),'-u',str(Path(__file__).resolve()),gpu],cwd=ROOT,timeout=90,capture_output=True,text=True)
            print(p.stdout,flush=True)
            if p.returncode:raise RuntimeError(p.stderr[-4000:])
