import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from web_bridge import WebBridge
from web_store import WebStore
from profile_avatar import ProfileAvatar
from task_progress import TaskProgress
from conversation_export import transcript
OUT=Path(r'D:/AI/AI Lokal Asisten/Leva/verification/conversation-reliability-v029');OUT.mkdir(parents=True,exist_ok=True)
class Reader:
 def graph(self):return {'nodes':[],'edges':[],'errors':[]}
 def panel(self,name):return {'title':'Verifikasi UI','rows':[]}
bridge=WebBridge(Reader(),port=0,store=WebStore(),avatar=ProfileAvatar(OUT/'fixture-profile'))
p=TaskProgress();p.begin('Asisten');p.add('understand','Memahami permintaan contoh');p.tool('file_action',{'action':'read'});p.tool('file_action',{'action':'read'},{'status':'done'});p.tool('terminal',{'action':'poll'},{'status':'failed'});p.add('response','Contoh: perlu memperbaiki kesalahan pengujian','needs_input')
rows=[('Anda' if i%2==0 else 'Leva','Catatan pengujian lengkap nomor '+str(i)) for i in range(161)]
rows[-2:]=[('Anda','Tolong periksa hasil program dan jelaskan bila ada yang gagal.'),('Leva','Raizei, berkas contoh sudah diperiksa. Pengujian contoh masih gagal; hasil ini belum dinyatakan selesai. Rincian status ada pada panel Proses Leva. Ini data contoh untuk memeriksa antarmuka.')]
for s,t in rows[-8:]:bridge.log(s,t)
bridge.transcript_provider=lambda room:transcript(rows,room,{'verification_mode':True,'task_progress':p.snapshot()})
bridge.update({'verification_mode':True,'workspace':'assistant','phase':'idle','busy':False,'route':'RTX 5070','route_choices':['Tanpa AI','RTX 4050','RTX 5070','Dual GPU'],'dual':False,'spoken':False,'language':'ja','task_progress':p.snapshot(),'activity':'Verifikasi tampilan · data contoh, tanpa menjalankan model','hardware':{},'hardware_age_s':0,'translation_progress':{'completed':2,'total':4},'voice_progress':{},'mic':{},'pipeline_settings':{}})
url=bridge.start();(OUT/'ui-fixture.json').write_text(json.dumps({'url':url,'origin':bridge.origin}),encoding='utf8');print(url,flush=True)
try:
 while not (OUT/'stop-ui-fixture').exists():time.sleep(.3)
finally:bridge.stop();bridge.store.db.close()
