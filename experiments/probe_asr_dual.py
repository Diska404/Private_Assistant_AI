"""Offline device-dispatch experiment. Never opens a microphone or invokes an agent."""
import json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from speech_resources import gpu_rows
rows=gpu_rows()
chosen=[next(r for r in rows if name in r['name']) for name in ('RTX 4050','RTX 5070')]
os.environ.update(CUDA_VISIBLE_DEVICES=','.join(r['uuid'] for r in chosen),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
import torch, soundfile as sf
torch.set_num_threads(4)
from qwen_asr import Qwen3ASRModel
start=time.monotonic()
engine=Qwen3ASRModel.from_pretrained('D:/AI/AI Lokal Asisten/AI Models/Qwen3-ASR-0.6B',dtype=torch.float16,
    device_map={'thinker.audio_tower':0,'thinker.model':1,'thinker.lm_head':1},
    max_inference_batch_size=1,max_new_tokens=256,attn_implementation='sdpa',local_files_only=True)
print('LOADED',time.monotonic()-start,flush=True)
counts={}
for name,p in engine.model.named_parameters():counts[str(p.device)]=counts.get(str(p.device),0)+p.numel()
print('PARAMETERS',counts,flush=True)
path=next(Path('D:/AI/AI Lokal Asisten/Leva/evaluation/asr-lab/audio').glob('*.wav'))
samples,rate=sf.read(path,dtype='float32')
from scipy.signal import resample_poly
from math import gcd
if samples.ndim>1:samples=samples.mean(axis=1)
if rate!=16000:
    g=gcd(rate,16000);samples=resample_poly(samples,16000//g,rate//g)
with torch.inference_mode(), torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
    result=engine.transcribe(audio=(samples,16000),language='Indonesian',return_time_stamps=False)
    for i in range(2):torch.cuda.synchronize(i)
events={}
for e in prof.events():
    if str(e.device_type).endswith('CUDA'):
        key=str(e.device_index);events[key]=events.get(key,0)+1
proof={'gpus':chosen,'parameters':counts,'cuda_event_counts':events,'text':result[0].text,
       'allocated_mib':[torch.cuda.memory_allocated(i)/2**20 for i in range(2)],'audio':str(path)}
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021');out.mkdir(parents=True,exist_ok=True)
(out/'dual-prototype.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(proof,ensure_ascii=True),flush=True)
