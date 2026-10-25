"""Real host/worker/server comparison, fixed text across delivery styles."""
import base64
import hashlib
import html
import json
from pathlib import Path
import queue
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from paths import DATA
from voice_pack_service import VoicePackService
from voice_packs import catalog

OUT=DATA/'verification/adaptive-voice-v014/final'
TEXTS={'id':'Aku di sini. Mau kita lanjutkan pekerjaanmu, atau kamu ingin bercerita sebentar?',
       'ja':'ここにいるよ。作業の続きを手伝おうか。それとも、少し話したい？'}

def sha(path):
    with Path(path).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()

def page(proof):
    body=['<!doctype html><meta charset="utf-8"><title>Leva — gaya dan engine</title>',
      '<style>body{background:#101820;color:#edf3f8;font:16px system-ui;max-width:1050px;margin:35px auto;padding:20px}article{background:#1d2b37;padding:18px;border-radius:12px;margin:18px 0}audio{width:100%}small{color:#acbfcd}button{padding:9px}h1{color:#e4bf6e}</style>',
      '<h1>Leva · perbandingan engine dan pembawaan</h1><p>Higgs: kalimat yang sama untuk gaya asisten dan personal. OmniVoice: kandidat engine tambahan; tag emosi Higgs tidak dipaksakan ke engine lain. Native tidak mempunyai referensi identitas tetap.</p>',
      '<button onclick="document.querySelectorAll(\'audio\').forEach(a=>a.pause())">Hentikan semua</button>']
    for pack in ('higgs_leva','higgs_native','higgs_jp_identity','omnivoice_leva','omnivoice_native'):
        body.append('<h2>'+html.escape(catalog()[pack]['name'])+'</h2>')
        for language in ('id','ja'):
            body.append('<article><p>'+html.escape(TEXTS[language])+'</p>')
            for row in proof['samples']:
                if row['pack']!=pack or row['language']!=language:continue
                encoded=base64.b64encode(Path(row['path']).read_bytes()).decode('ascii')
                body += ['<p>'+html.escape(row['style'])+'</p><audio controls preload="none" src="data:audio/wav;base64,'+encoded+'"></audio>',
                         '<small>'+html.escape(f"Audio {row['duration_seconds']:.2f} dtk; host sampai berkas {row['host_seconds']:.2f} dtk; worker PID {row['worker_pid']}")+'</small>']
            body.append('</article>')
    body.append('<script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(b!==a)b.pause()})))</script>')
    (OUT/'comparison.html').write_text('\n'.join(body),encoding='utf-8')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    proof_path=OUT/'proof.json'
    proof=json.loads(proof_path.read_text('utf-8')) if proof_path.exists() else {
        'samples':[],'pipeline':'VoicePackService → external worker → owned audio.cpp loopback server',
        'microphone_opened':False,'playback_started':False,'audio_uploaded':False,
        'human_review':'Prior long Japanese suitable for assistant/daily use; prior short Japanese suitable for personal/emotional use; native and reference both interesting. No winner selected.',
        'text_control':'Same text within each language; style is not chosen from sentence length.'}
    for pack in ('higgs_leva','higgs_native','higgs_jp_identity','omnivoice_leva','omnivoice_native'):
        service=VoicePackService(persistent=True)
        try:
            for language,text in TEXTS.items():
                for style in (('assistant','personal') if pack.startswith('higgs') else ('assistant',)):
                    ident=pack+'_'+language+'_'+style
                    prior=next((r for r in proof['samples'] if r['id']==ident),None)
                    if prior and Path(prior['path']).is_file() and sha(prior['path'])==prior['sha256']:continue
                    started=time.perf_counter();service.generate(pack,text,language=language,style=style)
                    pid=service.worker.process.pid
                    while True:
                        if service.check_timeout():raise RuntimeError('voice_timeout')
                        try:event=service.events.get_nowait()
                        except queue.Empty:time.sleep(.03);continue
                        if event.get('kind')=='error':raise RuntimeError(str(event))
                        if event.get('kind')=='generated':
                            service.accept_generated(event)
                            path=OUT/(ident+'.wav');shutil.copyfile(service.generated,path)
                            row={**event,'id':ident,'pack':pack,'language':language,'style':style,'text':text,
                                 'path':str(path),'sha256':sha(path),'worker_pid':pid,'host_seconds':round(time.perf_counter()-started,4)}
                            proof['samples'].append(row)
                            proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');page(proof)
                            print(json.dumps({k:row[k] for k in ('id','duration_seconds','host_seconds','worker_pid')},ensure_ascii=True),flush=True)
                            service.finish();break
        finally:service.stop()
    proof['status']='16_file_samples_completed_requires_listening'
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');page(proof)

if __name__=='__main__':main()
