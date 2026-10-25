import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from web_bridge import WebBridge
from web_store import WebStore
from profile_avatar import ProfileAvatar
from task_progress import TaskProgress
from preferences import DEFAULTS
from presence_companion import KEYS,validate_settings
from conversation_rooms import model_choices,GPUS
from leva_persona import PersonaDelivery
import queue
from conversation_export import transcript
OUT=Path(r'D:/AI/AI Lokal Asisten/Leva/verification/companion-presence-v030');OUT.mkdir(parents=True,exist_ok=True)
class Reader:
 def graph(self):return {'nodes':[],'edges':[],'errors':[]}
 def panel(self,name):return {'title':'Verifikasi UI','rows':[]}
bridge=WebBridge(Reader(),port=0,store=WebStore(),avatar=ProfileAvatar(OUT/'fixture-profile'))
p=TaskProgress();p.begin('Asisten');p.add('understand','Memahami permintaan contoh');p.tool('file_action',{'action':'read'});p.tool('file_action',{'action':'read'},{'status':'done'});p.tool('terminal',{'action':'poll'},{'status':'failed'});p.add('response','Contoh: perlu memperbaiki kesalahan pengujian','needs_input')
rows=[('Anda' if i%2==0 else 'Leva','Catatan pengujian lengkap nomor '+str(i)) for i in range(161)]
rows[-2:]=[('Anda','Tolong periksa hasil program dan jelaskan bila ada yang gagal.'),('Leva','Raizei, berkas contoh sudah diperiksa. Pengujian contoh masih gagal; hasil ini belum dinyatakan selesai. Rincian status ada pada panel Proses Leva. Ini data contoh untuk memeriksa antarmuka.')]
for s,t in rows[-8:]:bridge.log(s,t)
bridge.transcript_provider=lambda room:transcript(rows,room,{'verification_mode':True,'task_progress':p.snapshot()})
config={k:DEFAULTS[k] for k in KEYS};delivery=PersonaDelivery()
state={'companion':config,'rooms':{r:{'model':'qwen4b','gpu':'gpu5070','models':model_choices(r),'gpus':GPUS} for r in ('chat','secret')},'verification_mode':True,'workspace':'assistant','phase':'idle','busy':False,'route':'RTX 5070','route_choices':['Tanpa AI','RTX 4050','RTX 5070','Dual GPU'],'dual':False,'spoken':False,'language':'ja','task_progress':p.snapshot(),'activity':'Verifikasi tampilan · data contoh, tanpa menjalankan model','hardware':{},'hardware_age_s':0,'translation_progress':{'completed':2,'total':4},'voice_progress':{},'mic':{},'pipeline_settings':{}}
bridge.update(state)
url=bridge.start();(OUT/'ui-fixture.json').write_text(json.dumps({'url':url,'origin':bridge.origin}),encoding='utf8');print(url,flush=True)
try:
 while not (OUT/'stop-ui-fixture').exists():
  for channel in (bridge.controls,bridge.commands):
   try:job=channel.get_nowait()
   except queue.Empty:continue
   if job['kind']=='persona_settings':state['companion']=validate_settings(job['value'])
   elif job['kind']=='workspace':
    state['workspace']=job['value'];bridge.logs.clear();row=delivery.greeting(room=job['value']);bridge.log('Leva',row['text'])
   elif job['kind']=='chat':
    value=job['value'];bridge.log('Anda',value['text']);bridge.log('Leva','Contoh balasan UI. Tidak ada model atau kendali laptop dijalankan pada fixture ini.')
   bridge.update(state);bridge.finish(job,'completed','Pengaturan fixture tersimpan.')
  time.sleep(.05)
finally:bridge.stop();bridge.store.db.close()
