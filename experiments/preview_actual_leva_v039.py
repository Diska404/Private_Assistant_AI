"""Actual authenticated WebBridge/VRM renderer; isolated state, original asset read only."""
import copy,json,queue,sys,time
from pathlib import Path
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\actual-leva-intake-20261025');OUT.mkdir(exist_ok=True)
import paths
paths.DATA=OUT/'fixture-data';paths.DATA.mkdir(exist_ok=True)
import avatar_assets
avatar_assets.FOLDER=Path(r'D:\AI\AI Lokal Asisten\Leva\avatar-assets')
from web_bridge import WebBridge
from web_store import WebStore
from preview_companion_fixture import state as template
state=copy.deepcopy(template);state['avatar'].update(asset='leva_original',renderer_gpu='rtx4050',asset_choices=avatar_assets.choices(),realtime_speech=False,native_stream=False)
state['rooms']={room:{'model':'fixture','gpu':'fixture','models':{'fixture':'Preview tanpa inferensi'},'gpus':{'fixture':'Tidak memuat LLM'}} for room in ('assistant','chat','secret','companion_avatar')}
state['activity']='PREVIEW LEVA ASLI · sumber tidak diubah · tidak memuat LLM/mikrofon'
reader=Mock();reader.graph.return_value={'nodes':[],'edges':[]}
bridge=WebBridge(reader,port=20289,store=WebStore(paths.DATA/'web.sqlite3'))
bridge.update(state);bridge.log('Leva · Preview','Avatar VRM Leva asli dari berkas lokal. Material sumber dipertahankan; ini preview sementara untuk penilaian visual.')
url=bridge.start();(OUT/'fixture-url.txt').write_text(url,encoding='utf8')
bridge.ui_last_seen=time.monotonic()
if '--open' in sys.argv:
 import webbrowser
 webbrowser.open(url)
clip=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\higgs-naturalness-20261020\rtx4050-final\ja_long_leva_A.wav')
try:
 print('Actual Leva preview on loopback port '+str(bridge.server.server_port),flush=True)
 while not (OUT/'stop-fixture').exists() and time.monotonic()-bridge.ui_last_seen<600:
  try:job=bridge.controls.get(timeout=.1)
  except queue.Empty:continue
  kind=job['kind'];value=job.get('value')
  if kind=='workspace':state['workspace']=value
  elif kind=='companion_settings':
   if value.get('asset') in avatar_assets.choices():state['avatar']['asset']=value['asset']
   state['avatar']['enabled']=value.get('enabled',True)
  elif kind=='test_audio' and clip.is_file():
   bridge.publish_audio(clip,{'fixture':True,'pack':'higgs_leva','language':'ja'});state['avatar']['state']='speaking'
  elif kind in ('stop_voice','companion_stop'):
   bridge.cancel_audio();state['avatar']['state']='interrupted';state['avatar']['generation_id']+=1
  bridge.update(state);bridge.finish(job,'completed','Preview terisolasi; tidak menjalankan agent atau mikrofon.')
finally:bridge.stop();bridge.store.close()
