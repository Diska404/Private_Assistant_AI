"""Transcribe an existing synthetic reference on the requested GPU; never open mic."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from speech_asr import SpeechASR
root=Path('D:/AI/AI Lokal Asisten/Leva/verification/speech-v019')
root.mkdir(parents=True,exist_ok=True)
gpu=sys.argv[1]
source=Path('D:/AI/AI Lokal Asisten/Leva/verification/adaptive-voice-v014/final/higgs_leva_id_assistant.wav')
started=time.monotonic()
engine=SpeechASR('qwen_asr_06b',gpu)
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd
samples,rate=sf.read(source,dtype='float32')
if samples.ndim==2:samples=samples.mean(axis=1)
factor=gcd(rate,16000)
samples=resample_poly(samples,16000//factor,rate//factor)
rows=[engine.transcribe(samples,'id') for _ in range(2)]
import torch
proof={'gpu_preference':gpu,'model':'Qwen3-ASR-0.6B','source':str(source),
       'reference_text':'Aku di sini. Mau kita lanjutkan pekerjaanmu, atau kamu ingin bercerita sebentar?',
       'load_ms':engine.load_ms,'results':rows,'max_allocated_mib':round(torch.cuda.max_memory_allocated()/1024**2,1),
       'max_reserved_mib':round(torch.cuda.max_memory_reserved()/1024**2,1),'total_seconds':round(time.monotonic()-started,3),
       'microphone_opened':False,'playback':False,'synthetic_audio':True,'streaming':False}
(root/('asr-'+gpu+'.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=True))
