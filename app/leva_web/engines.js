// Shared settings belong to the laptop. Keep drafts until the host acknowledges.
export class EngineSettings {
 constructor(root,send){
  this.root=root;this.send=send;this.dirty=false;this.pending=null;
  this.ids={asr_model:'engine-asr-model',asr_gpu:'engine-asr-gpu',asr_language:'engine-asr-language',agent_local_model:'engine-agent-model',agent_provider:'engine-agent-route'};
  this.fields=Object.fromEntries(Object.entries(this.ids).map(([key,id])=>[key,document.getElementById(id)]));
  this.status=document.getElementById('engine-status');this.save=document.getElementById('engine-save');
  for(const field of Object.values(this.fields))field.onchange=()=>{this.dirty=true;this.status.textContent='Pilihan belum disimpan.'};
  document.getElementById('engine-form').onsubmit=async e=>{
   e.preventDefault();if(this.pending)return;
   const id=crypto.randomUUID();this.pending=id;this.save.disabled=true;
   const values=Object.fromEntries(Object.entries(this.fields).map(([key,field])=>[key,field.value]));
   this.status.textContent='Mengirim pengaturan ke laptop…';
   if(!await this.send('pipeline_settings',values,id)){this.pending=null;this.save.disabled=false;this.status.textContent='Pengiriman belum dipastikan. Periksa koneksi dan status permintaan.'}
  };
 }
 update(snapshot){
  const config=snapshot.state?.pipeline;if(!config?.values){this.root.hidden=true;return}this.root.hidden=false;
  const receipt=(snapshot.commands||[]).find(row=>row.id===this.pending);
  if(receipt&&['dispatched','completed','failed','cancelled','interrupted'].includes(receipt.status)){
   const success=['dispatched','completed'].includes(receipt.status);this.pending=null;
   if(success)this.dirty=false;
   this.status.textContent=success?'Tersimpan di laptop; model akan dimuat sesuai pilihan saat digunakan.':receipt.detail||'Pengaturan belum diterapkan.';
  }
  document.getElementById('engine-summary').textContent=config.summary||'';
  for(const [key,field] of Object.entries(this.fields)){
   const options=Object.entries(config.choices[key]||{}),signature=JSON.stringify(options);
   if(field.dataset.options!==signature){field.replaceChildren(...options.map(([value,label])=>new Option(label,value)));field.dataset.options=signature}
   if(!this.dirty&&!this.pending)field.value=config.values[key];
   field.disabled=!!snapshot.state.busy||!!this.pending;
  }
  this.save.disabled=!!snapshot.state.busy||!!this.pending;
 }
}
