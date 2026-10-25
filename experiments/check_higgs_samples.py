"""Offline transcription diagnostic, not a naturalness or similarity judge."""
import json
import os
from pathlib import Path
import re
import time
import unicodedata

os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',OMP_NUM_THREADS='4')
import librosa
import soundfile as sf
from faster_whisper import WhisperModel

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\higgs-naturalness-20261020\rtx4050-final')

def units(text,language):
    text=unicodedata.normalize('NFKC',text).casefold()
    if language=='ja': return [c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P')]
    return re.sub(r'[^\w\s]',' ',text).split()

def distance(a,b):
    old=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1): new.append(min(new[-1]+1,old[j]+1,old[j-1]+(x!=y)))
        old=new
    return old[-1]

def main():
    proof=json.loads((OUT/'proof.json').read_text('utf-8'))
    model=WhisperModel(r'D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small',device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    result={'purpose':'ASR diagnostic only, not a listening review or speaker similarity test',
        'metric_note':'Punctuation stripped; spelling, kanji and numerals not normalized beyond NFKC',
        'model':'faster-whisper-small CPU int8','rows':[]}
    for row in proof['samples']:
        if not row.get('valid_audio'): continue
        start=time.perf_counter()
        samples,sr=sf.read(row['path'],dtype='float32')
        samples=librosa.resample(samples,orig_sr=sr,target_sr=16000)
        segments,_=model.transcribe(samples,language=row['language'],beam_size=3,vad_filter=True,condition_on_previous_text=False)
        transcript=' '.join(seg.text.strip() for seg in segments)
        expected,hyp=units(row['text'],row['language']),units(transcript,row['language'])
        item={'id':row['id'],'text':row['text'],'transcript':transcript,'language':row['language'],
            'raw_error_rate':distance(expected,hyp)/max(len(expected),1),'seconds':time.perf_counter()-start}
        result['rows'].append(item)
        (OUT/'asr-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(item,ensure_ascii=True),flush=True)

if __name__=='__main__': main()
