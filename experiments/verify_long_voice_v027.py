"""Exercise the production reply queue with real Higgs inference, without playback."""
import sys,time,json,wave,shutil,threading,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from reply_voice import ReplyVoice,speech_chunks
from voice_pack_service import VoicePackService
OUT=DATA/'verification/visual-voice-v027';OUT.mkdir(parents=True,exist_ok=True)
prompts={
 'ja':'お帰りなさい。今日はあなたの予定を一緒に確認しましょう。まず、今夜の課題を整理してから、必要な資料を開きます。急ぐ必要はありません。わからないところがあれば、一つずつ考えていきましょう。作業が終わったら、結果を確認して、次の予定をまとめます。途中で私の説明を止めたいときは、そのまま話しかけてください。あなたの声を聞いて、説明を止めます。長い返事でも、文章を短い部分に分けて順番に話します。画面には全体の内容が残ります。今日はどの作業から始めますか。',
 'id':'Aku siap menemanimu menyelesaikan pekerjaan hari ini. Kita mulai dengan memeriksa jadwal, lalu membuka bahan belajar yang dibutuhkan. Kalau penjelasanku terlalu panjang, kamu boleh menyela dan mengarahkan percakapan. Aku akan menghentikan suara lebih dahulu tanpa membatalkan pekerjaan yang sedang berjalan. Setelah tugas selesai, kita periksa hasilnya bersama. Untuk jawaban panjang, aku membagi ucapan menjadi beberapa bagian agar proses pembentukan suara lebih stabil. Bagian yang sudah selesai tidak perlu dibacakan ulang saat satu bagian dicoba kembali. Semua isi jawaban tetap tersedia sebagai teks agar mudah kamu periksa.'}
class SilentProofService(VoicePackService):
 def __init__(self):super().__init__(persistent=True);self.language_key='';self.clips=[];self.total=[]
 def play(self):
  if not self.can_play:return False
  index=len(self.clips)+1;path=OUT/(self.language_key+'-'+str(index)+'.wav');shutil.copyfile(self.generated,path)
  self.clips.append({**(self.last_result or {}),'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
  self.events.put_nowait({'kind':'playback_started'});self.events.put_nowait({'kind':'playback_finished'});return True
def stats():
 rows=[]
 try:
  value=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000)
  for line in value.splitlines():
   name,used,load=line.rsplit(',',2);rows.append({'gpu':name.strip(),'used_mib':int(used),'utilization':int(load)})
 except Exception:pass
 return rows
service=SilentProofService();service.gpu_preference='rtx5070';voice=ReplyVoice(service);report={'speaker_opened':False,'microphone_opened':False,'pack':'higgs_leva','tts_gpu':'rtx5070','streaming':'sentence_queue_offline_engine','runs':[]};metrics=[];stop=threading.Event()
def sample():
 while not stop.is_set():metrics.append({'at':time.time(),'gpus':stats()});stop.wait(1)
thread=threading.Thread(target=sample,daemon=True);thread.start()
try:
 for language,text in prompts.items():
  service.language_key=language;service.clips=[];notices=[];began=time.monotonic();first=None
  voice.speak(text,'higgs_leva',language,'assistant')
  while voice.active:
   notices.extend(voice.poll())
   if service.clips and first is None:first=time.monotonic()-began
   if time.monotonic()-began>600:raise TimeoutError('long_voice_proof_timeout')
   time.sleep(.025)
  if voice.failed_chunks or len(service.clips)!=len(speech_chunks(text,language)):raise RuntimeError('incomplete_voice_proof')
  output=OUT/('long-'+language+'-leva.wav');duration=0
  with wave.open(str(output),'wb') as target:
   for index,row in enumerate(service.clips):
    with wave.open(row['path'],'rb') as clip:
     if not index:target.setparams(clip.getparams())
     target.writeframes(clip.readframes(clip.getnframes()));duration+=clip.getnframes()/clip.getframerate()
  result={'language':language,'text':text,'characters':len(text),'planned_chunks':len(speech_chunks(text,language)),'completed_chunks':len(service.clips),'failed_chunks':voice.failed_chunks,'first_clip_s':first,'wall_s':time.monotonic()-began,'duration_s':duration,'path':str(output),'notices':notices,'clips':service.clips}
  report['runs'].append(result);(OUT/'long-voice-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({k:v for k,v in result.items() if k not in ('clips','text')},ensure_ascii=True),flush=True)
finally:
 voice.stop();stop.set();thread.join(2);report['gpu_samples']=metrics;(OUT/'long-voice-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
