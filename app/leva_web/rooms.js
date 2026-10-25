export class RoomUI{
 constructor({api,command,notice,onSwitch}){
  Object.assign(this,{api,command,notice,onSwitch});this.workspace='assistant';this.files=[];this.settingsKey='';this.pendingUpload=false;
  this.$=id=>document.getElementById(id);
  for(const b of document.querySelectorAll('button[data-workspace]'))b.onclick=()=>command('workspace',b.dataset.workspace);
  this.$('room-form').onsubmit=async e=>{e.preventDefault();await command('room_settings',{workspace:this.workspace,model:this.$('room-model').value,gpu:this.$('room-gpu').value})};
  this.$('handoff-accept').onclick=()=>{if(this.handoff)command('handoff',this.handoff.target)};
  this.$('attach-message').onclick=()=>this.$('message-files').click();
  this.$('clear-attachments').onclick=()=>this.clear();
  this.$('message-files').onchange=async()=>{
   this.pendingUpload=true;this.$('send').disabled=true;
   try{for(const file of this.$('message-files').files){if(this.files.length>=3)throw new Error('Maksimal 3 lampiran.');if(file.size>6*1024*1024)throw new Error('Lampiran maksimal 6 MB.');const row=await api('/api/attachments?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});this.files.push(row);this.renderFiles();}}
   catch(e){notice(e.message)}finally{this.pendingUpload=false;this.$('send').disabled=false;this.$('message-files').value='';}
  };
 }
 clear(){this.files=[];this.renderFiles()}
 renderFiles(){const box=this.$('message-attachments');box.replaceChildren();for(const f of this.files){const chip=document.createElement('span');chip.className='attachment-chip';const name=document.createElement('span');name.textContent=f.name;const kind=document.createElement('small');kind.textContent=f.kind==='image_metadata'?'Metadata gambar':f.kind==='unsupported_binary'?'Isi belum dibaca':f.kind==='archive_inventory'?'Daftar arsip':f.truncated?'Cuplikan':'Berkas';const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label','Lepas '+f.name);remove.onclick=()=>{this.files=this.files.filter(row=>row.id!==f.id);this.renderFiles()};chip.append(name,kind,remove);box.append(chip)}this.$('clear-attachments').hidden=!this.files.length;}

 chatValue(value){return typeof value==='string'?{text:value,workspace:this.workspace,attachments:this.files.map(f=>f.id)}:value}
 update(state){
  const room=state.workspace||'assistant',changed=room!==this.workspace;this.workspace=room;
  if(changed){this.clear();this.onSwitch?.();}
  const labels={assistant:'Asisten',chat:'Chat',secret:'Secret 💗',companion_avatar:state.avatar?.display_name||'Leva ♡'};
  document.body.dataset.workspace=room;
  const heading=this.$('room-heading');if(heading)heading.textContent=room==='companion_avatar'?'Bersama '+labels[room]:room==='secret'?'Leva & kamu 💗':room==='chat'?'Chat bersama Leva':'Ruang kerja';const eyebrow=this.$('room-eyebrow');if(eyebrow)eyebrow.textContent=room==='companion_avatar'?'COMPANION / AVATAR':room==='secret'?'SECRET / PERSONAL':room==='chat'?'CHAT / LEVA':'ASISTEN / LEVA';
  const titles={assistant:'Biar Leva bantu menyelesaikannya.',chat:'Dari pertanyaan, menjadi pemahaman.',secret:'Sini, ceritakan harimu pada Leva.',companion_avatar:'Leva, hadir dalam percakapanmu.'};if(this.$('workspace-heading'))this.$('workspace-heading').textContent=titles[room];
  this.handoff=state.handoff;this.$('handoff-panel').hidden=!this.handoff||room!==this.handoff.source;this.$('handoff-accept').disabled=!!state.busy||!!state.translation_pending;
  if(this.handoff)this.$('handoff-detail').textContent='Leva menyarankan '+labels[this.handoff.target]+'. '+this.handoff.goal;
  for(const b of document.querySelectorAll('button[data-workspace]')){b.classList.toggle('active',b.dataset.workspace===room);b.setAttribute('aria-pressed',String(b.dataset.workspace===room));b.disabled=!!state.busy||!!state.translation_pending;if(b.dataset.workspace==='companion_avatar'){b.hidden=!state.avatar?.enabled;b.textContent=state.avatar?.display_name||'Leva ♡';}}
  this.$('workspace-label').textContent='RUANG KERJA / '+labels[room].toUpperCase();
  this.$('workspace-description').textContent=room==='assistant'?'Agent dengan alat laptop · periksa bukti hasil tindakan.':room==='chat'?'Percakapan dan analisis kiriman · lokal · tanpa alat kendali laptop.':'Teman bicara personal Leva · lokal · tanpa alat kendali laptop.';
  this.$('room-form').hidden=room==='assistant';this.$('attach-message').hidden=false;
  this.$('message').placeholder=room==='assistant'?'Tanyakan sesuatu, atau beri Leva tugas…':room==='secret'?'Ceritakan harimu pada Leva…':'Tanyakan, tempelkan teks, atau lampirkan bahan…';
  const config=state.rooms?.[room];if(!config)return;
  const key=JSON.stringify([room,config]);if(key!==this.settingsKey){this.settingsKey=key;for(const[id,rows,selected]of[['room-model',config.models,config.model],['room-gpu',config.gpus,config.gpu]]){const el=this.$(id);el.replaceChildren(...Object.entries(rows).map(([k,v])=>new Option(v,k)));el.value=selected;}}
  for(const el of this.$('room-form').elements)el.disabled=!!state.busy||!!state.translation_pending;
 }
}
