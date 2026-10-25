"""Offline intelligibility check; never a human voice similarity score."""
import json
import os
from pathlib import Path
import re
import time
import unicodedata

os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OMP_NUM_THREADS='4')
from faster_whisper import WhisperModel
import librosa
import soundfile as sf

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-bilingual-v3')
proof=json.loads((OUT/'proof.json').read_text('utf-8'))
model=WhisperModel(r'D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small',device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)

def tokens(text,language):
    text=unicodedata.normalize('NFKC',text).casefold()
    if language=='ja': return [c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P')]
    return re.sub(r'[^\w\s]',' ',text).split()

def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1): current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]

result={'model':'faster-whisper-small CPU int8','purpose':'intelligibility diagnostic, not speaker identity or independent benchmark',
        'metric_note':'Japanese raw CER, Indonesian raw WER after punctuation removal; numerals/kanji spellings not normalized',
        'shared_encoder_note':'Seed-VC uses Whisper-small features; ASR is not independent evidence of identity or quality','rows':[]}
for category in ('base','converted','references'):
    for row in proof[category]:
        language=row.get('language','ja')
        started=time.perf_counter()
        # These artifacts are verified mono WAVs. Decode explicitly to avoid
        # version-dependent PyAV metadata_errors handling, and specify 16 kHz.
        samples,rate=sf.read(row['path'],dtype='float32')
        samples=librosa.resample(samples,orig_sr=rate,target_sr=16000)
        segments,info=model.transcribe(samples,language=language,beam_size=3,vad_filter=True,condition_on_previous_text=False)
        text=' '.join(seg.text.strip() for seg in segments)
        ref,hyp=tokens(row['text'],language),tokens(text,language)
        errors=distance(ref,hyp)
        item={'id':row['id'],'category':category,'path':row['path'],'language':language,'transcript':text,
              'expected':row['text'],'metric':'cer' if language=='ja' else 'wer', 'errors':errors,
              'reference_units':len(ref),'error_rate':round(errors/max(1,len(ref)),4),
              'asr_seconds':round(time.perf_counter()-started,3)}
        result['rows'].append(item)
        (OUT/'asr-check.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'id':row['id'],'transcript':text,'error_rate':item['error_rate']},ensure_ascii=True),flush=True)
