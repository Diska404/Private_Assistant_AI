// Layout and display preferences only. This module never invokes an agent.
export function setupWorkspace(){
 const $=id=>document.getElementById(id),panel=document.querySelector('.chat-panel');
 panel.querySelector('.eyebrow').id='room-eyebrow';const heading=panel.querySelector('h2');for(const node of [...heading.childNodes])if(node.nodeType===Node.TEXT_NODE)node.remove();const roomHeading=document.createElement('span');roomHeading.id='room-heading';heading.append(roomHeading);
 const flow=document.createElement('div');flow.id='chat-flow';flow.className='chat-flow';
 panel.insertBefore(flow,$('room-form'));
 const options=document.createElement('details');options.id='chat-options';options.className='chat-options';
 const summary=document.createElement('summary');summary.textContent='Sesuaikan ruang · model, suara & persona';options.append(summary);
 const optionsBody=document.createElement('div');optionsBody.className='options-body';options.append(optionsBody);
 for(const el of [$('room-form'),$('voice-controls'),document.querySelector('.persona-panel')])optionsBody.append(el);
 flow.append(document.querySelector('.session-line'),options,$('handoff-panel'),$('speech-progress'),$('process-panel'),$('messages'));const preview=document.createElement('article');preview.id='stream-preview';preview.className='message assistant stream-preview';preview.hidden=true;const title=document.createElement('strong');title.textContent='Leva';const prose=document.createElement('div');prose.id='stream-preview-text';prose.className='message-body';preview.append(title,prose);flow.append(preview);
 const progress=document.createElement('button');progress.type='button';progress.id='process-toggle';progress.textContent='Proses';progress.onclick=()=>{const panel=$('process-panel');panel.open=!panel.open;panel.scrollIntoView({block:'nearest',behavior:'smooth'})};document.querySelector('.chat-actions').prepend(progress);
 $('voice-controls').open=false;
 const label=document.createElement('label');label.className='translation-toggle';
 const input=document.createElement('input');input.type='checkbox';input.id='show-japanese';
 try{input.checked=localStorage.getItem('leva.showJapanese')==='true'}catch{}
 const apply=()=>{document.body.dataset.showJapanese=String(input.checked);try{localStorage.setItem('leva.showJapanese',String(input.checked))}catch{}};
 input.onchange=apply;label.append(input,document.createTextNode('Tampilkan teks 日本語'));optionsBody.prepend(label);apply();
 $('attach-message').textContent='＋';$('attach-message').title='Lampirkan berkas';$('attach-message').setAttribute('aria-label','Lampirkan berkas');
 $('message-files').removeAttribute('accept');
 $('workspace-heading').textContent='Ada ruang untuk setiap ceritamu.';
}

export async function cropAvatar(file,{api,onSaved}){
 if(file.size>5*1024*1024)throw new Error('Foto maksimal 5 MB.');
 const url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Foto belum dapat dibaca.'));reader.readAsDataURL(file)}),image=new Image();image.src=url;
 try{await image.decode()}catch{throw new Error('Foto belum dapat dibaca.')}
 if(image.naturalWidth*image.naturalHeight>16000000){throw new Error('Foto maksimal 16 MP.')}
 const dialog=document.createElement('dialog');dialog.className='avatar-dialog';dialog.setAttribute('aria-label','Sesuaikan foto profil Leva');
 const title=document.createElement('h2');title.textContent='Buat Leva terasa milikmu.';
 const hint=document.createElement('p');hint.textContent='Geser foto dan sesuaikan zoom. Foto tersimpan setelah konfirmasi.';
 const canvas=document.createElement('canvas');canvas.width=512;canvas.height=512;canvas.className='avatar-crop';canvas.setAttribute('aria-label','Pratinjau foto; geser untuk mengatur posisi');
 const zoom=document.createElement('input');zoom.type='range';zoom.min='1';zoom.max='4';zoom.step='.01';zoom.value='1';zoom.setAttribute('aria-label','Zoom foto');
 const x=document.createElement('input'),y=document.createElement('input');for(const el of [x,y]){el.type='range';el.min='0';el.max='1';el.step='.005';el.value='.5'}x.setAttribute('aria-label','Posisi horizontal foto');y.setAttribute('aria-label','Posisi vertikal foto');
 const controls=document.createElement('div');controls.className='crop-sliders';for(const [text,el]of [['Zoom',zoom],['Horizontal',x],['Vertikal',y]]){const label=document.createElement('label');label.append(document.createTextNode(text),el);controls.append(label)}
 const buttons=document.createElement('div');buttons.className='dialog-actions';const cancel=document.createElement('button'),save=document.createElement('button');cancel.textContent='Batalkan';save.textContent='Gunakan foto';save.className='primary';buttons.append(cancel,save);
 const status=document.createElement('p');status.setAttribute('role','status');dialog.append(title,hint,canvas,controls,status,buttons);document.body.append(dialog);
 const frame=()=>({x:Number(x.value),y:Number(y.value),zoom:Number(zoom.value)});
 const draw=()=>{const f=frame(),side=Math.min(image.naturalWidth,image.naturalHeight)/f.zoom,left=Math.max(0,Math.min(image.naturalWidth-side,f.x*image.naturalWidth-side/2)),top=Math.max(0,Math.min(image.naturalHeight-side,f.y*image.naturalHeight-side/2)),ctx=canvas.getContext('2d');ctx.clearRect(0,0,512,512);ctx.drawImage(image,left,top,side,side,0,0,512,512);ctx.strokeStyle='#b7ede5';ctx.lineWidth=2;ctx.beginPath();ctx.arc(256,256,254,0,Math.PI*2);ctx.stroke()};
 for(const el of [zoom,x,y])el.oninput=draw;
 let last=null;canvas.onpointerdown=e=>{last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)};
 canvas.onpointermove=e=>{if(!last)return;const side=Math.min(image.naturalWidth,image.naturalHeight)/Number(zoom.value),width=canvas.getBoundingClientRect().width;x.value=Math.max(0,Math.min(1,Number(x.value)-(e.clientX-last[0])/width*side/image.naturalWidth));y.value=Math.max(0,Math.min(1,Number(y.value)-(e.clientY-last[1])/width*side/image.naturalHeight));last=[e.clientX,e.clientY];draw()};canvas.onpointerup=canvas.onpointercancel=()=>last=null;
 const close=()=>dialog.close();cancel.onclick=close;dialog.onclose=()=>{dialog.remove()};
 save.onclick=async()=>{save.disabled=cancel.disabled=true;status.textContent='Menyimpan foto ke laptop…';try{const result=await api('/api/avatar',{method:'POST',headers:{'Content-Type':file.type,'X-Leva-Crop':JSON.stringify(frame())},body:file});await onSaved(result);close()}catch(error){status.textContent=error.message;save.disabled=cancel.disabled=false}};
 dialog.showModal();draw();return dialog;
}
