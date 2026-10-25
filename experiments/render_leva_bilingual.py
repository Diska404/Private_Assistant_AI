"""Portable, offline A/B listening artifact with local ratings and JSON export."""
import base64
import html
import json
from pathlib import Path

OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-bilingual-v3')
DATA=OUT.parent.parent
proof=json.loads((OUT/'proof.json').read_text('utf-8'))
asr=json.loads((OUT/'asr-check.json').read_text('utf-8')) if (OUT/'asr-check.json').exists() else {'rows':[]}
asr_by_id={row['id']:row for row in asr['rows'] if row['category']=='converted'}
e=html.escape

def audio(path):
    data=base64.b64encode(Path(path).read_bytes()).decode()
    return '<audio controls preload="metadata" src="data:audio/wav;base64,'+data+'"></audio>'

sections=[]
for language,label in (('id','Bahasa Indonesia'),('ja','Bahasa Jepang')):
    sections.append(f'<section class="language-section" data-lang="{language}"><h2>{label}</h2>')
    for base in (b for b in proof['base'] if b['language']==language):
        voice=base.get('base_voice','piper')
        sections.append(f'<article data-voice="{voice}"><h3>{e(base["text"])}</h3>')
        if base.get('translation_id'): sections.append('<p class="muted">Arti: '+e(base['translation_id'])+'</p>')
        sections.append('<details><summary>Suara dasar sebelum konversi · '+e(base['base_engine'])+' '+e(voice)+'</summary>'+audio(base['path'])+'</details>')
        sections.append('<div class="variants">')
        for row in (r for r in proof['converted'] if r['base_id']==base['id']):
            ident=e(row['id'])
            sections.append('<div class="candidate"><p class="variant-name">Kandidat '+e(row['reference_id'])+'</p>'+audio(row['path']))
            sections.append('<p class="muted reveal">Seed-VC · referensi '+e(row['reference_id'])+' · '+str(row['conversion_seconds'])+' s konversi / '+str(row['duration_seconds'])+' s audio</p>')
            sections.append('<label>Kemiripan Leva <select data-score="'+ident+'"><option value="">Belum dinilai</option>'+''.join(f'<option value="{i}">{i} / 5</option>' for i in range(1,6))+'</select></label>')
            if row['id'] in asr_by_id:
                a=asr_by_id[row['id']]
                sections.append('<details class="reveal"><summary>Transkrip pemeriksaan lokal</summary><p>'+e(a['transcript'])+'</p><p class="muted">'+a['metric'].upper()+' mentah '+str(a['error_rate'])+'; bukan skor kemiripan.</p></details>')
            sections.append('</div>')
        sections.append('</div>')
        if language=='id':
            old_id=base['id'][3:]
            old=DATA/'verification/leva-nexus-candidate-v2'/f'{old_id}_leva_nexus_candidate.wav'
            if old.exists(): sections.append('<details><summary>Pembanding hasil lama · OpenVoice v2</summary>'+audio(old)+'</details>')
        sections.append('</article>')
    sections.append('</section>')

references=''.join('<article><h3>Referensi '+e(p['id'])+'</h3><p lang="ja">'+e(p['text'])+'</p>'+audio(p['path'])+'</article>' for p in proof['prompts'])
body='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leva · uji suara Indonesia dan Jepang v3</title>
<style>
:root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;background:#0b111b;color:#e9eef6;line-height:1.6}
body{max-width:1180px;margin:auto;padding:30px 24px 80px}h1{font-size:clamp(28px,4vw,46px);line-height:1.2;margin:10px 0}h2{margin-top:35px;color:#bce8e2}h3{font-size:19px;font-weight:550}p{max-width:90ch}.eyebrow{letter-spacing:.15em;color:#73daca;font-size:12px;text-transform:uppercase}.muted{color:#9cacbf;font-size:14px}.notice{border-left:3px solid #eebc72;background:#251f18;padding:16px 20px;border-radius:6px}.controls{display:flex;flex-wrap:wrap;gap:18px;align-items:center;padding:18px;background:#131e2d;border:1px solid #29364a;border-radius:12px;margin:24px 0;position:sticky;top:0;z-index:2}select,button,textarea{background:#0b1522;color:#eef5ff;border:1px solid #43566f;border-radius:7px;padding:9px;font:inherit}button{cursor:pointer;color:#8de0d0}article{background:#121c2a;border:1px solid #26364c;border-radius:14px;padding:20px 24px;margin:16px 0}.variants,.references{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:18px}.candidate{padding:15px;background:#0b1421;border:1px solid #2b3b51;border-radius:9px}.variant-name{margin:0 0 10px;color:#84dfcf}audio{width:100%;display:block;margin:12px 0}summary{cursor:pointer;color:#b8cadd}details{margin:16px 0}label{font-size:14px}textarea{display:block;box-sizing:border-box;width:100%;min-height:95px;margin:12px 0}footer{color:#9cacbf;margin-top:30px;font-size:13px}.blind .reveal{display:none}[hidden]{display:none!important}a{color:#82d9cb}
</style>
<div class="eyebrow">Leva · Laboratorium suara · 19 Oktober 2026</div>
<h1>Satu identitas, dua bahasa.</h1>
<p>Bandingkan kandidat suara Leva dalam bahasa Indonesia dan Jepang. Dengarkan referensi dahulu, lalu A dan B. Dua suara dasar Jepang membantu memeriksa seberapa kuat karakter sumber masih memengaruhi hasil.</p>
<p class="notice">Ini sintesis ucapan baru dengan model umum Seed-VC dan referensi mod Nexus yang Anda sediakan. Belum model Leva hasil fine-tuning, belum divalidasi lebih mirip, dan belum menjadi suara aktif Leva.exe. Kemiripan perlu penilaian Anda. Halaman sepenuhnya lokal, tanpa unggahan dan tanpa autoplay.</p>
<h2>Dengarkan target referensi</h2><div class="references">'''+references+'''</div>
<div class="controls"><label>Bahasa <select id="language"><option value="all">Keduanya</option><option value="id">Indonesia</option><option value="ja">Jepang</option></select></label><label>Dasar Jepang <select id="voice"><option value="jf_alpha">Alpha</option><option value="jf_nezumi">Nezumi</option><option value="all">Tampilkan semua</option></select></label><label><input type="checkbox" id="blind"> Sembunyikan detail teknis</label><button id="stop">Hentikan audio</button></div>
'''+''.join(sections)+'''
<article><h2>Catatan pendengaran Anda</h2><p>Skor: 1 sangat berbeda, 5 sangat mirip. Nilai identitas dan warna suara; catat pelafalan, intonasi atau artefak secara terpisah. Nilai disimpan hanya pada browser ini bila penyimpanan lokal tersedia.</p><textarea id="notes" placeholder="Contoh: Jepang Alpha A lebih dekat, tetapi ujung kalimat masih terlalu tinggi..."></textarea><button id="export">Simpan penilaian JSON</button><span id="status" class="muted" role="status"></span></article>
<footer>RTX 4050 · 30 langkah diffusion · CFG 0,7 · pitch shift 0 · dua referensi. Waktu konversi tidak mencakup pembuatan teks, load dingin, TTS dasar, STT atau playback. Tidak ada klaim streaming/interupsi atau benchmark RTX 5070. Referensi adalah hasil mod, bukan verifikasi independen suara asli game.</footer>
<script>
const key='leva-bilingual-v3-ratings';let saved={scores:{},notes:''};try{saved=JSON.parse(localStorage.getItem(key))||saved}catch{};
const notes=document.querySelector('#notes');notes.value=saved.notes||'';
function persist(){try{localStorage.setItem(key,JSON.stringify(saved));document.querySelector('#status').textContent=' Tersimpan lokal.'}catch{document.querySelector('#status').textContent=' Gunakan ekspor JSON untuk menyimpan.'}}
document.querySelectorAll('[data-score]').forEach(s=>{s.value=saved.scores?.[s.dataset.score]||'';s.onchange=()=>{saved.scores[s.dataset.score]=s.value;persist()}});notes.oninput=()=>{saved.notes=notes.value;persist()};
function filter(){const l=document.querySelector('#language').value,v=document.querySelector('#voice').value;document.querySelectorAll('.language-section').forEach(s=>s.hidden=l!=='all'&&s.dataset.lang!==l);document.querySelectorAll('[data-voice]').forEach(a=>a.hidden=a.dataset.voice!=='piper'&&v!=='all'&&a.dataset.voice!==v);document.querySelectorAll('audio').forEach(a=>a.pause())}
document.querySelector('#language').onchange=filter;document.querySelector('#voice').onchange=filter;document.querySelector('#blind').onchange=e=>document.body.classList.toggle('blind',e.target.checked);document.querySelector('#stop').onclick=()=>document.querySelectorAll('audio').forEach(a=>a.pause());
document.querySelectorAll('audio').forEach(a=>a.onplay=()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()}));
document.querySelector('#export').onclick=()=>{const blob=new Blob([JSON.stringify({experiment:'leva-bilingual-v3',saved_at:new Date().toISOString(),...saved},null,2)],{type:'application/json'});const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='leva-bilingual-v3-penilaian.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),500)};filter();
</script></html>'''
(OUT/'comparison.html').write_text(body,encoding='utf-8')
print(json.dumps({'html':str(OUT/'comparison.html'),'converted':len(proof['converted']),'embedded_audio':body.count('<audio ')}))
