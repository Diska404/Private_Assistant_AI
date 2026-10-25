// One playback queue for the real desktop voice pack. No speechSynthesis or mic capture.
export class RemoteVoice {
 constructor({button,status,test,send,contextFactory=()=>new AudioContext(),fetchAudio=(...args)=>fetch(...args)}) {
  Object.assign(this,{button,status,test,send,contextFactory,fetchAudio});
  this.enabled=false;this.epoch=null;this.cursor=0;this.queue=[];this.generation=0;this.pumping=false;
  button.onclick=()=>this.toggle();test.onclick=()=>{if(this.enabled)this.send('test_audio')};test.disabled=true;
 }
 note(message){this.status.textContent=message}
 async toggle(){
  if(this.enabled&&this.context?.state==='running'){this.enabled=false;this.stop();this.button.textContent='Aktifkan suara';this.button.setAttribute('aria-pressed','false');this.test.disabled=true;this.note('Suara perangkat ini nonaktif.');return}
  try{
   this.context??=this.contextFactory();await this.context.resume();
   if(this.context.state!=='running')throw new Error('audio_suspended');
   this.enabled=true;this.button.textContent='Matikan suara HP';this.button.setAttribute('aria-pressed','true');this.test.disabled=false;
   this.note('Suara aktif · menunggu balasan baru dari laptop.');this.pump();
  }catch{this.enabled=false;this.note('Audio belum aktif. Ketuk Aktifkan suara kembali.');}
 }
 stop(message=''){
  this.generation++;this.queue=[];this.controller?.abort();
  this.playbackBuffer=null;
  const current=this.source;this.source=null;
  if(current){try{current.stop()}catch{}current.disconnect()}
  if(message)this.note(message);
 }
 get outputLevel(){
  if(!this.enabled||!this.source||this.context?.state!=='running'||!this.playbackBuffer?.getChannelData)return 0;
  const samples=this.playbackBuffer.getChannelData(0),start=Math.max(0,Math.floor((this.context.currentTime-this.playbackStarted)*this.playbackBuffer.sampleRate));
  let power=0,count=0;for(let i=start;i<Math.min(samples.length,start+480);i+=4){power+=samples[i]*samples[i];count++}
  return count?Math.min(1,Math.sqrt(power/count)*4):0;
 }
 get outputFeatures(){
  if(!this.enabled||!this.source||this.context?.state!=='running'||!this.playbackBuffer?.getChannelData)return {zeroCrossingRate:0,available:false};
  const now=this.context.currentTime;if(this.featureSource===this.source&&now-this.featureTime<.008)return this.features;
  const samples=this.playbackBuffer.getChannelData(0),start=Math.max(0,Math.floor((now-this.playbackStarted)*this.playbackBuffer.sampleRate));let crossings=0,count=0;
  for(let i=start+1;i<Math.min(samples.length,start+512);i++){if((samples[i]>=0)!==(samples[i-1]>=0))crossings++;count++}
  this.featureSource=this.source;this.featureTime=now;this.features={zeroCrossingRate:count?crossings/count:0,available:count>0};return this.features;
 }
 disconnected(){this.stop('Koneksi laptop terputus · audio dijeda.');this.fresh=true}
 recordingTap(){
  if(!this.enabled||this.context?.state!=='running'||!this.context.createMediaStreamDestination)return null;
  if(this.recordTap)throw new Error('audio_recording_already_active');
  const destination=this.context.createMediaStreamDestination();this.recordTap=destination;this.source?.connect(destination);
  let closed=false;return {stream:destination.stream,close:()=>{if(closed)return;closed=true;try{this.source?.disconnect(destination)}catch{}for(const track of destination.stream.getTracks())track.stop();if(this.recordTap===destination)this.recordTap=null}};
 }
 update(audio){
  if(!audio){this.note('Perbarui Leva Desktop untuk mengirim suara ke perangkat ini.');this.test.disabled=true;return}
  if(this.epoch===null||this.fresh){this.epoch=audio.epoch;this.cursor=audio.latest;this.fresh=false;if(this.enabled)this.note('Suara aktif · menunggu balasan baru dari laptop.');return}
  if(this.epoch!==audio.epoch){this.stop();this.epoch=audio.epoch;this.cursor=audio.clips.length?audio.clips[0].seq-1:audio.latest;}
  if(!this.enabled){this.cursor=audio.latest;return}
  for(const clip of audio.clips){
   if(clip.seq<=this.cursor)continue;
   this.cursor=clip.seq;
   if(this.queue.length<12)this.queue.push(clip);
  }
  this.pump();
 }
 async pump(){
  if(this.pumping||!this.enabled||!this.queue.length)return;
  if(this.context?.state!=='running'){this.note('Ketuk Aktifkan suara untuk melanjutkan audio.');this.button.textContent='Aktifkan suara';return}
  this.pumping=true;
  try{
   while(this.enabled&&this.queue.length){
    const token=this.generation,clip=this.queue.shift();
    if(!/^\/api\/audio\/[a-f0-9]{24}\/[0-9]{1,12}\.wav$/.test(clip.url))continue;
    this.note('Menerima suara Leva dari laptop…');
    this.controller=new AbortController();const timeout=setTimeout(()=>this.controller?.abort(),10000);
    let bytes;
    try{
     const response=await this.fetchAudio(clip.url,{credentials:'same-origin',signal:this.controller.signal});
     if(!response.ok)throw new Error('audio_unavailable');
     if(Number(response.headers.get('Content-Length'))>12*1024*1024)throw new Error('audio_size');
     bytes=await response.arrayBuffer();
     if(bytes.byteLength>12*1024*1024)throw new Error('audio_size');
    }finally{clearTimeout(timeout)}
    if(token!==this.generation)continue;
    const buffer=await this.context.decodeAudioData(bytes);
    if(token!==this.generation)continue;
    const source=this.context.createBufferSource();source.buffer=buffer;source.connect(this.context.destination);if(this.recordTap)source.connect(this.recordTap);this.source=source;
    this.note('Memutar Leva · '+(clip.language==='ja'?'日本語':'Indonesia')+' · '+buffer.duration.toFixed(1)+' dtk');
    this.status.dataset.played=String(clip.seq);this.status.dataset.pack=clip.pack;
    this.playbackBuffer=buffer;this.playbackStarted=this.context.currentTime;
    await new Promise(resolve=>{source.onended=resolve;source.start()});
    source.disconnect();if(this.source===source)this.source=null;
    this.playbackBuffer=null;
   }
   if(this.enabled&&!this.fresh)this.note('Suara aktif · menunggu balasan baru dari laptop.');
  }catch(error){
   this.status.dataset.error=error.name;
   if(error.name!=='AbortError')this.note('Suara belum diputar. Coba Uji suara Leva atau aktifkan audio kembali.');
  }finally{this.pumping=false;if(this.enabled&&this.queue.length)this.pump()}
 }
}
