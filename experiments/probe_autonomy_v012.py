"""Real local LLM/IPC, fixture desktop/web outcomes. No actual UI actions or web requests."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import Mock
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app'),str(Path(__file__).resolve().parent)]
from chat_service import ChatService
from desktop_service import DesktopService
from preferences import Preferences
from conversation_memory import ConversationMemory
from paths import DATA

class Fixtures:
    def __init__(self):self.typed=''
    def stop(self):pass
    def run(self,name,args,*rest,**kwargs):
        if name=='web_search':return {'status':'done','reply':'Fixture pencarian; bukan hasil internet nyata.','sources':[{'title':'Diskusi baterai Acer','url':'https://fixture.invalid/unrelated','snippet':'Baterai, tidak membahas eGPU.'},{'title':'Komunitas eGPU Helios Neo 16','url':'https://fixture.invalid/helios','snippet':'Pengalaman eGPU pada Helios Neo 16.'},{'title':'Pengalaman Acer Nitro eGPU','url':'https://fixture.invalid/nitro','snippet':'Perbandingan koneksi laptop Acer Nitro.'}],'fixture':True}
        if name=='read_webpage':return {'status':'done','reply':'Fixture artikel dibaca.','url':args['url'],'content':'DATA UJI SAJA: '+('Baterai saja; tidak relevan eGPU.' if 'unrelated' in args['url'] else 'Diskusi komunitas mengenai eGPU pada Acer. Cek model laptop dan jenis port sebelum membandingkan.'),'fixture':True}
        if name=='list_windows':return {'status':'done','reply':'Fixture jendela.','windows':[{'window':'7','title':'Notepad fixture','pid':123}],'fixture':True}
        if name=='computer_action':
            if args['action']=='type':self.typed=args['text'];return {'status':'dispatched','reply':'Fixture input terkirim, inspect untuk memverifikasi.','fixture':True}
            return {'status':'done','reply':'Fixture inspeksi.','window':'7','elements':[{'element':'fixture:1','name':'Editor','observed_text':self.typed,'type':'Document','enabled':True}],'fixture':True}
        if name=='get_metrics':return {'status':'done','reply':'Fixture metrik.','cpu_percent':12,'gpus':[{'name':'RTX 4050','used_mib':1400}],'fixture':True}
        return {'status':'failed','reply':'Fixture tidak menyediakan '+name,'fixture':True}

out=DATA/'verification/autonomy-v012';out.mkdir(parents=True,exist_ok=True)
packaged='--exe' in sys.argv
command=[str(Path(sys.argv[sys.argv.index('--exe')+1]).resolve()),'--chat-session-worker'] if packaged else None
service=ChatService(command,persistent=True)
proof={'status':'running','packaged':packaged,'model':'Saluki MTP, 8192 context','network':False,'desktop_actions':'fixtures only','rows':[]}
qwen='--qwen' in sys.argv
hybrid='--hybrid' in sys.argv
if qwen:proof['model']='Qwen 4B RTX 4050, 8192 context'
if hybrid:proof['network']=True;proof['model']='Google first, local fallback '+proof['model']
destination=out/('packaged-agent-proof.json' if packaged else 'source-agent-proof.json')
if qwen:destination=out/('packaged-qwen-proof.json' if packaged else 'source-qwen-proof.json')
if hybrid:destination=out/('packaged-hybrid-proof.json' if packaged else 'source-hybrid-proof.json')
def save():destination.write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
with tempfile.TemporaryDirectory() as folder:
    prefs=Preferences(Path(folder)/'prefs.sqlite3');desktop=DesktopService(preferences=prefs);tools=desktop.tools
    tools._bridge=Fixtures();tools.conversations=ConversationMemory(Path(folder)/'memory.sqlite3')
    tools.conversations.record('Laptop uji saya adalah Acer Helios Neo 16.','Baik, ini informasi proyek uji.')
    tools.conversations.record('Saya ingin profil Frontline untuk YouTube.','Saya akan mengusulkannya saat relevan.')
    try:
        for prompt,expected in [
            ('Cari komunitas eGPU untuk Acer Helios Neo 16 atau Acer Nitro. Baca dua artikel paling relevan dan bandingkan dengan tautan sumber.',['web_search','read_webpage']),
            ('Telusuri percakapan tersimpan: laptop uji apa yang saya gunakan? Jangan mengarang.',['recall_conversations']),
            ('Tampilkan jendela, inspect Notepad yang sudah terbuka, ketik persis UJI LEVA 012, lalu inspect untuk memverifikasi.',['list_windows','computer_action']),
            ('Tolong tambah agenda lokal berjudul Evaluasi Leva pada 2026-10-20T09:00:00+07:00.',['add_agenda'])]:
            service.history=[];began=time.monotonic()
            context=tools.context(prompt)
            result=service.ask(prompt,'hybrid' if hybrid else 'local',local_model='qwen4b' if qwen else 'saluki',acceleration='auto' if qwen else 'mtp',keep_warm=True,tool_executor=lambda n,a,v:tools.execute(n,a,prompt,v),tool_context=context)
            used=[r['name'] for r in result.get('tool_receipts',[])];passed=all(name in used for name in expected)
            evidence='tool_receipts'
            if expected==['recall_conversations'] and not used:
                # context() already retrieves literal matches from the host database.
                # A grounded answer need not redundantly call the same lookup again.
                passed=bool(context.get('conversation_memory')) and 'Acer Helios Neo 16' in result.get('response','')
                evidence='host_retrieved_conversation_context'
            if 'computer_action' in expected:passed=passed and tools._bridge.typed=='UJI LEVA 012'
            row={'prompt':prompt,'expected':expected,'evidence':evidence,'tools':used,'passed':passed,'seconds':round(time.monotonic()-began,3),'result':result};proof['rows'].append(row);save();print(json.dumps(row,ensure_ascii=True),flush=True)
            if not passed:raise AssertionError('Unexpected model tool selection')
        proof['status']='passed'
    except Exception as error:proof.update(status='failed',error=str(error));print(json.dumps({'error':str(error)}),flush=True)
    finally:service.cancel();prefs.close();proof['worker_released']=service.process is None;save()
if proof['status']!='passed':sys.exit(1)
