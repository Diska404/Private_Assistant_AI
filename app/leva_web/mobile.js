const $=id=>document.getElementById(id);
const labels={queued:'Mengantre',running:'Dikerjakan',completed:'Selesai',needs_input:'Memerlukan jawaban',failed:'Gagal',cancelled:'Dibatalkan',interrupted:'Terputus · periksa hasil',dispatched:'Diteruskan',unverified:'Belum terverifikasi',submitted:'Dikirim ke proses gambar'};
let pending=null;try{pending=JSON.parse(sessionStorage.getItem('leva.pending')||'null')}catch{}
export function pendingRequest(){return pending}
export function savePending(value){pending=value;try{value?sessionStorage.setItem('leva.pending',JSON.stringify(value)):sessionStorage.removeItem('leva.pending')}catch{}$('retry-send').hidden=!value}
export function mobileSetup(api,onPair,retry){
 $('pair-form').onsubmit=async event=>{event.preventDefault();$('pair-submit').disabled=true;try{await api('/api/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('pair-code').value.trim(),name:$('device-name').value.trim()||'Android'})});$('pair-code').value='';await onPair()}catch(e){$('pair-notice').textContent=e.message}finally{$('pair-submit').disabled=false}};
 $('retry-send').hidden=!pending;$('retry-send').onclick=()=>retry(pending);
 const toggle=$('mobile-graph');
 const showNeural=visible=>{document.body.dataset.mobileNeural=String(visible);toggle.textContent=visible?'Fokus chat':'Tampilkan neural';toggle.setAttribute('aria-expanded',String(visible));};
 let visible=true;try{visible=localStorage.getItem('leva.mobileNeural')!=='false'}catch{}
 showNeural(visible);
 toggle.onclick=()=>{visible=!visible;showNeural(visible);try{localStorage.setItem('leva.mobileNeural',String(visible))}catch{}};
}
export function showPair(){ document.body.dataset.pairing='true';$('pair-panel').hidden=false;$('pair-notice').textContent='Masukkan kode sekali pakai dari Leva Desktop → Pengaturan → Hubungkan Android.'}
export function mobileState(snapshot){
 document.body.dataset.pairing='false';$('pair-panel').hidden=true;const remote=!!snapshot.session?.remote;
 document.body.dataset.remote=String(remote);$('device-status').textContent=(remote?snapshot.session.device+' · HTTPS pribadi':'Terhubung ke laptop')+' · '+(snapshot.state.busy?'Leva bekerja':'Siap');
 $('transport-mode').textContent=remote?'HTTPS PRIBADI':'LOOPBACK ONLY';
 $('arm').hidden=remote;
 if(remote)$('audio-output').textContent='Model suara di laptop · aktifkan pemutaran di perangkat ini untuk mendengar Leva.';
 const box=$('deliveries');box.replaceChildren();
 for(const job of(snapshot.commands||[]).filter(j=>j.kind==='chat').slice(0,5)){
  const d=document.createElement('details'),s=document.createElement('summary'),name=document.createElement('span'),status=document.createElement('strong');
  name.textContent=job.goal?.slice(0,85)||'Permintaan';status.textContent=labels[job.status]||job.status;status.dataset.state=job.status;s.append(name,status);d.append(s);
  const p=document.createElement('p');p.textContent=job.detail||'Hasil akan tersedia setelah desktop memproses.';d.append(p);
  if(job.task_id){const code=document.createElement('code');code.textContent='Lanjutkan melalui chat: lanjut tugas '+job.task_id;d.append(code)}box.append(d);
  if(pending?.id===job.id)savePending(null);
 }
 $('delivery-panel').hidden=!box.childElementCount;
}
