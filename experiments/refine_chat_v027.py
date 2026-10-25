from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'app/leva_web/index.html';s=p.read_text('utf8')
s=s.replace('<div class="phone-audio" aria-label=', '<details id="voice-controls" open><summary>Suara &amp; mikrofon <span>Ketuk untuk tampilkan / ringkas</span></summary><div class="phone-audio" aria-label=',1)
s=s.replace('<div class="messages" id="messages"','</details><div id="speech-progress" role="status" hidden></div><div class="messages" id="messages"',1)
p.write_text(s,encoding='utf8')
p=root/'app/leva_web/app.js';s=p.read_text('utf8')
s=s.replace("if(key===lastMessages)return;lastMessages=key;","if(key===lastMessages)return;const initial=!lastMessages;lastMessages=key;")
s=s.replace('if(stick||rows.length<3)box.scrollTop=box.scrollHeight','if(initial||stick||rows.length<3)box.scrollTop=box.scrollHeight')
s=s.replace("document.body.dataset.chatLayout=value;","document.body.dataset.chatLayout=value;$('voice-controls').open=value!=='fullscreen';")
s=s.replace("messages(snapshot.messages||[]);mobileState(snapshot);", "messages(snapshot.messages||[]);const vp=state.voice_progress||{};$('speech-progress').hidden=!vp.total||vp.state==='idle';$('speech-progress').textContent='Ucapan '+Math.min((vp.completed||0)+1,vp.total)+' / '+vp.total+(vp.state==='thinking'?' · menyiapkan suara':' · antrean suara')+(vp.failed?' · sebagian belum selesai':'');mobileState(snapshot);")
p.write_text(s,encoding='utf8')
p=root/'app/leva_web/style.css'
with p.open('a',encoding='utf8') as f:f.write('''
#voice-controls{flex-shrink:0;border-bottom:1px solid #28414a}#voice-controls summary{cursor:pointer;padding:10px 18px;color:#a7d7d3;font-size:12px;background:#11232c}#voice-controls summary span{float:right;font-size:10px;color:#799da9}#speech-progress{padding:7px 16px;color:#a7d7d3;font-size:11px;background:#16312c;flex-shrink:0}
''')
