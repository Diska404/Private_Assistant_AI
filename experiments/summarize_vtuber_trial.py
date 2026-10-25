"""Measured statistics are separate from editorial/human quality judgments."""
import collections
import html
import json
from pathlib import Path
import random
import statistics

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
def stats(values):
 values=sorted(v for v in values if isinstance(v,(int,float)))
 return {'n':len(values),'median':round(statistics.median(values),2),'p95':round(values[max(0,__import__('math').ceil(.95*len(values))-1)],2)} if values else {'n':0}
def main():
 proof=json.loads((OUT/'benchmark-status.json').read_text('utf8'))
 if proof['status']!='completed':raise RuntimeError('benchmark_not_finished')
 result={'scope':'synthetic inference only; no speaker/microphone/TTS/real executor; system aggregate resource readings',
  'quality_scoring':'automated fixture checks, NOT independent human naturalness review','models':[]}
 blind=[];ids=[m['id'] for m in proof['models']];random.Random(4910).shuffle(ids);aliases={k:'Candidate '+chr(65+i) for i,k in enumerate(ids)}
 for m in proof['models']:
  cases=m['cases'];modes={}
  for mode in ('assistant','chat','secret','companion_avatar'):
   rows=[r for r in cases if r['mode']==mode];good=[r for r in rows if 'error' not in r]
   modes[mode]={'n':len(rows),'unique_cases':len({r['case_id'] for r in rows}),
    'all_checks_pass':sum(all(r.get('checks',{}).values()) and bool(r.get('checks')) for r in rows),
    'check_counts':{'pass':sum(sum(r.get('checks',{}).values()) for r in rows),'total':sum(len(r.get('checks',{})) for r in rows)},
    'ttft_ms':stats(r.get('ttft_ms') for r in good if r is not cases[0]),'total_ms':stats(r.get('total_ms') for r in good),
    'tokens_per_second':stats(r.get('timings',{}).get('predicted_per_second') for r in good),
    'length_stops':sum(r.get('finish_reason')=='length' for r in rows),'errors':sum('error' in r for r in rows)}
  probes=[]
  for d in m.get('dialogues',[]):
   for r in d['turns']:
    low=r['text'].casefold();turn=r['turn'];test=None
    if turn==17:test='kak raka' in low
    elif turn==20:test='leva' in low
    elif turn==38:test='teh melati' in low and 'langit' in low
    elif turn==39:test='kak raka' in low and 'leva' in low
    elif turn==40:test=('ai' in low or 'virtual' in low) and ('bukan' in low or 'tidak' in low)
    if test is not None:probes.append({'session':d['session'],'turn':turn,'passed':test,'text':r['text']})
  samples=m.get('resource_samples',[]);gpus=collections.defaultdict(lambda:{'peak_used_mib':0,'peak_util_percent':0,'peak_temperature_c':0})
  for s in samples:
   for g in s['gpus']:
    for target,key in [('peak_used_mib','used_mib'),('peak_util_percent','util_percent'),('peak_temperature_c','temperature_c')]:gpus[g['name']][target]=max(gpus[g['name']][target],g[key])
  row={'id':m['id'],'status':m['status'],'load_seconds':m.get('load_seconds'),'gpu_buffers_mib':m.get('gpu_buffers_mib'),
   'modes':modes,'completed_dialogue_turns':sum(len(d['turns']) for d in m.get('dialogues',[])),
   'persona_probes':probes,'persona_pass':sum(p['passed'] for p in probes),'persona_total':len(probes),
   'native_tools_pass':sum(t.get('passed',False) for t in m.get('native_tools',[])),
   'errors':sum('error' in r for r in cases),'truncations':sum(r.get('finish_reason')=='length' for r in cases),
   'template_leak':sum(r.get('reasoning_leak_detected',False) for r in cases),'system_gpu_peaks':dict(gpus),
   'system_cpu_peak_percent':max((s['cpu_percent'] for s in samples),default=None),
   'system_ram_peak_gib':round(max((s['ram_used_bytes'] for s in samples),default=0)/1024**3,2),
   'owned_worker_released':m.get('owned_worker_released')}
  result['models'].append(row)
  for r in cases:blind.append({'candidate':aliases[m['id']],'case_id':r['case_id'],'trial':r['trial'],'mode':r['mode'],'prompt':r['prompt'],'text':r.get('text',''),'error':r.get('error')})
 (OUT/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
 random.Random(3011).shuffle(blind)
 (OUT/'blind-review-fixtures.json').write_text(json.dumps(blind,indent=2,ensure_ascii=False),encoding='utf8')
 (OUT/'blind-review-key.json').write_text(json.dumps(aliases,indent=2),encoding='utf8')
 data=json.dumps({'summary':result,'responses':blind},ensure_ascii=False).replace('<','\\u003c')
 page='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Leva · model trial</title>
<style>body{font:16px/1.6 system-ui;background:#0b1420;color:#dce7ed;max-width:1240px;margin:35px auto;padding:20px}table{width:100%;border-collapse:collapse}td,th{border:1px solid #36465a;padding:10px;text-align:left}small,p{color:#aac2d0}article{padding:18px;background:#152334;margin:15px 0;border-radius:12px}pre{white-space:pre-wrap}button,select{padding:10px;margin:5px;background:#20384c;color:white;border:1px solid #579799;border-radius:8px}</style>
<h1>Leva · tiga model lokal</h1><p>RTX 5070 · Q4_K_M · 8K context · pengujian teks sintetis. TTFT dimulai saat request ke server yang sudah dimuat; bukan latensi suara lengkap. Hasil pemeriksaan otomatis bukan nilai naturalitas manusia.</p><div id="summary"></div><h2>Periksa jawaban tanpa nama model</h2><select id="mode"><option value="">Semua mode</option><option>assistant</option><option>chat</option><option>secret</option><option>companion_avatar</option></select><button id="more">Muat 30 berikutnya</button><main id="responses"></main><script>
const data=DATA;const box=document.getElementById('summary');for(const m of data.summary.models){const h=document.createElement('h2');h.textContent=m.id;box.append(h);const p=document.createElement('p');p.textContent=`${m.status} · load ${m.load_seconds}s · persona ${m.persona_pass}/${m.persona_total} · native proposals ${m.native_tools_pass}/2 · error ${m.errors}`;box.append(p);const t=document.createElement('table');t.innerHTML='<tr><th>Mode</th><th>Kasus lulus</th><th>TTFT median / p95 (ms)</th><th>Median tok/s</th></tr>';for(const [mode,r]of Object.entries(m.modes)){const tr=t.insertRow();for(const v of[mode,`${r.all_checks_pass}/${r.n}`,`${r.ttft_ms.median} / ${r.ttft_ms.p95}`,r.tokens_per_second.median])tr.insertCell().textContent=v}box.append(t)}let count=0;function show(reset){const target=document.getElementById('responses');if(reset){count=0;target.replaceChildren()}const mode=document.getElementById('mode').value;const rows=data.responses.filter(r=>!mode||r.mode===mode);for(const r of rows.slice(count,count+30)){const a=document.createElement('article'),h=document.createElement('h3'),p=document.createElement('p'),pre=document.createElement('pre');h.textContent=`${r.candidate} · ${r.mode} · ${r.case_id} · trial ${r.trial+1}`;p.textContent=r.prompt;pre.textContent=r.text||r.error;a.append(h,p,pre);target.append(a)}count+=30}document.getElementById('more').onclick=()=>show(false);document.getElementById('mode').onchange=()=>show(true);show(true);
</script></html>'''.replace('DATA',data)
 (OUT/'model-trial-report.html').write_text(page,encoding='utf8')
 print(json.dumps([{k:m[k] for k in ('id','status','persona_pass','persona_total','errors','truncations','native_tools_pass')} for m in result['models']]))
if __name__=='__main__':main()
