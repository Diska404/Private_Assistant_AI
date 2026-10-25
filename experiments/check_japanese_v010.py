"""Local intelligibility diagnostic, not a speaker-identity or human-similarity score."""
import json
import os
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4')
import soundfile as sf
from scipy.signal import resample_poly
from faster_whisper import WhisperModel
from math import gcd

out=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\japanese-v010')
model=WhisperModel(r'D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small',device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
proof={'model':'faster-whisper-small CPU int8','purpose':'intelligibility diagnostic only; same encoder family is used by Seed-VC, not independent voice similarity evidence','network_used':False,'rows':[]}
for name in ('japanese-1.wav','japanese-2.wav','native-ui-response.wav'):
    data,rate=sf.read(out/name,dtype='float32');factor=gcd(rate,16000)
    audio=resample_poly(data,16000//factor,rate//factor)
    segments,info=model.transcribe(audio,language='ja',beam_size=3,vad_filter=False)
    proof['rows'].append({'file':name,'transcript':''.join(s.text for s in segments),'language':info.language})
(out/'asr-check.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=True))
