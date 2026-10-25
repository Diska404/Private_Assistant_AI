"""Real local model/tool IPC probe. Application launches use clearly labelled fixtures."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from chat_service import ChatService
from desktop_service import DesktopService
from assistant_tools import PersonalMemory
from paths import DATA

out=DATA/'verification/agent-v010';out.mkdir(parents=True,exist_ok=True)
packaged='--exe' in sys.argv
exe=Path(sys.argv[sys.argv.index('--exe')+1]).resolve() if packaged else None
service=ChatService([str(exe),'--chat-session-worker'],persistent=True) if packaged else ChatService()
inventory={'profiles':[{'id':'fixture-diska','name':'Diska','channel':'stable','profile_directory':'Profile 1','user_data_root':'C:/fixture','directory_exists':True}]}
with patch('desktop_service.inspect_profiles',return_value=inventory):desktop=DesktopService(browser=Mock())
desktop.browser.launch.return_value={'dispatched':True,'new_window_observed':True,'fixture':True}
tools=desktop.tools;tools.memory=PersonalMemory(out/'fixture-memory.sqlite3')
tools.apps.launch=lambda app,authorized=lambda:True:{'status':'done','reply':'Fixture saja: permintaan '+app+' tervalidasi; tidak membuka aplikasi nyata.','fixture':True}
proof={'status':'running','model':'Saluki MTP','packaged_worker':packaged,'network_used':False,'app_launches':'fixture only, not actual execution','microphone_opened':False,'rows':[]}
def save():(out/('packaged-proof.json' if packaged else 'source-proof.json')).write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
try:
    for prompt,language,clear in [
        ('Hai Leva, jawab satu kalimat singkat.','id',False),
        ('Menurut jam komputer saya, sekarang pukul berapa?','id',False),
        ('Aku mau ngobrol di Discord, tolong siapkan aplikasinya.','id',False),
        ('Buka ChatGPT menggunakan Chrome dan profil Diska.','id',False),
        ('Ingat bahwa kode uji preferensiku adalah uji-010.','id',True),
        ('Apa kode uji preferensi yang kusimpan? Cek memorimu.','id',True),
        ('Jawab singkat bahwa kamu siap membantu saya.','ja',True)]:
        if clear:service.history=[]
        started=time.monotonic()
        result=service.ask(prompt,'local',local_model='saluki',acceleration='mtp',keep_warm=True,
            tool_executor=lambda name,args,valid:tools.execute(name,args,prompt,valid),tool_context=tools.context(),speech_language=language)
        row={'prompt':prompt,'speech_language':language,'elapsed_seconds':round(time.monotonic()-started,3),'result':result}
        proof['rows'].append(row);save();print(json.dumps(row,ensure_ascii=True),flush=True)
    proof['status']='completed'
except Exception as error:proof.update(status='failed',error=str(error))
finally:service.cancel();proof['worker_released']=service.process is None;save()
