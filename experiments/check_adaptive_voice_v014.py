"""Read-only, local ASR diagnostic for the new controlled comparisons."""
import hashlib
import json
from pathlib import Path
import time
from check_higgs_samples import units,distance
import librosa
import soundfile as sf
from faster_whisper import WhisperModel

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\adaptive-voice-v014\final')

def main():
    proof=json.loads((OUT/'proof.json').read_text('utf-8'))
    model=WhisperModel(r'D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small',device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    result={'purpose':'transcription diagnostic only; human naturalness and identity judgment pending','rows':[]}
    for row in proof['samples']:
        with Path(row['path']).open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=row['sha256']:raise RuntimeError('changed_audio')
        samples,sr=sf.read(row['path'],dtype='float32');samples=librosa.resample(samples,orig_sr=sr,target_sr=16000)
        start=time.perf_counter();segments,_=model.transcribe(samples,language=row['language'],beam_size=3,vad_filter=True,condition_on_previous_text=False)
        transcript=' '.join(s.text.strip() for s in segments)
        ref,hyp=units(row['text'],row['language']),units(transcript,row['language'])
        item={'id':row['id'],'transcript':transcript,'expected':row['text'],'raw_error_rate':distance(ref,hyp)/max(1,len(ref)),'asr_seconds':time.perf_counter()-start}
        result['rows'].append(item);(OUT/'asr-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(item,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
