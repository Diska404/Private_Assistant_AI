"""Anchor the user-liked generated Japanese native voice for bilingual comparison."""
import hashlib,json,os
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='4')
import soundfile as sf
import librosa
from faster_whisper import WhisperModel

DATA=Path(r'D:\AI\AI Lokal Asisten\Leva')
source=DATA/'verification/higgs-naturalness-20261020/rtx4050-final/ja_long_native.wav'
out=DATA.parent/'AI Models/Leva-GFL2/Higgs-JP-native-reference-v1'
out.mkdir(parents=True,exist_ok=True)
audio,sr=sf.read(source,dtype='float32')
model=WhisperModel(str(DATA.parent/'AI Models/faster-whisper-small'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
segments,_=model.transcribe(librosa.resample(audio,orig_sr=sr,target_sr=16000),language='ja',word_timestamps=True,beam_size=3,condition_on_previous_text=False)
words=[w for seg in segments for w in (seg.words or [])]
chosen=[w for w in words if w.end<=7.0]
if not chosen or chosen[-1].end<3:raise RuntimeError('reference_alignment_too_short')
end=min(len(audio)/sr,chosen[-1].end+.08)
path=out/'japanese_native_reference.wav';sf.write(path,audio[:int(end*sr)],sr,subtype='PCM_16')
def sha(p):
    with p.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
profile={'path':str(path),'sha256':sha(path),'text':''.join(w.word for w in chosen).strip(),
    'source':str(source),'source_sha256':sha(source),'source_generated':True,'duration_seconds':end,
    'alignment':'Whisper-small word timestamps; local diagnostic, not verified verbatim transcription',
    'purpose':'Compare Indonesian and Japanese using the same user-liked Japanese native identity reference; not a trained Leva checkpoint'}
(out/'profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(profile,ensure_ascii=True))
