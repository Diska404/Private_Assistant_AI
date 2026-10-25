"""Eight offline native/reference Higgs samples; no uploads, mic, or playback."""
import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import numpy as np
import soundfile as sf

DATA = Path(r'D:\AI\AI Lokal Asisten\Leva')
BASE = DATA / 'verification/higgs-naturalness-20261020'
OUT = BASE / 'rtx4050-final'
PROMPTS = [
    ('id_short','id','pendek','Halo, aku Leva. Kamu ingin ditemani mengobrol, atau ada yang bisa kubantu?'),
    ('id_long','id','panjang','Kamu akhirnya kembali. Tadi aku menemukan beberapa artikel yang mungkin cocok dengan masalah laptopmu. Aku akan membandingkan pengalaman pengguna, jenis koneksi, dan hasil pengujiannya terlebih dahulu. Kalau ada informasi menarik di luar topik utama, akan kutawarkan setelah bagian yang paling penting selesai. Jadi, kita mulai dari yang mana? Tidak perlu terburu-buru. Aku di sini, dan kita bisa memeriksanya bersama.'),
    ('ja_short','ja','pendek','おかえり、指揮官。少し話す？ それとも、何か手伝おうか？'),
    ('ja_long','ja','panjang','おかえり、指揮官。あなたのパソコンの問題に関係しそうな記事を、いくつか見つけたの。まずは使っている機種と接続方法、それから実際に試した人の結果を比べてみるわ。気になる話があっても、大事なことを確認してから紹介するね。それで、どこから始めようか。急がなくていいのよ。一緒に、少しずつ確かめていきましょう。'),
]

def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()

def gpu_snapshot():
    result = subprocess.run(['nvidia-smi','--query-gpu=index,uuid,name,memory.used,clocks.sm,utilization.gpu',
        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,creationflags=0x08000000)
    rows=[]
    if result.returncode==0:
        for line in result.stdout.splitlines():
            fields=[v.strip() for v in line.split(',')]
            if len(fields)==6:
                rows.append(dict(zip(('index','uuid','name','memory_mib','sm_mhz','gpu_percent'),fields)))
    return rows

def render_page(proof):
    chunks=['<!doctype html><meta charset="utf-8"><title>Leva — Higgs TTS 3</title>',
        '<style>body{background:#101820;color:#e8edf4;font:16px system-ui;margin:40px auto;max-width:1100px;padding:0 24px}article{background:#1c2934;padding:20px;border-radius:12px;margin:20px 0}audio{width:100%}small{color:#b4c7d8}button{padding:10px;cursor:pointer}h1{color:#efc76e}pre{white-space:pre-wrap}</style>',
        '<h1>Leva · Higgs TTS 3 · Uji pendengaran</h1><p>Suara native tanpa referensi dibandingkan sintesis langsung dengan referensi Leva A. Ini bukan model Leva hasil training baru. Tidak memakai Piper atau Seed-VC pada hasil Higgs.</p>',
        '<p>Semua input memakai token emotion:affection untuk gaya hangat. Native adalah suara yang dihasilkan engine tanpa referensi identitas, bukan satu preset pembicara tetap. Jepang panjang memakai chunker Jepang dengan anggaran 160 karakter.</p>',
        '<p>Nilai kemiripan, kejelasan, naturalitas dan ekspresi secara terpisah. Hasil belum dinyatakan mirip atau fasih hanya karena WAV berhasil dibuat.</p>',
        '<button onclick="document.querySelectorAll(\'audio\').forEach(a=>a.pause())">Hentikan semua</button>']
    ref=proof.get('reference',{})
    if ref.get('path') and Path(ref['path']).is_file():
        encoded=base64.b64encode(Path(ref['path']).read_bytes()).decode('ascii')
        chunks += ['<article><h2>Referensi Leva A</h2><p>'+html.escape(ref.get('text',''))+'</p>',
                   '<audio controls preload="none" src="data:audio/wav;base64,'+encoded+'"></audio></article>']
    for ident,lang,length,text in PROMPTS:
        chunks += ['<article><h2>'+html.escape(ident+' · '+length)+'</h2><p>'+html.escape(text)+'</p>']
        for mode in ('native','leva_A'):
            row=next((r for r in proof['samples'] if r['id']==ident+'_'+mode),None)
            chunks.append('<h3>'+('Native · tanpa cloning' if mode=='native' else 'Referensi Leva A · direct cloning')+'</h3>')
            if row and row.get('valid_audio'):
                encoded=base64.b64encode(Path(row['path']).read_bytes()).decode('ascii')
                chunks.append('<audio controls preload="none" src="data:audio/wav;base64,'+encoded+'"></audio>')
                chunks.append('<small>'+html.escape(f"{row['duration_seconds']:.2f} dtk audio; {row['wall_seconds']:.2f} dtk proses (termasuk load); RTF {row['rtf_total']:.2f}")+'</small>')
            elif row: chunks.append('<p>'+html.escape(row.get('error','Gagal'))+'</p>')
            else: chunks.append('<p>Belum dibuat.</p>')
        chunks.append('</article>')
    chunks.append('<script>document.querySelectorAll("audio").forEach(a=>a.addEventListener("play",()=>document.querySelectorAll("audio").forEach(b=>{if(b!==a)b.pause()})))</script>')
    (OUT/'comparison.html').write_text('\n'.join(chunks),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gpu',default='RTX 5070')
    parser.add_argument('--timeout',type=int,default=240)
    parser.add_argument('--only',default='')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((BASE/'manifest.json').read_text('utf-8'))
    executables=list(Path(manifest['runtime']).rglob('audiocpp_cli.exe'))
    if len(executables)!=1: raise RuntimeError('expected_one_cli')
    exe=executables[0]
    model=Path(manifest['model'])
    if sha(model)!=manifest['files'][0]['sha256']: raise RuntimeError('model_hash_changed')
    old=json.loads((DATA/'verification/leva-bilingual-v3/proof.json').read_text('utf-8'))
    ref=next(r for r in old['prompts'] if r['id']=='A')
    if sha(ref['path'])!=ref['sha256']: raise RuntimeError('reference_hash_changed')
    gpus=gpu_snapshot()
    selected=[r for r in gpus if args.gpu in r['name']]
    if len(selected)!=1: raise RuntimeError('gpu_selection_ambiguous')
    env=os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES=selected[0]['uuid'],PYTHONIOENCODING='utf-8',
               HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    env['PATH']=str(exe.parent)+os.pathsep+env.get('PATH','')
    proof_path=OUT/'proof.json'
    proof=json.loads(proof_path.read_text('utf-8')) if proof_path.exists() else {
        'engine':'Higgs TTS 3 / audio.cpp Q8_0','manifest':str(BASE/'manifest.json'),
        'reference':ref,'samples':[],'human_similarity_validated':False,
        'audio_uploaded':False,'microphone_opened':False,'playback_started':False,
        'note':'Per-process cold load included in timings; not TTFA or warm streaming benchmark.'}
    def save():
        proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        render_page(proof)
    save()
    for ident,lang,length,text in PROMPTS:
        for mode in ('native','leva_A'):
            sample_id=ident+'_'+mode
            if args.only and sample_id!=args.only: continue
            previous=next((r for r in proof['samples'] if r['id']==sample_id and r.get('valid_audio')),None)
            if previous: continue
            path=OUT/(sample_id+'.wav')
            row={'id':sample_id,'language':lang,'length':length,'text':text,'mode':mode,
                 'gpu':selected[0],'before_gpus':gpu_snapshot(),'path':str(path),'valid_audio':False}
            speech='<|emotion:affection|>'+text
            command=[str(exe),'--task','tts' if mode=='native' else 'clon','--family','higgs_audio_tts',
                '--model',str(model),'--backend','cuda','--text',speech,'--out',str(path),
                '--seed','20261020','--max-tokens','1400','--text-chunk-size','160' if lang=='ja' and length=='panjang' else '1024',
                '--session-option','higgs_audio_tts.reference_prefill_mode=exact']
            if lang=='ja': command += ['--text-chunk-mode','japanese']
            if mode=='leva_A': command += ['--voice-ref',ref['path'],'--reference-text',ref['text']]
            row['command']=command
            observations=[]
            done=threading.Event()
            def monitor():
                while not done.is_set():
                    try: observations.append({'at':time.time(),'gpus':gpu_snapshot()})
                    except Exception: pass
                    done.wait(1)
            thread=threading.Thread(target=monitor,daemon=True)
            thread.start()
            start=time.perf_counter()
            log_path=OUT/(sample_id+'.log')
            if log_path.exists():
                backup=OUT/(sample_id+'.attempt-'+str(time.time_ns())+'.log')
                backup.write_bytes(log_path.read_bytes())
            try:
                with log_path.open('w',encoding='utf-8') as log:
                    result=subprocess.run(command,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,
                        stdout=log,stderr=log,timeout=args.timeout,creationflags=0x08000000)
                row['exit_code']=result.returncode
                row['wall_seconds']=round(time.perf_counter()-start,4)
                if result.returncode!=0: raise RuntimeError('engine_exit_'+str(result.returncode))
                audio,sr=sf.read(path,dtype='float32',always_2d=True)
                row.update(duration_seconds=len(audio)/sr,sample_rate=sr,channels=audio.shape[1],
                    peak=float(np.max(np.abs(audio))),rms=float(np.sqrt(np.mean(audio**2))),sha256=sha(path))
                row['rtf_total']=row['wall_seconds']/max(row['duration_seconds'],0.001)
                row['valid_audio']=bool(np.all(np.isfinite(audio)) and row['rms']>0.0001 and row['duration_seconds']>0.3)
            except Exception as exc:
                row['wall_seconds']=round(time.perf_counter()-start,4)
                row['error']=type(exc).__name__+': '+str(exc)
            finally:
                done.set();thread.join(timeout=10)
            row['gpu_observations']=observations
            row['after_gpus']=gpu_snapshot()
            prior=[r for r in proof['samples'] if r['id']==sample_id]
            if prior:
                proof.setdefault('superseded_attempts',[]).extend(prior)
            proof['samples']=[r for r in proof['samples'] if r['id']!=sample_id]+[row]
            save()
            print(json.dumps({k:row.get(k) for k in ('id','valid_audio','duration_seconds','wall_seconds','error')},ensure_ascii=False),flush=True)
            if not row['valid_audio']: raise RuntimeError('sample_failed_check_log: '+str(log_path))
    proof['status']='file_inference_completed_requires_listening'
    save()

if __name__=='__main__':
    import msvcrt
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'.render.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        main()
