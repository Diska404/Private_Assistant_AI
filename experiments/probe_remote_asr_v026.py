"""Real whole-utterance phone-ASR worker using cached synthetic Indonesian speech."""
from pathlib import Path
import json,time,wave,audioop,io,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from remote_speech import RemoteSpeech
from task_reactions import cached_reaction
path=cached_reaction('higgs_leva','id')
if path is None:raise RuntimeError('cached_reference_missing')
with wave.open(str(path),'rb') as f:
    pcm=f.readframes(f.getnframes());rate=f.getframerate();channels=f.getnchannels();width=f.getsampwidth()
if width!=2:raise RuntimeError('pcm16_required')
if channels==2:pcm=audioop.tomono(pcm,2,.5,.5)
pcm,_=audioop.ratecv(pcm,2,1,rate,16000,None)
buffer=io.BytesIO()
with wave.open(buffer,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
speech=RemoteSpeech();started=time.monotonic()
try:
    speech.submit('real-asr-v026-dual','verification',buffer.getvalue())
    speech.pump({'model':'qwen_asr_06b','gpu':'dual','language':'id'},lambda owner:True,lambda:None)
    while speech.pending() and time.monotonic()-started<135:time.sleep(.2)
    result=speech.get('real-asr-v026-dual','verification')
    result.update(seconds=round(time.monotonic()-started,2),fixture='cached assistant Indonesian speech, not live human microphone',microphone_open=False)
    out=Path('D:/AI/AI Lokal Asisten/Leva/verification/host-access-v026/remote-asr-proof.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True))
    if result['status']!='completed':raise SystemExit(1)
finally:speech.stop()
