"""One-time source migration, no runtime or private data changes."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def edit(name,old,new):
 p=ROOT/name;s=p.read_text(encoding='utf8')
 if new in s:return
 assert old in s,(name,old[:70]);p.write_text(s.replace(old,new),encoding='utf8')
edit('app/web_bridge.py',"'/physics.js':'physics.js'","'/physics.js':'physics.js','/camera.js':'camera.js'")
edit('app/leva_web/graph.js',"import{hash", "import{rotatePoint,orbit}from'./camera.js';\nimport{hash")
edit('app/leva_web/graph.js',"this.zoom=1;this.pan=", "this.camera={yaw:0,pitch:0};this.zoom=1;this.pan=")
edit('app/leva_web/graph.js',"reset(){this.zoom=1;", "reset(){this.camera={yaw:0,pitch:0};this.zoom=1;")
edit('app/leva_web/graph.js',"project(n){const d=.82+(n.z||0)*.35;return{x:this.w/2+n.x*d*this.zoom+this.pan.x,y:this.h*.45+n.y*d*this.zoom+this.pan.y,r:Math.max(2,(n.r||4)*d*this.zoom),d}}", "project(n){const scale=this.mode==='neural'?Math.min(this.w*.32,this.h*.39):180,p=rotatePoint(n.x,n.y,(n.z||0)*scale,this.camera.yaw,this.camera.pitch),depth=p.z/scale,d=.82+depth*.35;return{x:this.w/2+p.x*d*this.zoom+this.pan.x,y:this.h*.45+p.y*d*this.zoom+this.pan.y,r:Math.max(2,(n.r||4)*d*this.zoom),d,depth}}")
edit('app/leva_web/graph.js',"return [...this.nodes].reverse().find", "return [...this.nodes].sort((a,b)=>this.project(b).depth-this.project(a).depth).find")
edit('app/leva_web/graph.js',"const d=.82+(n.z||0)*.35;this.pan={x:-n.x*d*this.zoom,y:-n.y*d*this.zoom}","const p=this.project(n);this.pan={x:this.pan.x+this.w/2-p.x,y:this.pan.y+this.h*.45-p.y}")
edit('app/leva_web/graph.js',"node:this.hit(p.x,p.y),moved:false", "node:this.hit(p.x,p.y),moved:false,pan:e.shiftKey||e.button===2")
edit('app/leva_web/graph.js',"if(this.down.node){const n=this.down.node,d=.82+(n.z||0)*.35;n.x+=dx/(this.zoom*d);n.y+=dy/(this.zoom*d);n.offsetX=(n.offsetX||0)+dx/(this.zoom*d);n.offsetY=(n.offsetY||0)+dy/(this.zoom*d);this.alpha=1}else{this.pan.x+=dx;this.pan.y+=dy}","if(this.down.pan){this.pan.x+=dx;this.pan.y+=dy}else{orbit(this.camera,dx,dy);c.dataset.yaw=this.camera.yaw.toFixed(3);c.dataset.pitch=this.camera.pitch.toFixed(3)}")
edit('app/leva_web/graph.js',"this.pan.x+=dirs[e.key][0];this.pan.y+=dirs[e.key][1]", "orbit(this.camera,dirs[e.key][0],dirs[e.key][1])")
edit('app/leva_web/graph.js',"this.down?.node?.id", "null")
edit('app/leva_web/graph.js',"(a.z||0)-(b.z||0)", "this.project(a).depth-this.project(b).depth")
edit('app/leva_web/graph.js',"this.inViewport=true;", "this.inViewport=true;c.addEventListener('contextmenu',e=>e.preventDefault());")
edit('app/leva_web/index.html','WEB · 0.26.1','WEB · 0.27.0')
edit('app/leva_web/index.html','<span class="brand-mark">L</span>','<span class="brand-mark profile-avatar" id="brand-avatar">L</span>')
edit('app/leva_web/index.html','<div class="segmented"><button id="neural-mode"','<button id="graph-fullscreen" aria-pressed="false" title="Perbesar jaringan">⛶ <span>Layar penuh</span></button><div class="segmented"><button id="neural-mode"')
edit('app/leva_web/index.html','Geser untuk pan, scroll untuk zoom, tarik node untuk memindahkan.','Tarik untuk rotasi 3D, Shift+tarik untuk geser, roda untuk zoom. Tombol panah memutar.')
edit('app/leva_web/index.html','</form></section>\n</main>', '</form><div id="chat-resize" role="separator" tabindex="0" aria-orientation="horizontal" aria-label="Tarik untuk mengubah tinggi percakapan" aria-valuemin="560" aria-valuemax="2400" aria-valuenow="740"><span></span></div></section>\n</main>')
edit('app/leva_web/index.html','<script type="module"','<input type="file" id="avatar-file" accept="image/png,image/jpeg,image/webp" hidden><script type="module"')
edit('app/leva_web/index.html','<h2>Percakapan</h2>','<h2><button id="profile-button" class="profile-button" title="Ganti foto profil Leva"><span id="chat-avatar" class="profile-avatar">L</span></button> Percakapan</h2>')
edit('app/leva_web/app.js',"import{RemoteVoice}","import{chatHeight}from'./camera.js';\nimport{RemoteVoice}")
edit('app/leva_web/app.js',"onStart:()=>voicePlayer.stop()", "onStart:()=>{voicePlayer.stop();command('stop_voice')}")
edit('app/leva_web/app.js',"function messages(rows){const key=JSON.stringify(rows);", "function messages(rows){const key=JSON.stringify([rows,avatarRevision]);")
edit('app/leva_web/app.js',"if(!info)head.append(text('span',user?'A':'L','avatar'));", "if(!info){const icon=text('span',user?'A':'L','avatar');if(!user)fillAvatar(icon);head.append(icon);}")
edit('app/leva_web/app.js',"function apply(snapshot){revision=", "function apply(snapshot){applyAvatar(snapshot.avatar);revision=")
edit('app/leva_web/app.js',"if(e.key==='Escape'){$('drawer').hidden=true;", "if(e.key==='Escape'){setGraphFullscreen(false);$('drawer').hidden=true;")
edit('app/leva_web/app.js',"document.body.dataset.chatLayout=value;", "if(value==='fullscreen')setGraphFullscreen(false);document.body.dataset.chatLayout=value;")
with (ROOT/'app/leva_web/app.js').open('a',encoding='utf8') as f:f.write('''
let avatarRevision='',avatarURL='';
function fillAvatar(element){element.replaceChildren();if(avatarURL){const img=document.createElement('img');img.src=avatarURL;img.alt='Leva';element.append(img)}else element.textContent='L';}
function applyAvatar(value={}){if((value.revision||'')===avatarRevision)return;avatarRevision=value.revision||'';avatarURL=value.url||'';for(const id of ['brand-avatar','chat-avatar'])fillAvatar($(id));}
$('profile-button').onclick=()=>$('avatar-file').click();
$('avatar-file').onchange=async()=>{const file=$('avatar-file').files[0];if(!file)return;try{if(file.size>5*1024*1024)throw new Error('Foto maksimal 5 MB.');applyAvatar(await api('/api/avatar',{method:'POST',headers:{'Content-Type':file.type},body:file}));lastMessages='';revision=-1;await poll();notice('Foto profil Leva diperbarui untuk laptop dan HP.')}catch(e){notice(e.message)}finally{$('avatar-file').value=''}};
function setGraphFullscreen(value){document.body.dataset.graphLayout=value?'fullscreen':'normal';$('graph-fullscreen').setAttribute('aria-pressed',String(value));$('graph-fullscreen').innerHTML=value?'✕ <span>Kembali</span>':'⛶ <span>Layar penuh</span>';if(value&&document.body.dataset.chatLayout==='fullscreen'){layout.value=previousLayout;setChatLayout(previousLayout)}requestAnimationFrame(()=>graph.resize());}
$('graph-fullscreen').onclick=()=>setGraphFullscreen(document.body.dataset.graphLayout!=='fullscreen');
const resizeHandle=$('chat-resize'),chatPanel=document.querySelector('.chat-panel');
function setChatHeight(value){value=chatHeight(value);document.body.style.setProperty('--chat-height',value+'px');resizeHandle.setAttribute('aria-valuenow',String(Math.round(value)));try{localStorage.setItem('leva.chatHeight',String(value))}catch{}}
try{const value=localStorage.getItem('leva.chatHeight');if(value)setChatHeight(value)}catch{}
let resizing=null;
resizeHandle.onpointerdown=e=>{resizing={y:e.clientY,height:chatPanel.getBoundingClientRect().height};resizeHandle.setPointerCapture(e.pointerId);document.body.classList.add('resizing-chat');};
resizeHandle.onpointermove=e=>{if(resizing)setChatHeight(resizing.height+e.clientY-resizing.y)};
resizeHandle.onpointerup=resizeHandle.onpointercancel=()=>{resizing=null;document.body.classList.remove('resizing-chat')};
resizeHandle.onkeydown=e=>{if(['ArrowUp','ArrowDown','Home','End'].includes(e.key)){e.preventDefault();setChatHeight(e.key==='Home'?560:e.key==='End'?2400:chatPanel.getBoundingClientRect().height+(e.key==='ArrowUp'?-40:40))}};
''')
with (ROOT/'app/leva_web/style.css').open('a',encoding='utf8') as f:f.write('''
/* Shared conversation identity; requested reading order: owner left, Leva right. */
.message{width:88%;max-width:780px;margin:20px 0;clear:both}.message.user{margin-right:auto}.message.assistant{margin-left:auto}
.message.assistant .message-head{justify-content:flex-end;flex-direction:row-reverse}.message.assistant .message-body{padding:13px 16px;background:#16312f77;border:1px solid #31534f;border-radius:12px 0 12px 12px;color:#d3e9e6}
.message.user .message-body{margin-left:0;border-radius:0 12px 12px 12px}.message.info{width:auto;max-width:none;margin:12px 0}
.avatar img,.profile-avatar img{width:100%;height:100%;object-fit:cover;border-radius:inherit}.avatar{overflow:hidden;flex-shrink:0}
.profile-avatar{display:inline-grid;place-items:center;width:32px;height:32px;border:1px solid #447a77;border-radius:50%;overflow:hidden;color:#aff0e3}
.brand-mark{transform:none}.profile-button{padding:0;background:transparent;border:0;vertical-align:middle;min-height:0}.chat-panel h2{display:flex;align-items:center;gap:5px}
#chat-resize{height:17px;display:grid;place-items:center;cursor:ns-resize;touch-action:none;border-top:1px solid #2a434d;background:#101f2b;flex-shrink:0}
#chat-resize span{width:64px;height:3px;border-radius:4px;background:#477e82}#chat-resize:hover span,#chat-resize:focus-visible span{background:#a1ede2}.resizing-chat{cursor:ns-resize;user-select:none}
body:not([data-chat-layout=fullscreen]):not([data-chat-layout=expanded]) .chat-panel{height:var(--chat-height,840px);min-height:560px;max-height:none}
body[data-chat-layout=expanded] #chat-resize,body[data-chat-layout=fullscreen] #chat-resize{display:none}
#graph-fullscreen{font-size:11px;padding:7px 9px;white-space:nowrap}.neural-panel .panel-header{flex-wrap:wrap}.neural-panel .panel-header>div:first-child{margin-right:auto}
body[data-graph-layout=fullscreen]{overflow:hidden}
body[data-graph-layout=fullscreen] #neural-panel{display:flex!important;flex-direction:column;position:fixed;inset:10px;z-index:40;background:#09131f;height:calc(100dvh - 20px);box-shadow:0 0 0 100vmax #050a12}
body[data-graph-layout=fullscreen] .graph-stage{height:auto;min-height:0;flex:1}
body[data-graph-layout=fullscreen] .heard,body[data-graph-layout=fullscreen] .hardware-heading,body[data-graph-layout=fullscreen] .hardware{display:none}
body[data-graph-layout=fullscreen] .panel-header{padding:15px 20px;flex-shrink:0}
body[data-graph-layout=fullscreen] .graph-caption{flex-shrink:0;padding-bottom:16px}
body[data-graph-layout=fullscreen] .meters{top:18%;right:25px}.graph-controls button{width:34px;height:34px}
@media(max-width:800px){#chat-resize{display:none}.message{width:94%}.message-body{line-height:1.8}#graph-fullscreen span{display:none}#graph-fullscreen{min-width:38px}.neural-panel .panel-header{gap:7px}.neural-panel .panel-header>div:first-child{flex:1}.neural-panel h2{font-size:14px}body[data-graph-layout=fullscreen] #neural-panel{inset:0;height:100dvh;border-radius:0}body[data-graph-layout=fullscreen] .panel-header{padding:15px 12px}.message-head .avatar{width:27px;height:27px}}
''')
print('Visual source migration complete')
