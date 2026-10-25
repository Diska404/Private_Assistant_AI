"""Real model/tool IPC with fixture launch receipts; does not launch apps or games."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from assistant_tools import effective_speech_language
from chat_service import ChatService
from desktop_service import DesktopService
from preferences import Preferences
from paths import DATA

out=DATA/'verification/voice-steam-v011';out.mkdir(parents=True,exist_ok=True)
packaged='--exe' in sys.argv
exe=Path(sys.argv[sys.argv.index('--exe')+1]).resolve() if packaged else None
service=ChatService([str(exe),'--chat-session-worker'],persistent=True) if packaged else ChatService()
proof={'status':'running','packaged':packaged,'network_used':False,'launches':'fixtures only','rows':[]}
destination=out/('packaged-model-proof.json' if packaged else 'source-model-proof.json')
def save():destination.write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
with tempfile.TemporaryDirectory() as folder:
    prefs=Preferences(Path(folder)/'prefs.sqlite3')
    desktop=DesktopService(preferences=prefs);tools=desktop.tools
    tools.apps.launch=Mock(return_value={'status':'done','reply':'Fixture Steam: jendela terdeteksi.','fixture':True})
    tools.steam.launch=Mock(return_value={'status':'unverified','reply':'Fixture GFL2: permintaan terkirim, jendela belum terkonfirmasi.','fixture':True})
    proof['real_inventory']={'steam':bool(tools.apps.resolve('Steam')),'gfl2':tools.steam.resolve('gfl2')['id'] if tools.steam.resolve('gfl2') else None}
    try:
        for prompt,expected in [('ubah modul suara mu ke bahasa jepang','ja'),('gunakan kembali modul suara indonesia','id'),('coba buka steam dulu','open_app'),('bukakan steam dan jalankan gfl2 exilium','launch_game')]:
            service.history=[];started=time.monotonic()
            if expected in ('ja','id'):
                result=desktop.handle(prompt)
                ok=result.get('voice_language')==expected and prefs.get('speech_language')==expected
            else:
                result=service.ask(prompt,'local',local_model='saluki',acceleration='mtp',keep_warm=True,tool_executor=lambda n,a,v:tools.execute(n,a,prompt,v),tool_context=tools.context(prompt),speech_language=prefs.get('speech_language'))
                ok=any(r['name']==expected for r in result.get('tool_receipts',[]))
            proof['rows'].append({'prompt':prompt,'expected':expected,'passed':ok,'elapsed_seconds':round(time.monotonic()-started,3),'result':result})
            save();print(json.dumps(proof['rows'][-1],ensure_ascii=True),flush=True)
            if not ok:raise AssertionError('Unexpected tool/setting: '+expected)
        proof['status']='passed'
    except Exception as error:proof.update(status='failed',error=str(error))
    finally:service.cancel();prefs.close();proof['worker_released']=service.process is None;save()
if proof['status']!='passed':sys.exit(1)
