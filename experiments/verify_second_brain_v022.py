"""VIDEO_001: local fixture benchmark and actual Saluki -> host read -> cited answer."""
import hashlib,json,queue,sys,time,tracemalloc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from second_brain import VaultIndex,SecondBrain
from preferences import Preferences
from saluki_backend import SalukiEngine
from agent_runtime import _run_agent

OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/second-brain-v022');OUT.mkdir(parents=True,exist_ok=True)
fixture=OUT/('fixture-'+str(time.time_ns()));fixture.mkdir()
documents={
    'Aurora':('Kode warna prototipe Aurora adalah Safir-872. Keputusan desain ini adalah data fixture untuk pengujian.','Apa kode warna prototipe Aurora?'),
    'Diskrit':('Belajar matematika diskrit membahas kombinatorika dan teori graf hari Kamis pukul 19:00.','Kapan jadwal belajar matematika diskrit?'),
    'Chrome':('Profil Diska digunakan pada contoh fixture untuk membuka ChatGPT di Chrome.','Profil Chrome untuk ChatGPT?'),
    'ComfyUI':('Workflow gambar ComfyUI menggunakan checkpoint fixture-example.safetensors dan VAE bawaan.','Apa checkpoint workflow ComfyUI?'),
    'Headset':('Perangkat audio fixture adalah Headset DAXA dengan input dan output terpisah.','Perangkat audio headset apa?'),
    'eGPU':('Catatan eksperimen eGPU membahas Thunderbolt dan enclosure eksternal.','Apa koneksi enclosure eGPU?'),
    'Suara':('Output suara Jepang memakai identitas Leva; percakapan teks tetap Indonesia.','Bagaimana bahasa output suara Leva?'),
    'Pengingat':('Pengingat belajar ditunda sampai jam yang dijadwalkan, tidak membuka aplikasi sekarang.','Bagaimana perilaku pengingat belajar tertunda?'),
    'GPU':('Kartu RTX 4050 dan RTX 5070 dapat dipilih sesuai penempatan model dan kebutuhan VRAM.','Pilihan kartu RTX 4050 dan RTX 5070?'),
    'Vault':('Vault Markdown adalah catatan pengetahuan eksternal, bukan bobot model yang dilatih ulang.','Apakah vault Markdown melatih ulang bobot model?')}
for title,(body,_) in documents.items():
    (fixture/(title+'.md')).write_text('# '+title+'\n\n'+body+'\n\n[[Aurora]]\n',encoding='utf8')
index=VaultIndex(fixture,OUT/'index');tracemalloc.start();cpu=time.process_time();cold=index.refresh()
measurements=[]
for title,(_,query) in documents.items():
    began=time.perf_counter();sources=index.search(query,3)
    measurements.append({'query':query,'expected':title+'.md','retrieved':[r['path'] for r in sources],
        'hit_at_3':title+'.md' in [r['path'] for r in sources],'latency_ms':round((time.perf_counter()-began)*1000,2),
        'excerpt_characters':sum(len(r['excerpt']) for r in sources)})
_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
benchmark={'video_id':'VIDEO_001','fixture_only':True,'queries':measurements,'hits_at_3':sum(r['hit_at_3'] for r in measurements),
    'cold_index':cold,'warm_index':index.refresh(),'cpu_ms':round((time.process_time()-cpu)*1000,2),'python_allocation_peak_bytes':peak,
    'embedding_model_loaded':False,'gpu_used_by_retrieval':False}
(OUT/'retrieval-benchmark.json').write_text(json.dumps(benchmark,ensure_ascii=False,indent=2),encoding='utf8')
if benchmark['hits_at_3']<9:raise RuntimeError('fixture_retrieval_acceptance_failed')

prefs=Preferences(OUT/'fixture-preferences.sqlite3');prefs.set('obsidian_vault',str(fixture));service=SecondBrain(prefs,OUT/'service-index')
model=SalukiEngine(OUT/'model-runtime',mode='dual',acceleration='plain',max_output_tokens=2048)
commands=queue.Queue();receipts=[];started=time.perf_counter()
goal='Baca catatan Obsidian Aurora.md. Apa kode warna prototipe Aurora menurut catatan itu? Jawab singkat dalam bahasa Indonesia dan sebutkan sumber catatan. Gunakan obsidian_action; jangan jalankan terminal atau mengubah berkas.'
def emit(event):
    if event.get('kind')!='tool_call':return
    result=service.run(event['args']) if event['name']=='obsidian_action' else {'status':'failed','reply':'Uji ini hanya menyediakan pembaca vault; tidak ada tindakan lain dijalankan.'}
    receipts.append({'tool':event['name'],'action':event['args'].get('action'),'status':result['status'],'source_paths':[s['path'] for s in result.get('sources',[])]})
    print(json.dumps(receipts[-1]),flush=True)
    commands.put({'kind':'tool_result','id':1,'call_id':event['call_id'],'result':result})
try:
    result=_run_agent({'id':1,'mode':'local','time_budget_seconds':180,'messages':[{'role':'user','content':goal}]},model,commands,emit)
    proof={'video_id':'VIDEO_001','real_model':'Saluki 27B IQ2 mix','gpu':'dual','fixture_only':True,'receipts':receipts,
        'seconds':round(time.perf_counter()-started,2),'result':result,
        'ok':'Safir-872' in result.get('response','') and 'Aurora.md' in result.get('response','') and any(r['status']=='done' and r['source_paths'] for r in receipts) and not result.get('incomplete')}
except Exception as error:proof={'ok':False,'code':str(error),'receipts':receipts,'seconds':round(time.perf_counter()-started,2)}
finally:model.close();prefs.close()
(OUT/'real-agent.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in proof.items() if k!='result'}),flush=True)
if not proof['ok']:raise SystemExit(1)
