// Replay of observed host events only. No prompt, arguments or reasoning payload.
export class TraceReplay {
 constructor({api,render,panel,document:doc=document}){
  this.api=api;this.render=render;this.panel=panel;this.doc=doc;this.mode='';this.epoch=0;this.lastFetch=0;this.pending=false;this.live=[];
  const bar=doc.createElement('div');bar.className='trace-toolbar';
  this.select=doc.createElement('select');this.select.setAttribute('aria-label','Riwayat proses tersimpan');
  this.note=doc.createElement('small');this.note.setAttribute('role','status');
  bar.append(this.select,this.note);panel.insertBefore(bar,panel.querySelector('ol'));
  this.reset();this.select.onchange=()=>{this.epoch++;this.pending=false;this.load()};
  panel.addEventListener('toggle',()=>{if(panel.open&&!this.pending)this.load()});
 }
 reset(){this.select.replaceChildren();const option=this.doc.createElement('option');option.value='';option.textContent='Proses saat ini';this.select.append(option);this.note.textContent='';}
 update(mode,rows){
  if(mode!==this.mode){this.mode=mode;this.epoch++;this.pending=false;this.lastFetch=0;this.reset();this.render([])}
  this.live=rows;const visible=['assistant','chat'].includes(mode);this.panel.hidden=!visible;
  if(!visible){this.render([]);return}
  if(!this.select.value)this.render(rows);
  if(this.panel.open&&!this.pending&&Date.now()-this.lastFetch>2000)this.load();
 }
 async load(){
  const mode=this.mode,epoch=this.epoch,run=this.select.value;
  if(!['assistant','chat'].includes(mode))return;
  if(!run)this.render(this.live);
  this.pending=true;this.lastFetch=Date.now();
  try{
   const value=await this.api('/api/trace'+(run?'?run_id='+encodeURIComponent(run):''));
   if(epoch!==this.epoch||mode!==this.mode||value.workspace!==mode)return;
   if(run){this.render((value.events||[]).map(traceRow));this.note.textContent=value.truncated?'Riwayat sebagian · batas penyimpanan atau antrean.':'Riwayat tersimpan · '+run.slice(0,8);}
   else{
    this.reset();for(const r of value.runs||[]){const option=this.doc.createElement('option');option.value=r.run_id;option.textContent=r.updated_at.slice(0,19)+' UTC · '+r.run_id.slice(0,8)+' · '+r.event_count+' event';this.select.append(option)}
    this.note.textContent='Tersimpan 7 hari · maks. 100 proses / 20.000 event';
   }
   const health=value.health||{};
   if(health.dropped||health.error)this.note.textContent+=' · Penyimpanan bermasalah: '+(health.dropped||0)+' event hilang'+(health.error?' · '+health.error:'');
  }catch(error){if(epoch===this.epoch)this.note.textContent='Riwayat belum dapat dibaca: '+error.message}
  finally{if(epoch===this.epoch)this.pending=false}
 }
}
export function traceRow(e){return {elapsed_s:e.elapsed_ms/1000,status:e.provenance+' · '+e.status,label:({'model.ready':'Runtime model siap','model.prompt_started':'Prompt dikirim ke model','model.response_started':'Token jawaban pertama tersedia','model.completed':'Generasi model selesai','voice.deferred':'Overlap suara ditunda karena resource'}[e.event_type]||e.event_type)+(e.metrics?.ttft_ms!=null?' · TTFT '+e.metrics.ttft_ms.toFixed(0)+' ms':''),event_id:e.event_id};}
