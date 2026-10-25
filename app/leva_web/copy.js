// Explicit local copy/download only. No upload and no training side effects.
export async function copyText(value, environment = globalThis) {
  const text = String(value);
  try {
    if (environment.navigator?.clipboard?.writeText) {
      await environment.navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* User activation or clipboard permission can vary on Android. */ }
  const doc = environment.document;
  if (!doc?.body || !doc.execCommand) return false;
  const box = doc.createElement('textarea');
  box.value = text;box.setAttribute('readonly','');
  box.style.position='fixed';box.style.opacity='0';
  const prior=doc.activeElement;doc.body.append(box);box.select();
  let copied=false;
  try {copied=doc.execCommand('copy');} catch {copied=false;}
  box.remove();prior?.focus?.();return copied;
}

export function downloadConversation(data, format = 'json') {
  const value=format==='txt'?data.text:JSON.stringify(data,null,2);
  const blob=new Blob([value],{type:format==='txt'?'text/plain;charset=utf-8':'application/json;charset=utf-8'});
  const url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download='leva-'+data.workspace+'-'+new Date().toISOString().slice(0,10)+'.'+format;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function setupCopy({api,workspace,notice}) {
  const get=()=>api('/api/conversation?workspace='+encodeURIComponent(workspace()));
  document.getElementById('copy-conversation').onclick=async()=>{
    try {const data=await get();if(!await copyText(data.text)){notice('Clipboard ditolak perangkat. Gunakan Simpan laporan untuk mengunduh percakapan lengkap.');return;}notice('Seluruh percakapan tersalin. Credential disamarkan; tidak diunggah otomatis.');}
    catch(error){notice('Belum tersalin: '+error.message);}
  };
  document.getElementById('export-conversation').onclick=async()=>{
    try{downloadConversation(await get());notice('Laporan percakapan disimpan pada perangkat ini. Kirim secara manual jika ingin ditinjau.');}
    catch(error){notice('Ekspor belum selesai: '+error.message);}
  };
}
