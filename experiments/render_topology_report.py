"""Self-contained, offline benchmark dashboard. Raw evidence is linked by filename."""
import json
import re
from pathlib import Path

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\topology-benchmark-20261023')
data=[]
for label in ('mini-main','mini-batch-equal-v2','saluki-final','saluki-control'):
    path=OUT/label/'proof.json'
    if not path.is_file():continue
    proof=json.loads(path.read_text('utf8'))
    if proof.get('invalidated'):continue
    for row in proof['profiles']:
        # Batch runs made before equal concurrency was introduced remain raw
        # evidence, but are excluded from the primary comparison dashboard.
        if row['workload']=='batch' and proof.get('batch_concurrency')!=2:continue
        row={**row,'label':label,'model_name':Path(proof['model']).name,'model_sha256':proof['model_sha256'],
             'batch_concurrency':proof.get('batch_concurrency',1),'raw':label+'/proof.json'}
        row['offload_evidence']=[]
        for log in (OUT/label/(row['name']+'-'+row['workload'])).glob('*.log'):
            match=re.search(r'offloaded (\d+)/(\d+) layers to GPU',log.read_text('utf8',errors='replace'))
            if match:row['offload_evidence'].append({'worker':log.stem,'gpu_layers':int(match[1]),'total_layers':int(match[2]),'full_gpu_offload':match[1]==match[2]})
        data.append(row)
payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
html='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LEVA · Lab pembagian model</title>
<style>:root{color-scheme:dark;font-family:system-ui;background:#071018;color:#e2eef4}*{box-sizing:border-box}body{max-width:1400px;margin:auto;padding:24px}h1{font-weight:550;letter-spacing:.02em}small,.muted{color:#9ab0bd}header{border-bottom:1px solid #25404e;padding-bottom:20px}strong{color:#72dde4}.note{border-left:3px solid #e2b66f;background:#17212a;padding:14px;line-height:1.6;margin:18px 0}select,button{font:inherit;background:#112836;color:#ecf6fb;border:1px solid #365665;border-radius:8px;padding:9px}table{width:100%;border-collapse:collapse;margin-top:20px}td,th{text-align:left;padding:13px;border-bottom:1px solid #223847;white-space:nowrap}th{color:#86becd;font-size:13px}tbody tr:hover{background:#102331}.scroll{overflow:auto}section{background:#0c1a24;padding:18px;border:1px solid #223b4a;border-radius:14px;margin-top:20px}.bar{background:#19323f;height:24px;margin:10px 0;border-radius:4px;overflow:hidden}.bar span{display:block;height:100%;background:#48a9b4;min-width:2px}pre{white-space:pre-wrap;word-break:break-word;background:#08131b;padding:12px;border-radius:8px}a{color:#7fe0e5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.pill{font-size:12px;border:1px solid #416575;border-radius:20px;padding:4px 8px}.bad{color:#ffc38b}@media(max-width:700px){body{padding:14px}.grid{grid-template-columns:1fr}td,th{padding:10px}h1{font-size:25px}}</style>
<header><small>LEVA / VERIFICATION LAB / 23 OKTOBER 2026</small><h1>Satu model dibagi, atau pekerjaan dibagi?</h1><p>Inferensi nyata pada dua GPU laptop. <strong>Belum ada hasil Colab/Kaggle atau pengukuran WAN.</strong></p><span class="pill">RPC loopback TCP</span> <span class="pill">Tanpa tindakan desktop</span> <span class="pill">Data tersimpan lokal</span></header>
<div class="note">Batch memakai dua permintaan aktif pada semua topologi: dua slot pada satu model, atau satu slot per replika. Lima pekerjaan identik per putaran; jumlah putaran tercatat pada bukti. Startup dipisah dari pengukuran warm. Aplikasi lain tetap berjalan; urutan uji dan perubahan beban/clock dapat memengaruhi hasil. Skor JSON hanya empat kasus sempit, bukan ukuran kecerdasan agent.</div>
<label>Model <select id="model"></select></label> <label>Pengukuran <select id="mode"><option value="serial">Satu permintaan · serial</option><option value="batch">Lima pekerjaan · dua bersamaan</option></select></label>
<div class="scroll"><table><thead><tr><th>Topologi</th><th>Startup s</th><th>Respons pertama p50 ms</th><th>Total per permintaan p50 ms</th><th>Decode token/s p50</th><th>Lima pekerjaan p50 ms</th><th>Lengkap</th><th>JSON benar</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="grid"><section><h2 id="chart-title">Waktu proses</h2><div id="chart"></div></section><section><h2>Resource teramati</h2><p class="muted">VRAM/CPU/RAM mencakup seluruh sistem. RSS adalah jumlah working set proses benchmark, tidak menghapus halaman yang dibagi.</p><div id="resource"></div></section></div>
<section><h2>Alokasi dan jawaban asli</h2><p>Periksa kedua alokasi RPC dan keluaran, termasuk kesalahan format atau arti. Replika Saluki pada RTX 4050 dapat memakai CPU offload; lihat bukti alokasi.</p><select id="detail"></select><div id="evidence"></div></section>
<section><h2>Cloud belum terhubung</h2><p>Colab gratis membatasi distributed computing worker. Notebook pemeriksaan environment disiapkan terpisah; tidak membuka port, memasang paket atau mengunggah model. RPC tidak memiliki proteksi yang cukup untuk diekspos langsung ke internet. Pengujian WAN memerlukan runtime yang sesuai dan transport privat.</p><p><a href="https://research.google.com/colaboratory/faq.html">Colab FAQ</a> · <a href="https://www.kaggle.com/docs/notebooks">Kaggle Notebooks</a> · <a href="https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md">llama.cpp RPC</a></p></section>
<script>
const data=DATA;
const names={rpc_dual:'Satu model · dua endpoint RPC',gpu5070:'Satu model · RTX 5070',native_dual:'Satu model · dua GPU native',replicas:'Dua replika · bagi pekerjaan'};
const $=id=>document.getElementById(id),fmt=x=>Number.isFinite(x)?x.toLocaleString('id-ID',{maximumFractionDigits:2}):'—';
const text=(tag,value)=>{const el=document.createElement(tag);el.textContent=value;return el};
for(const name of [...new Set(data.map(r=>r.model_name))]){$('model').add(new Option(name,name))}
function selected(){return data.filter(r=>r.model_name===$('model').value&&r.workload===$('mode').value)}
function refresh(){const list=selected();$('rows').replaceChildren();$('chart').replaceChildren();$('resource').replaceChildren();$('detail').replaceChildren();
const batch=$('mode').value==='batch',metric=r=>batch?r.summary?.batch_makespan_p50_ms:r.summary?.total_p50_ms,max=Math.max(1,...list.map(metric).filter(Number.isFinite));
$('chart-title').textContent=batch?'Total lima pekerjaan · lebih pendek lebih cepat':'Total satu permintaan · lebih pendek lebih cepat';
list.forEach((r,i)=>{const s=r.summary||{},tr=document.createElement('tr');[(names[r.name]||r.name)+(r.status==='completed'?'':' · '+r.status),fmt(r.startup_s),fmt(s.ttft_p50_ms),fmt(s.total_p50_ms),fmt(s.decode_tps_p50),fmt(s.batch_makespan_p50_ms),`${s.complete||0}/${s.n||0}`,`${s.exact_checks_passed||0}/${s.exact_checks_total||0}`].forEach(v=>tr.append(text('td',v)));$('rows').append(tr);
const title=text('div',`${names[r.name]} · ${fmt(metric(r))} ms`),bar=document.createElement('div');bar.className='bar';const fill=document.createElement('span');fill.style.width=100*(metric(r)||0)/max+'%';bar.append(fill);$('chart').append(title,bar);
const samples=r.telemetry.filter(x=>x.gpus),gpuPeaks={};for(const sample of samples)for(const gpu of sample.gpus)gpuPeaks[gpu.name]=Math.max(gpuPeaks[gpu.name]||0,gpu.used_mib);
const block=document.createElement('p');block.append(text('strong',names[r.name]),text('div',Object.entries(gpuPeaks).map(([n,v])=>`${n}: ${fmt(v)} MiB`).join(' · ')),text('small',`CPU peak ${fmt(Math.max(...samples.map(x=>x.system_cpu_percent)))}% · RAM sistem peak ${fmt(Math.max(...samples.map(x=>x.system_ram_used_gib)))} GiB · RSS benchmark peak ${fmt(Math.max(...samples.map(x=>x.owned_rss_mib)))} MiB`));$('resource').append(block);$('detail').add(new Option(names[r.name],String(i)));});detail();}
function detail(){const r=selected()[Number($('detail').value)||0];$('evidence').replaceChildren();if(!r)return;const a=text('a','Buka bukti JSON');a.href=r.raw;$('evidence').append(a,text('p','SHA-256 model: '+r.model_sha256),text('pre',JSON.stringify({placement:r.placement,offload:r.offload_evidence,error:r.error},null,2)));for(const q of r.requests||[]){const d=document.createElement('details');d.append(text('summary',`Putaran ${q.round+1} · ${q.case} · ${q.status} · JSON ${q.exact_pass===null?'tidak dinilai':q.exact_pass?'benar':'salah'}`),text('pre',q.answer||q.error));$('evidence').append(d)}}
$('model').onchange=refresh;$('mode').onchange=refresh;$('detail').onchange=detail;refresh();
</script></html>'''.replace('DATA',payload)
path=OUT/'index.html';path.write_text(html,encoding='utf8')
(OUT/'dashboard-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'dashboard':str(path),'profiles':len(data)}))
