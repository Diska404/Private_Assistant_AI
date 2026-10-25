"""Real Saluki harness proof against requested files and read-only room-lamp status."""
import json
from pathlib import Path
import queue
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from agent_runtime import _run_agent
from file_workspace import FileWorkspace,known_folders
from iot_lamp import RoomLamp
from saluki_backend import SalukiEngine
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/host-access-v026');OUT.mkdir(parents=True,exist_ok=True)
engine=SalukiEngine(OUT/'agent-runtime',mode='dual',acceleration='plain',max_output_tokens=1024)
goals=[
 'Leva, bisakah kamu mengontrol lampu kamar ESP8266 saya di 192.168.0.171? Periksa status saja, jangan mengubah lampu.',
 'Leva, baca folder dokumen>arduino>Smarthome_IoT lalu baca kode Arduino dan jelaskan endpoint HTTP yang bisa dipakai untuk lampu. Jangan ubah kode atau jalankan program.',
 'Leva, cari file Matematika Diskrit 2026-05.pdf di unduhan lalu baca halaman 1 dan 2, ringkas materinya. Jangan mengubah file.'
]
proof=[]
try:
 for index,goal in enumerate(goals):
    commands=queue.Queue();files=FileWorkspace(OUT/'file-history');receipts=[];start=time.monotonic()
    def emit(event):
        if event.get('kind')!='tool_call':return
        name=event['name'];args=event['args']
        try:
            if name=='file_action' and args['action'] in ('roots','list','search','read'):result=files.run(args,goal)
            elif name=='iot_action' and args['action'] in ('list','status'):result=RoomLamp().run(args,goal)
            elif name=='discover_tools':result={'status':'done','reply':'Gunakan files atau connectors.'}
            else:result={'status':'failed','reply':'Uji ini hanya membaca berkas dan status lampu. Tidak ada perubahan diizinkan.'}
        except (ValueError,OSError) as error:result={'status':'failed','code':str(error) if isinstance(error,ValueError) else type(error).__name__,'retryable':True,'reply':'Gunakan known_folders/roots, search nama lalu read hasilnya.'}
        receipts.append({'name':name,'args':args,'status':result['status'],'code':result.get('code'),'total_pages':result.get('total_pages'),'total_lines':result.get('total_lines')})
        print(json.dumps({'case':index,**receipts[-1]}),flush=True)
        commands.put({'kind':'tool_result','id':index+1,'call_id':event['call_id'],'result':result})
    result=_run_agent({'id':index+1,'mode':'local','speech_language':'id','time_budget_seconds':180,'messages':[{'role':'user','content':goal}],
       'tool_context':{'known_folders':{k:str(v) for k,v in known_folders().items()},'lan_devices':[RoomLamp().public()],'client':{'kind':'android','name':'Android verification','executor':'laptop Windows'}}},engine,commands,emit)
    ok=any(r['status']=='done' and (r['name']=='iot_action' if index==0 else r['name']=='file_action' and r['args']['action']=='read') for r in receipts) and not result.get('incomplete')
    proof.append({'case':index,'seconds':round(time.monotonic()-start,2),'receipts':receipts,'response':result.get('response'),'ok':ok})
    (OUT/'real-agent-proof.json').write_text(json.dumps({'model':'Saluki 27B IQ2-mix','gpu':'dual','cases':proof,'no_lamp_state_change':True},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'case':index,'ok':ok,'seconds':proof[-1]['seconds']}),flush=True)
finally:engine.close()
if not all(p['ok'] for p in proof):raise SystemExit(1)
