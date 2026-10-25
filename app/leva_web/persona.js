export class PersonaSettings {
 constructor(send,activity){
  this.send=send;this.form=document.getElementById('persona-form');this.dirty=false;this.pending=null;
  this.fields={companion_idle:document.getElementById('persona-idle'),companion_playful:document.getElementById('persona-playful'),companion_idle_delay:document.getElementById('persona-delay')};
  this.status=document.getElementById('persona-status');this.save=document.getElementById('persona-save');
  for(const field of Object.values(this.fields))field.onchange=()=>{this.dirty=true;this.status.textContent='Pilihan belum disimpan.'};
  let lastActivity=0;
  const signal=()=>{if(document.hidden||Date.now()-lastActivity<3000)return;lastActivity=Date.now();activity?.(!!document.getElementById('message').value.trim()).catch(()=>{})};
  document.getElementById('message').addEventListener('input',signal);
  document.addEventListener('pointerdown',signal,{passive:true});
  setInterval(()=>{if(document.getElementById('message').value.trim())signal()},4000);
  this.form.onsubmit=async e=>{e.preventDefault();if(this.pending)return;const id=crypto.randomUUID();this.pending=id;this.save.disabled=true;
   const value={companion_idle:this.fields.companion_idle.checked,companion_playful:this.fields.companion_playful.checked,companion_idle_delay:this.fields.companion_idle_delay.value};
   this.status.textContent='Mengirim pengaturan sapaan ke laptop…';
   if(!await this.send('persona_settings',value,id)){this.pending=null;this.save.disabled=false;this.status.textContent='Pengiriman belum dipastikan.'}
  };
 }
 update(snapshot){
  const value=snapshot.state?.companion;if(!value)return;
  const receipt=(snapshot.commands||[]).find(r=>r.id===this.pending);
  if(receipt&&['dispatched','completed','failed','cancelled','interrupted'].includes(receipt.status)){
   const ok=['dispatched','completed'].includes(receipt.status);this.pending=null;if(ok)this.dirty=false;
   this.status.textContent=ok?'Tersimpan pada laptop dan berlaku di semua mode.':receipt.detail||'Pengaturan belum tersimpan.';
  }
  if(!this.dirty&&!this.pending){this.fields.companion_idle.checked=value.companion_idle;this.fields.companion_playful.checked=value.companion_playful;this.fields.companion_idle_delay.value=value.companion_idle_delay}
  for(const field of Object.values(this.fields))field.disabled=!!this.pending;
  this.save.disabled=!!this.pending;
 }
}
