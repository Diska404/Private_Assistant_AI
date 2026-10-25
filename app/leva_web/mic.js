// Push-to-talk creates a draft only. It never sends an agent task automatically.
export function pcmWav(chunks,rate){
 const length=chunks.reduce((n,c)=>n+c.length,0),source=new Float32Array(length);let offset=0;
 for(const c of chunks){source.set(c,offset);offset+=c.length}
 const count=Math.min(960000,Math.floor(length*16000/rate)),buffer=new ArrayBuffer(44+count*2),view=new DataView(buffer);
 const str=(p,s)=>{for(let i=0;i<s.length;i++)view.setUint8(p+i,s.charCodeAt(i))};
 str(0,'RIFF');view.setUint32(4,36+count*2,true);str(8,'WAVE');str(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,'data');view.setUint32(40,count*2,true);
 for(let i=0;i<count;i++){const x=i*rate/16000,k=Math.floor(x),sample=Math.max(-1,Math.min(1,source[k]*(1-(x-k))+(source[k+1]??source[k])*(x-k)));view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true)}
 return new Blob([buffer],{type:'audio/wav'});
}

export class PhoneMic{
 constructor({button,status,meter,cancel,api,onDraft,onStart,media=globalThis.navigator?.mediaDevices,contextFactory=()=>new AudioContext(),nodeFactory=(ctx)=>new AudioWorkletNode(ctx,'leva-capture')}){
  Object.assign(this,{button,status,meter,cancel,api,onDraft,onStart,media,contextFactory,nodeFactory});this.allowed=false;this.held=false;this.chunks=[];this.token=0;this.pending=false;
  button.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();button.setPointerCapture?.(e.pointerId);this.begin()};
  button.onpointerup=e=>{e.preventDefault();this.end()};button.onpointercancel=()=>this.end(true);button.onlostpointercapture=()=>{if(this.held)this.end(true)};
  button.oncontextmenu=e=>e.preventDefault();button.onkeydown=e=>{if([' ','Enter'].includes(e.key)&&!e.repeat){e.preventDefault();this.begin()}};button.onkeyup=e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();this.end()}};
  cancel.onclick=()=>this.end(true);button.onblur=()=>{if(this.held)this.end(true)};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)this.end(true)});globalThis.addEventListener?.('pagehide',()=>this.end(true));
 }
 enable(value){this.allowed=!!value;this.button.disabled=!value||this.pending;if(!value)this.end(true)}
 say(value){this.status.textContent=value}
 async begin(){
  if(!this.allowed||this.held||this.pending)return;
  if(!this.media?.getUserMedia){this.say('Mic memerlukan browser HTTPS yang mendukung perekaman.');return}
  this.held=true;const token=++this.token;this.chunks=[];this.samples=0;this.cancel.hidden=false;this.button.setAttribute('aria-pressed','true');this.say('Meminta izin mic · tetap tahan tombol…');this.onStart?.();
  try{
   // Resume context within the actual press gesture; never on load or reconnect.
   const context=this.contextFactory();this.context=context;await context.resume();
   if(!this.held||token!==this.token){this.cleanup();return}
   const stream=await this.media.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
   if(!this.held||token!==this.token){stream.getTracks().forEach(t=>t.stop());await context.close();return}
   this.stream=stream;await context.audioWorklet.addModule('/mic-worklet.js');
   if(!this.held||token!==this.token){this.cleanup();return}
   const node=this.nodeFactory(context);this.node=node;this.source=context.createMediaStreamSource(stream);this.silent=context.createGain();this.silent.gain.value=0;
   node.port.onmessage=e=>{
    if(e.data==='flushed'){this.flushed?.();return}
    if(token!==this.token||!this.stream)return;
    const chunk=e.data;if(!(chunk instanceof Float32Array))return;this.samples+=chunk.length;
    if(this.samples>context.sampleRate*60){this.end();return}
    this.chunks.push(chunk);let sum=0;for(const n of chunk)sum+=n*n;this.meter.value=Math.min(1,Math.sqrt(sum/chunk.length)*5);
    this.say('Merekam '+(this.samples/context.sampleRate).toFixed(1)+' dtk · lepas untuk membuat transkrip');
   };
   this.source.connect(node);node.connect(this.silent);this.silent.connect(context.destination);
   this.timer=setTimeout(()=>this.end(),60000);this.say('Merekam · lepas tombol setelah selesai berbicara');
  }catch(e){if(token===this.token){this.say(e.name==='NotAllowedError'?'Izin mic belum diberikan. Tekan dan tahan lagi setelah mengizinkan.':'Mic belum tersedia: '+e.message);this.end(true)}}
 }
 cleanup(){clearTimeout(this.timer);this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;this.source?.disconnect();this.node?.disconnect();this.silent?.disconnect();this.context?.close().catch(()=>{});this.node=this.source=this.silent=this.context=null;this.meter.value=0}
 async end(discard=false){
  const wasHeld=this.held;this.held=false;this.button.setAttribute('aria-pressed','false');clearTimeout(this.timer);
  if(discard){++this.token;this.cleanup();this.chunks=[];if(this.uploadId){this.api('/api/transcribe/cancel',{method:'POST',headers:{'X-Leva-Request':this.uploadId}}).catch(()=>{});this.uploadId=null}this.pending=false;this.button.disabled=!this.allowed;this.cancel.hidden=true;if(wasHeld)this.say('Rekaman dibatalkan · mic mati');return}
  if(!wasHeld)return;
  this.stream?.getTracks().forEach(t=>t.stop());
  this.pending=true;this.button.disabled=true;const token=this.token,rate=this.context?.sampleRate||16000;
  if(this.node)await new Promise(resolve=>{this.flushed=resolve;this.node.port.postMessage('flush');setTimeout(resolve,200)});
  if(token!==this.token)return;
  const parts=this.chunks;this.chunks=[];this.cleanup();
  if(parts.reduce((n,p)=>n+p.length,0)/rate<.2){this.pending=false;this.button.disabled=!this.allowed;this.cancel.hidden=true;this.say('Rekaman terlalu pendek · tekan dan tahan saat berbicara');return}
  const id=crypto.randomUUID();this.uploadId=id;this.say('Mic mati · mengirim rekaman ke ASR laptop…');
  try{
   await this.api('/api/transcribe',{method:'POST',headers:{'Content-Type':'audio/wav','X-Leva-Request':id},body:pcmWav(parts,rate)});
   if(token!==this.token){await this.api('/api/transcribe/cancel',{method:'POST',headers:{'X-Leva-Request':id}});return}
   for(let tries=0;tries<180;tries++){
    if(token!==this.token)return;const result=await this.api('/api/transcribe?id='+encodeURIComponent(id));
    if(token!==this.token)return;
    if(result.status==='completed'){this.onDraft(result.text);this.say(result.text?'Transkrip siap · periksa lalu tekan Kirim. Mic mati.':'Tidak ada ucapan jelas yang dikenali. Mic mati.');return}
    if(['failed','cancelled'].includes(result.status))throw new Error(result.error||'Rekaman dibatalkan');
    this.say(result.status==='queued'?'Mic mati · menunggu tugas/suara laptop selesai…':'Mic mati · ASR laptop membaca rekaman lengkap…');await new Promise(r=>setTimeout(r,1000));
   }
   throw new Error('ASR melewati batas waktu; rekaman tidak dijalankan sebagai tugas.');
  }catch(e){if(token===this.token)this.say('Transkrip belum berhasil: '+e.message)}
  finally{if(token===this.token){this.pending=false;this.button.disabled=!this.allowed;this.cancel.hidden=true;this.uploadId=null}}
 }
}
