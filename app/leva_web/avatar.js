import{FACE_PROFILES}from'./avatar_performance.js';
import{VRMAvatarProvider}from'./vrm_avatar.js';
export{VRMAvatarProvider}from'./vrm_avatar.js';
// Asset-independent, original procedural placeholder. No microphone, model or fetch.
export class AvatarProvider{
 load(){throw new Error('avatar_provider_not_configured')}
 setExpression(){}setViseme(){}setGaze(){}playMotion(){}setQuality(){}dispose(){}
}
export class PlaceholderAvatar extends AvatarProvider{
 constructor(canvas,{level=()=>0,onMetrics=()=>{}}={}){
  super();this.canvas=canvas;this.ctx=canvas.getContext('2d');this.level=level;this.onMetrics=onMetrics;
  this.state='idle';this.expression='neutral';this.mouth=0;this.quality='balanced';this.scale=1;this.frames=[];this.raf=0;this.last=0;this.dead=false;
  this.visible=true;this.visibility=()=>{this.last=0;if(!document.hidden)this.schedule()};document.addEventListener('visibilitychange',this.visibility);
  this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(canvas);
  this.intersection=new IntersectionObserver(rows=>{this.visible=rows[0].isIntersecting;if(this.visible)this.schedule()});this.intersection.observe(canvas);
  this.resize();this.schedule();
 }
 resize(){const r=this.canvas.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);this.w=r.width;this.h=r.height;this.canvas.width=Math.round(r.width*d);this.canvas.height=Math.round(r.height*d);this.ctx.setTransform(d,0,0,d,0,0);this.schedule()}
 load(){return{provider:'placeholder',asset:'leva_procedural_placeholder_v1',final_character:false}}
 setExpression(value){if(['neutral','happy','curious','thinking','shy','surprised','sad'].includes(value))this.expression=value}
 setViseme(value){this.mouth=Math.max(0,Math.min(1,value||0))}
 setGaze(value){this.gaze=value}
 setQuality(value){if(['premium','performance','balanced','gaming','eco'].includes(value))this.quality=value}
 update(value={}){if(this.generation!==value.generation_id){this.generation=value.generation_id;this.mouth=0}this.state=value.state||'idle';this.setExpression(value.expression||'neutral');this.schedule()}
 schedule(){if(!this.dead&&!this.raf&&!document.hidden&&this.visible)this.raf=requestAnimationFrame(t=>this.frame(t))}
 frame(t){this.raf=0;if(this.dead||document.hidden||!this.visible)return;const interval=['performance','premium'].includes(this.quality)?1000/60:this.quality==='eco'?1000/15:1000/30;
  if(this.last&&t-this.last<interval-.5){this.schedule();return}const delta=this.last?t-this.last:interval;this.last=t;
  const start=performance.now(),level=this.state==='interrupted'?0:this.level();this.setViseme(level);this.draw(t);
  this.frames.push({cost:performance.now()-start,delta});if(this.frames.length>120)this.frames.shift();
  if(!this.reported||t-this.reported>1000){this.reported=t;const sorted=this.frames.map(v=>v.delta).sort((a,b)=>a-b);this.onMetrics({samples:sorted.length,frame_p95_ms:sorted[Math.floor((sorted.length-1)*.95)],draw_ms:this.frames.reduce((s,v)=>s+v.cost,0)/this.frames.length})}
  this.schedule();
 }
 draw(t){const c=this.ctx,w=this.w||400,h=this.h||420;c.clearRect(0,0,w,h);
  const glow=c.createRadialGradient(w/2,h*.43,10,w/2,h*.43,w*.65);glow.addColorStop(0,'#55406455');glow.addColorStop(1,'#080f1800');c.fillStyle=glow;c.fillRect(0,0,w,h);
  const small=matchMedia('(prefers-reduced-motion: reduce)').matches,breath=small?0:Math.sin(t*.0018)*2;
  c.save();c.translate(w/2,h*.52+breath);c.scale(this.scale,this.scale);
  c.fillStyle='#090e18';c.beginPath();c.ellipse(0,128,95,16,0,0,Math.PI*2);c.fill();
  c.fillStyle='#233747';c.strokeStyle='#75c9cf';c.lineWidth=1.5;c.beginPath();c.roundRect(-60,22,120,105,38);c.fill();c.stroke();
  c.fillStyle='#3c5867';for(const side of [-1,1]){c.save();c.translate(side*68,55);c.rotate(side*(this.expression==='happy'?-.35:-.08));c.beginPath();c.roundRect(-13,-22,26,86,13);c.fill();c.restore()}
  c.fillStyle='#263141';c.beginPath();c.roundRect(-86,-122,172,163,60);c.fill();
  c.fillStyle='#eed7c9';c.strokeStyle='#dcbab0';c.beginPath();c.roundRect(-68,-104,136,133,48);c.fill();c.stroke();
  c.fillStyle='#465368';c.beginPath();c.moveTo(-76,-45);c.quadraticCurveTo(-88,-136,0,-130);c.quadraticCurveTo(90,-133,76,-38);c.lineTo(57,-95);c.lineTo(28,-59);c.lineTo(12,-101);c.lineTo(-21,-66);c.lineTo(-43,-101);c.closePath();c.fill();
  const blink=!small&&(t%4700)>4520,eye=this.expression==='happy'?6:this.expression==='surprised'?13:10;
  c.fillStyle='#263849';for(const x of [-27,27]){c.beginPath();c.ellipse(x,-42,8,blink?1:eye,0,0,Math.PI*2);c.fill();if(!blink){c.fillStyle='#9ce2dd';c.beginPath();c.ellipse(x+1,-44,3,5,0,0,Math.PI*2);c.fill();c.fillStyle='#263849'}}
  c.strokeStyle='#9e6973';c.lineWidth=2;c.fillStyle='#694653';c.beginPath();
  if(this.mouth>.04){c.ellipse(0,-6,8,2+this.mouth*13,0,0,Math.PI*2);c.fill()}else{c.moveTo(-9,-5);c.quadraticCurveTo(0,this.expression==='sad'?-12:4,9,-5);c.stroke()}
  if(this.expression==='shy'||this.expression==='happy'){c.fillStyle='#df8e9b55';for(const x of [-43,43]){c.beginPath();c.ellipse(x,-18,12,5,0,0,Math.PI*2);c.fill()}}
  c.fillStyle='#86d8d6';c.beginPath();c.arc(0,58,9,0,Math.PI*2);c.fill();c.restore();
 }
 dispose(){this.dead=true;cancelAnimationFrame(this.raf);this.raf=0;this.observer.disconnect();this.intersection.disconnect();document.removeEventListener('visibilitychange',this.visibility);this.frames=[];this.mouth=0}
}
// Deliberately fail closed: the blueprint contains no approved VRM/Live2D asset.
export class Live2DAvatarProvider extends AvatarProvider{load(){throw new Error('live2d_requires_licensed_artwork_rig_and_runtime')}}

export class CompanionStage{
 constructor({command,voice,api}){this.command=command;this.voice=voice;this.api=api;this.$=id=>document.getElementById(id);
  const focus=document.createElement('button');focus.type='button';focus.id='avatar-focus';focus.textContent='Perbesar avatar';focus.setAttribute('aria-pressed','false');this.$('companion-stage').querySelector('.panel-header').append(focus);focus.onclick=()=>{const active=this.$('companion-stage').classList.toggle('avatar-focused');focus.textContent=active?'Kembali ke percakapan':'Perbesar avatar';focus.setAttribute('aria-pressed',String(active))};
  this.$('companion-form').onsubmit=e=>{e.preventDefault();command('companion_settings',{enabled:this.$('companion-enabled').checked,label:this.$('companion-label').value,experimental_models:this.$('trial-enabled').checked,asset:this.$('avatar-asset').value,renderer_gpu:this.$('avatar-gpu').value,realtime_speech:this.$('realtime-speech').checked,native_stream:this.$('native-voice-stream').checked})};
  this.$('avatar-upload').onchange=async()=>{const file=this.$('avatar-upload').files[0];if(!file)return;try{if(file.size>64*1024*1024)throw new Error('Model maksimal 64 MiB.');const row=await api('/api/avatar-model',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const option=new Option(row.label,'custom');this.$('avatar-asset').append(option);this.$('avatar-asset').value='custom';this.$('avatar-upload-status').textContent='Model tersimpan. Tekan Simpan opsi untuk memakainya.'}catch(e){this.$('avatar-upload-status').textContent=e.message}finally{this.$('avatar-upload').value=''}};
  this.$('avatar-stop').onclick=()=>{this.cancelRecording();this.demoUntil=0;voice.stop();command('companion_stop')};
  this.$('avatar-demo').textContent='Demo ekspresi';this.$('avatar-demo').onclick=()=>{const provider=this.provider;this.demoUntil=performance.now()+3000;provider?.setExpression?.('happy');this.$('avatar-source').textContent='DEMO EKSPRESI · mulut tetap mengikuti audio aktual';setTimeout(()=>{if(this.provider===provider)provider?.setExpression?.(this.lastAvatar?.expression||'neutral')},3000)};
  this.$('avatar-quality').onchange=()=>this.provider?.setQuality(this.$('avatar-quality').value);
  this.$('avatar-lighting').onchange=()=>this.provider?.setLighting?.(this.$('avatar-lighting').value);
  this.$('avatar-framing').onchange=()=>this.provider?.setFraming?.(this.$('avatar-framing').value);
  const view=document.createElement('select');view.id='avatar-view';view.setAttribute('aria-label','Sudut avatar');for(const [key,label]of[['front','Depan'],['quarter','Sudut 3/4'],['side','Samping'],['back','Belakang']])view.append(new Option(label,key));this.$('avatar-framing').after(view);view.onchange=()=>this.provider?.setView?.(view.value);
  this.$('avatar-material').onchange=()=>{try{this.provider?.setMaterial?.(this.$('avatar-material').value)}catch(e){this.$('avatar-test-status').textContent=e.message;this.$('avatar-material').value='source'}};
  this.$('avatar-debug').onchange=()=>this.provider?.setDebug?.(this.$('avatar-debug').checked);
  const tools=this.$('avatar-motion').parentElement;
  const check=(id,label,checked,apply)=>{const box=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.id=id;input.checked=checked;input.onchange=()=>apply(input.checked);box.append(input,document.createTextNode(label));tools.append(box);return input};
  check('avatar-r1','Animasi R1',true,v=>this.provider?.setEnhanced?.(v));
  check('avatar-physics','Fisika sumber',true,v=>this.provider?.setPhysicsEnabled?.(v));
  check('avatar-freeze','Jeda pose',false,v=>this.provider?.setFreezePose?.(v));
  check('avatar-slow','Gerak 0,25×',false,v=>this.provider?.setAnimationSpeed?.(v ? .25 : 1));
  const reset=document.createElement('button');reset.type='button';reset.textContent='Reset simulasi';reset.onclick=()=>this.provider?.resetSimulation?.();tools.append(reset);
  const expression=document.createElement('select');expression.id='avatar-expression-qa';expression.setAttribute('aria-label','Ekspresi QA');expression.append(new Option('Ekspresi · Auto',''));for(const name of Object.keys(FACE_PROFILES))expression.append(new Option(name,name));expression.onchange=()=>this.provider?.setExpressionOverride?.(expression.value);tools.append(expression);
  for(const [key,label]of[['head_tilt','Miringkan kepala'],['fast_turn','Menoleh cepat'],['shoulders','Gerak bahu']])this.$('avatar-motion').append(new Option(label,key));
  const calibration=document.createElement('small');calibration.id='avatar-calibration-info';this.$('avatar-metrics').after(calibration);
  for(const [key,label]of [['premium_studio','Premium Studio'],['soft_anime','Soft Anime'],['dark_environment','Dark Environment']])this.$('avatar-lighting').append(new Option(label,key));
  this.$('avatar-test-motion').onclick=()=>{if(!(this.provider instanceof VRMAvatarProvider)||!this.loaded){this.$('avatar-test-status').textContent='Pilih VRM untuk pengujian rig.';return}this.provider.playMotion(this.$('avatar-motion').value);this.$('avatar-test-status').textContent='SIMULASI QA · '+this.$('avatar-motion').selectedOptions[0].textContent+' · 12 detik';};
  this.$('avatar-reset-style').onclick=()=>{for(const [id,value]of[['avatar-lighting','default'],['avatar-material','source'],['avatar-quality','balanced'],['avatar-framing','portrait']])this.$(id).value=value;this.$('avatar-debug').checked=false;this.provider?.setLighting?.('default');this.provider?.setMaterial?.('source');this.provider?.setFraming?.('portrait');this.provider?.setQuality('balanced');this.provider?.setDebug?.(false);this.$('avatar-view').value='front';this.provider?.setView?.('front');for(const [id,value]of[['avatar-r1',true],['avatar-physics',true],['avatar-freeze',false],['avatar-slow',false]])this.$(id).checked=value;this.$('avatar-expression-qa').value='';this.provider?.setEnhanced?.(true);this.provider?.setPhysicsEnabled?.(true);this.provider?.setFreezePose?.(false);this.provider?.setAnimationSpeed?.(1);this.provider?.setExpressionOverride?.('')};
  this.$('avatar-record').onclick=()=>this.recordCanvas();
 }
 recordCanvas(){
  if(this.recording)return;const canvas=this.$('avatar-canvas');
  if(!canvas.captureStream||typeof MediaRecorder==='undefined'){this.$('avatar-test-status').textContent='Rekaman kanvas tidak didukung browser ini.';return}
  const provider=this.provider,stream=canvas.captureStream(30),parts=[];let recorder,audioTap;
  try{audioTap=this.voice.recordingTap?.();if(audioTap)for(const track of audioTap.stream.getAudioTracks())stream.addTrack(track);recorder=new MediaRecorder(stream,{mimeType:'video/webm'})}catch(e){audioTap?.close();for(const track of stream.getTracks())track.stop();this.$('avatar-test-status').textContent='Rekaman belum dapat dimulai: '+e.message;return}
  if(provider instanceof VRMAvatarProvider){provider.captureActive=true;provider.schedule()}
  const record=this.recording={recorder,stream,save:true,timer:null};this.$('avatar-record').disabled=true;
  recorder.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
  recorder.onstop=()=>{clearTimeout(record.timer);if(provider instanceof VRMAvatarProvider)provider.captureActive=false;audioTap?.close();for(const track of stream.getTracks())track.stop();this.recording=null;this.$('avatar-record').disabled=false;
   if(record.save){const url=URL.createObjectURL(new Blob(parts,{type:'video/webm'})),link=document.createElement('a');link.href=url;link.download='leva-avatar-qa.webm';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);this.$('avatar-test-status').textContent='Rekaman kanvas selesai · file WebM diunduh pada perangkat ini.'}else this.$('avatar-test-status').textContent='Rekaman dibatalkan · file tidak diunduh.'};
  recorder.start();this.$('avatar-test-status').textContent='Merekam kanvas'+(audioTap?' + suara Leva':'')+' 12 detik · tanpa mic atau kamera';record.timer=setTimeout(()=>{if(recorder.state!=='inactive')recorder.stop()},12000);
 }
 cancelRecording(){const r=this.recording;if(!r)return;r.save=false;clearTimeout(r.timer);for(const track of r.stream.getTracks())track.stop();if(r.recorder.state!=='inactive')r.recorder.stop()}
 update(state){const value=state.avatar||{};this.lastAvatar=value;const active=value.enabled&&state.workspace==='companion_avatar';this.$('companion-stage').hidden=!active;
  if(!this.$('companion-form').contains(document.activeElement)){this.$('companion-enabled').checked=!!value.enabled;this.$('companion-label').value=value.display_name||'Leva ♡';this.$('trial-enabled').checked=!!state.experimental_models_enabled;
   this.$('avatar-asset').replaceChildren(...Object.entries(value.asset_choices||{placeholder:'Placeholder 2D'}).map(([k,v])=>new Option(v,k)));this.$('avatar-asset').value=value.asset||'placeholder';this.$('avatar-gpu').value=value.renderer_gpu||'rtx4050';this.$('realtime-speech').checked=!!value.realtime_speech;this.$('native-voice-stream').checked=!!value.native_stream;}
  if(!active){this.$('companion-stage').classList.remove('avatar-focused');this.$('avatar-focus').textContent='Perbesar avatar';this.$('avatar-focus').setAttribute('aria-pressed','false');this.cancelRecording();this.provider?.dispose();this.provider=null;this.providerKey=null;return}
  const key=(value.asset||'placeholder')+'|'+value.renderer_gpu;
  if(!this.provider||this.providerKey!==key){
   this.cancelRecording();this.provider?.dispose();this.providerKey=key;this.loaded=false;this.loadError='';
   const old=this.$('avatar-canvas'),canvas=old.cloneNode(false);old.replaceWith(canvas);
   const options={level:()=>this.voice.outputLevel||0,audioPlaying:()=>!!(this.voice.enabled&&this.voice.source&&this.voice.context?.state==='running'),
    onMetrics:m=>{this.$('avatar-metrics').textContent=`Frame p95 ${m.frame_p95_ms.toFixed(1)} ms · draw ${m.draw_ms.toFixed(2)} ms · ${m.samples} sampel`+(m.profile?` · ${m.profile} · fisika ${m.physics_hz} Hz · ${m.spring_joints} joint / ${m.colliders} collider · ${m.mtoon_materials} MToon · ${m.draw_calls} draw / ${m.triangles} tri`:'');if(m.renderer)this.$('avatar-renderer-info').textContent=`Browser: ${m.renderer} · permintaan ${value.renderer_gpu} · ${m.gpu_verified?'cocok':'belum cocok/terverifikasi'}`;if(m.calibration)this.$('avatar-calibration-info').textContent=(m.enhanced?'R1':'Baseline')+' · profil '+m.calibration.profile+(m.calibration.limited?' · morph terbatas':'')+' · physics '+m.physics_ms.toFixed(2)+' ms · '+JSON.stringify(m.calibration.weights)+' · tersedia: '+m.supported_expressions.join(', ');}};
   if(value.asset&&value.asset!=='placeholder'){
    canvas.setAttribute('aria-label','Avatar VRM 3D · rotasi dengan drag');this.provider=new VRMAvatarProvider(canvas,options);
    const provider=this.provider;provider.load({url:'/api/avatar-model/'+value.asset+'.vrm',requestedGPU:value.renderer_gpu}).then(()=>{if(this.provider===provider){this.loaded=true;provider.setLighting(this.$('avatar-lighting').value);provider.setFraming(this.$('avatar-framing').value);provider.setMaterial(provider.canModify?this.$('avatar-material').value:'source');provider.setDebug(this.$('avatar-debug').checked);this.$('avatar-material').disabled=!provider.canModify;this.$('avatar-material').value=provider.canModify?this.$('avatar-material').value:'source';provider.setView(this.$('avatar-view').value);provider.setEnhanced(this.$('avatar-r1').checked);provider.setPhysicsEnabled(this.$('avatar-physics').checked);provider.setFreezePose(this.$('avatar-freeze').checked);provider.setAnimationSpeed(this.$('avatar-slow').checked ? .25 : 1);provider.setExpressionOverride(this.$('avatar-expression-qa').value);this.$('avatar-source').textContent=value.asset==='leva_original'?'Leva GFL2 · VRM asli tanpa modifikasi · preview sementara':'VRM dimuat · rotasi dengan drag'}}).catch(e=>{if(this.provider===provider){this.loadError=e.message;this.$('avatar-source').textContent='VRM belum dapat dimuat: '+e.message;provider.dispose()}});
   }else{canvas.setAttribute('aria-label','Placeholder orisinal 2D');this.provider=new PlaceholderAvatar(canvas,options);this.loaded=true;}
   this.provider.setQuality(this.$('avatar-quality').value);
  }
  const shown=performance.now()<(this.demoUntil||0)?{...value,expression:'happy'}:value;
  this.provider.update(shown);this.$('avatar-name').textContent=value.display_name||'Leva ♡';this.$('avatar-status').textContent=`${shown.state||'idle'} · ${shown.expression||'neutral'}`+(this.$('avatar-expression-qa').value?' · QA '+this.$('avatar-expression-qa').value:'');
  if(performance.now()>=(this.demoUntil||0))this.$('avatar-source').textContent=this.loadError?'VRM belum dapat dimuat: '+this.loadError:!this.loaded?'Memuat renderer / model VRM…':value.asset&&value.asset!=='placeholder'?(value.asset==='leva_original'?'Leva GFL2 · VRM asli tanpa modifikasi · preview sementara':(value.asset_choices?.[value.asset]||'VRM pribadi')+' · rotasi dengan drag · bukan Leva final'):'PLACEHOLDER 2D · mulut mengikuti audio perangkat ini';
  this.$('avatar-privacy').textContent=`Mic laptop ${value.mic_authorized?'diizinkan sesi ini':'off'} · mic HP tekan-tahan · riwayat hanya sesi · tanpa alat PC`;
 }
 dispose(){this.cancelRecording();this.provider?.dispose();this.provider=null}
}
