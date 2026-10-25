"""Actual Higgs SSE -> reply controller -> paced PCM sink, without audio devices."""
import sys,time,json,shutil,wave,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from reply_voice import ReplyVoice,speech_chunks
from voice_pack_service import VoicePackService
from stream_playback import StreamPlayback
from web_audio import WebAudio
OUT=DATA/'verification/visual-voice-v027';OUT.mkdir(parents=True,exist_ok=True)
prior=json.loads((OUT/'long-voice-proof.json').read_text('utf8'));audio=WebAudio();report={'speaker_opened':False,'microphone_opened':False,'real_sse_engine':True,'sink':'paced PCM in memory, no audio device','runs':[]}
class ProofService(VoicePackService):
 def __init__(self):super().__init__(persistent=True);self.clips=[];self.first_play=None;self.began=0;self.byte_count=0;self.language_key=''
 def accept_generated(self,event):
  super().accept_generated(event);target=OUT/('stream-'+self.language_key+'-'+str(len(self.clips)+1)+'.wav');shutil.copyfile(self.generated,target)
  self.clips.append({**event,'path':str(target),'completed_at_s':time.monotonic()-self.began})
class Sink:
 def __init__(self,rate,owner):self.rate=rate;self.owner=owner
 def start(self):
  if self.owner.first_play is None:self.owner.first_play=time.monotonic()-self.owner.began
 def write(self,raw):self.owner.byte_count+=len(raw);time.sleep(len(raw)/(self.rate*2))
 def stop(self):pass
 def abort(self):pass
 def close(self):pass
service=ProofService();service.gpu_preference='rtx5070';service.audio_ready_callback=audio.publish;service.stream_audio=True
voice=ReplyVoice(service);voice.stream_factory=lambda owner:StreamPlayback(owner,lambda rate:Sink(rate,owner))
try:
 for original in prior['runs']:
  language=original['language'];text=original['text'];service.language_key=language;service.clips=[];service.byte_count=0;service.first_play=None;service.began=time.monotonic();notices=[]
  voice.speak(text,'higgs_leva',language,'assistant')
  while voice.active:
   notices.extend(voice.poll())
   if time.monotonic()-service.began>240:raise TimeoutError('stream_reply_proof_timeout')
   time.sleep(.02)
  if voice.failed_chunks or not service.clips:raise RuntimeError('incomplete_stream_reply: '+str(notices))
  # Recovery may split an unplayed sentence. This is recorded, not disguised as
  # an uninterrupted success; all PCM and completed utterances are still checked.
  expected=sum(r['pcm_bytes'] for r in service.clips)
  assert service.byte_count==expected,(service.byte_count,expected)
  assert service.first_play<service.clips[0]['completed_at_s'],(service.first_play,service.clips[0]['completed_at_s'])
  target=OUT/('stream-long-'+language+'-leva.wav')
  with wave.open(str(target),'wb') as result:
   result.setnchannels(1);result.setsampwidth(2);result.setframerate(24000)
   for clip in service.clips:
    with wave.open(clip['path'],'rb') as source:result.writeframes(source.readframes(source.getnframes()))
  row={'language':language,'characters':len(text),'planned_sentences':len(speech_chunks(text,language)),'completed_sentences':len(service.clips),'first_play_s':service.first_play,'first_sentence_done_s':service.clips[0]['completed_at_s'],'wall_s':time.monotonic()-service.began,'duration_s':expected/48000,'pcm_bytes_delivered':service.byte_count,'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'stream_chunks':sum(c['stream_chunks'] for c in service.clips),'web_clips_retained':len(audio.manifest()['clips']),'notices':notices,'clips':service.clips}
  report['runs'].append(row);(OUT/'stream-reply-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in row.items() if k!='clips'}),flush=True)
finally:
 voice.stop();(OUT/'stream-reply-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
