"""Interactive UI fixture: synthetic knowledge, conversations and controls, no inference."""
import copy,json,queue,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from web_bridge import WebBridge
from web_store import WebStore
from profile_avatar import ProfileAvatar
from conversation_rooms import model_choices,GPUS

OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/workspace-v032');OUT.mkdir(parents=True,exist_ok=True)
stop=OUT/'stop-preview';stop.unlink(missing_ok=True)
nodes=[{'id':str(i),'label':'Catatan '+str(i),'category':['document','skill','task','activity','conversation'][i%5],
        'detail':{'path':'Note '+str(i)+'.md'},'source':{'kind':'fixture'}} for i in range(130)]
graph={'nodes':nodes,'edges':[{'source':str(i),'target':str((i+7)%130),'relation':'fixture_link'} for i in range(130)],'errors':[],'provenance':'Data contoh. Bintang latar dekoratif, bukan hubungan baru.'}
with tempfile.TemporaryDirectory(prefix='leva-workspace-ui-') as folder:
 base=Path(folder);reader=SimpleNamespace(graph=lambda:graph,panel=lambda name:{'title':'Panel uji','rows':[]})
 bridge=WebBridge(reader,port=8792,store=WebStore(base/'web.db'),avatar=ProfileAvatar(base/'avatar'));bridge.bootstrap='workspace-v032-fixture-only'
 state={'verification_mode':True,'phase':'idle','route':'Tanpa AI','route_choices':['Tanpa AI'],'workspace':'assistant','language':'ja','busy':False,
        'activity':'Uji antarmuka · tanpa model aktif','version':'0.32.0','room_models':model_choices('chat'),'room_gpus':GPUS,
        'hardware':{'cpu_percent':17,'ram_used_gib':18.2,'ram_total_gib':63.7,'measured_at':time.time(),'gpus':[{'name':'NVIDIA GeForce RTX 5070','used_mib':2300,'total_mib':12227,'utilization':12,'temperature_c':47}]},'hardware_age_s':0,
        'task_progress':[{'elapsed_s':i*.8,'label':'Membaca berkas contoh '+str(i),'status':'done','tool':'file_action'} for i in range(15)]}
 state['rooms']={r:{'models':model_choices(r),'gpus':GPUS,'model':'qwen4b' if r!='chat' else 'auto','gpu':'gpu5070'} for r in ('assistant','chat','secret')}
 bridge.update(state)
 bridge.log('Anda','Leva, bisa bantu merapikan ide untuk proyek baru?')
 bridge.log('Leva','Bisa, Raizei. Kita mulai dari bagian yang paling ingin kamu wujudkan. Ceritakan gambaran utamanya dulu; setelah itu aku bantu menyusun langkahnya.\n\nKalau sudah ada bahan, kamu bisa melampirkannya lewat tombol +.')
 bridge.log('Ucapan · 日本語','もちろん、ライゼイ。まずは一番実現したいことから始めよう。')
 for i in range(4):bridge.log('Anda' if i%2==0 else 'Leva','Percakapan contoh untuk menguji ruang, scroll, dan keterbacaan. '+('Konteks tetap tersimpan dan panel tidak saling menutupi. '*4))
 bridge.start();print(json.dumps({'url':'http://127.0.0.1:8792/#session=workspace-v032-fixture-only'}),flush=True)
 start=time.monotonic()
 try:
  while not stop.exists() and time.monotonic()-start<1800:
   try:
    job=bridge.controls.get_nowait()
    if job['kind']=='workspace':state['workspace']=job['value'];state['room_models']=model_choices(job['value']);bridge.update(copy.deepcopy(state))
    bridge.finish(job,'completed','Contrôle fixture; aucun modèle lancé.')
   except queue.Empty:pass
   time.sleep(.05)
 finally:bridge.stop();bridge.store.db.close()
