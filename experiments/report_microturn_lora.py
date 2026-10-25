"""Summarize measured LoRA integration evidence without claiming audio duplex."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\microturn-lora')
MODELS=Path(r'D:\AI\AI Lokal Asisten\AI Models\MicroTurn-Duplex')

def main():
    proof=json.loads((OUT/'proof.json').read_text('utf-8'))
    packaged=json.loads((OUT/'packaged-check.json').read_text('utf-8'))
    ui=json.loads((OUT/'ui-check.json').read_text('utf-8'))
    manifest=json.loads((MODELS/'manifest.json').read_text('utf-8'))
    assert proof['status']=='inference_completed_text_only'
    assert packaged['status']=='packaged_lora_inference_completed'
    assert not packaged['service_active_after_stop']
    assert ui['native_ui_checked'] and ui['observed_ticks']==5 and ui['stopped_notice_seen']
    metrics=proof['metrics']
    profile_rows=[]
    for name in ('baseline-5070-cpu24-threads4-mmap.json','profile-5070-cpu24-threads8-none.json',
                 'profile-5070-cpu32-threads8-none.json','profile-dual-cpu16-threads8-none.json'):
        row=json.loads((OUT/name).read_text('utf-8'))
        measured=row.get('metrics',{})
        profile_rows.append(f"| {row.get('gpu_mode','gpu5070')} | {row['cpu_moe_layers']} | {row.get('cpu_threads',4)} | {row.get('load_mode','mmap')} | "
            f"{measured.get('p50_ms','—')} | {measured.get('p95_ms','—')} | {row.get('error') or row['status']} |")
    report=f'''# Penerapan MicroTurn Duplex LoRA pada Leva

19 Oktober 2026, WIB. Model dasar dan LoRA yang sesuai telah diunduh ke D, diverifikasi hash, dimuat bersama dan diuji inferensi nyata. Duplex Lab menyediakan pilihan Qwen 35B + LoRA dan baseline Qwen 4B. **Ini penerapan backend/protokol micro-turn teks; belum percakapan mikrofon/STT/TTS full-duplex lokal.**

## Pasangan model dan runtime

- Model: `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` ({next(r['bytes'] for r in manifest['files'] if r['name'].endswith('UD-Q4_K_M.gguf')):,} byte).
- Adapter: `microturn-duplex-lora.gguf`, skala 1. Identitas/skala dikonfirmasi lewat endpoint `/lora-adapters` setelah startup, bukan hanya keberadaan berkas.
- SHA/revisi sumber pada `D:\\AI\\AI Lokal Asisten\\AI Models\\MicroTurn-Duplex\\manifest.json`. Pengunduhan HTTP range tidak menggandakan seluruh model; SHA-256 berkas gabungan cocok LFS sumber.
- Runtime: `{proof['runtime_path']}`. Perangkat yang dipilih menurut nama llama.cpp: {', '.join(proof['devices'])}; RTX 5070 + RAM, `{proof['cpu_moe_layers']}` lapisan expert pada CPU.
- Context {proof['context_size']} token, parallel 1, ubatch/batch 512, {proof['cpu_threads']} thread CPU, load-mode {proof['load_mode']}. Context berbeda dari contoh pembuat 32768; angka berikut adalah benchmark perangkat ini.
- Model chat utama dan suara kandidat A tidak diganti. Model/LoRA hanya dimuat setelah pengguna memulai mesin lab. Idle 3 menit, stop, jeda dan keluar melepas worker milik Leva.

## Protokol

Prompt sistem dipertahankan persis seperti klien pembuat. Input/riwayat menggunakan ChatML mentah melalui `/completion`, cache prompt, probabilitas token pertama dan ambang listen 0,3. Jika keluaran mulai dengan tag tetapi probabilitas listen di bawah ambang, kandidat token tag diblok lalu decoding diulang. Token template pada input ditolak. Mode batas ketat menolak keluaran >600 ms. Replay manual mempertahankan keluaran valid yang terlambat sebagai riwayat teks dengan label keterlambatan; hasil ini tidak diteruskan ke playback. Input stale/invalid tetap ditolak pada kedua mode.

Adapter dilatih untuk bahasa Inggris. Fragmen Indonesia di bawah adalah pemeriksaan eksploratif dengan prompt asli; bukan hasil fine-tuning Indonesia. Tidak mengklaim memasang LoRA ini ke Qwen 4B atau mengganti sistem chat normal dengan keluaran tiga kata.

## Inferensi aktual

| Ukuran | Hasil |
|---|---|
| LoRA dilaporkan aktif runtime | {proof['lora_loaded']} |
| Verifikasi hash + startup | {proof['verification_and_load_seconds']} detik |
| Startup runtime saja | {proof['load_seconds']} detik |
| Tick diukur | {metrics['measured_ticks']} |
| Median backend per tick | {metrics['p50_ms']} ms |
| p95 backend per tick | {metrics['p95_ms']} ms |
| Tick >600 ms | {metrics['over_600ms']} |
| Retry decoding | {metrics['decoding_retries']} |
| Runtime benchmark ditutup | {proof['owned_runtime_stopped']} |
| Worker executable berhasil inferensi + dihentikan | {packaged['status']}, active={packaged['service_active_after_stop']} |

Waktu diukur dari request backend, termasuk retry bila ada. Bukan latensi sampai suara pertama, ASR, TTS atau mikrofon. Replay berjalan berurutan secepat respons selesai; ini uji teks tanpa jadwal audio 600 ms dan bukan benchmark percakapan manusia. Probe mencampur konteks pendek baru dan tick lanjutan, sehingga bukan distribusi performa produksi. Snapshot VRAM pada JSON mencakup aplikasi lain dan bukan alokasi Leva terisolasi.

| Skenario | Bahasa | Tick | Potongan bicara | Keluaran di luar grammar | Jawaban gabungan |
|---|---|---|---|---|---|
'''
    for row in proof['scenarios']:
        report+=f"| {row['id']} | {row['language']} | {row['ticks']} | {row['spoken_chunks']} | {row['grammar_invalid']} | {row['assembled_response'].replace('|','/')} |\n"
    report+='\n## Perbandingan profil terukur\n\n| GPU | CPU expert layers | Thread | Load | p50 ms | p95 ms | Hasil |\n|---|---|---|---|---|---|---|\n'+'\n'.join(profile_rows)+'\n\nProfil dua GPU gagal sebelum inferensi: alokasi CUDA0 sekitar 12.702 MiB gagal, dan auto-fit tidak dapat berjalan karena tensor-split eksplisit. Ini bukan bukti kedua GPU tidak dapat digunakan; konfigurasi tersebut belum layak. Profil CPU32 dipilih untuk ruang VRAM lebih longgar dan median terbaik pada probe ini. Ketiga profil satu GPU sama-sama gagal memenuhi target 600 ms. Perbedaan kecil median bukan bukti keunggulan statistik.\n'
    report+='''
## Pemakaian program

1. Buka `program\\Leva\\Leva.exe` atau shortcut Leva.
2. Buka **Duplex Lab**, pilih **Qwen 35B + LoRA · profil GPU + RAM**, lalu **Muat mesin pilihan**. Profil terukur dibaca dari `runtime-profile.json` pada folder model: RTX 5070 + RAM, CPU expert 32, 8 thread, load-mode none.
3. Setelah status siap, masukkan fragmen teks. Kolom kosong adalah `<no voice>`. Tombol Kirim tick menjalankan satu permintaan manual; tidak merekam atau memutar suara.
4. Replay manual aktif secara default untuk meninjau riwayat teks walau >600 ms. Hilangkan centangnya sebelum memuat mesin untuk uji batas ketat. Tabel membedakan hasil diterima, invalid dan lewat batas. Status menampilkan waktu backend serta P(listen). **Sela / batalkan tick** menghentikan model dan membersihkan antrean; muat kembali untuk sesi baru.

Google Live, chat normal, voice pack netral dan arsip Shiroko dipertahankan. Tidak mengaktifkan mikrofon saat startup, mengubah driver/undervolt/power, membuat layanan internet, mengunggah audio atau mengirim pesan ke pembuat model. Server inference mengikat loopback dengan token sesi melalui environment, tanpa key dalam argumen proses. Program lama dicadangkan pada `D:\\AI\\AI Lokal Asisten\\Leva\\backups\\20261019-microturn-program`.

Bukti rinci: `proof.json`, `packaged-check.json`, `ui-check.json`, `leva-lora-ui.jpg`, log runtime dan manifest model. Pengujian source: 91 tes aplikasi + 61 tes eksperimen lulus. Self-test IPC/storage executable juga lulus. UI Windows menjalankan lima tick berurutan: empat `<listen>` lalu `That sounds like`, semuanya diberi label replay >600 ms. Tombol Hentikan model menampilkan status model dilepas; pemeriksaan proses sesudahnya tidak menemukan llama-server aktif. Model besar sudah dilepas setelah pengujian. Pembukaan lab tidak mengaktifkan perangkat audio.

Sumber: [adapter dan protokol Codacus](https://huggingface.co/codacus/Qwen3.6-35B-A3B-MicroTurn-Duplex-LoRA), [kuantisasi model dasar](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF). Apache-2.0 menurut metadata sumber; klien asli dipertahankan sebagai referensi, implementasi Leva menambahkan batas input, kepemilikan proses dan pengukuran.
'''
    (ROOT/'MICROTURN_LORA_PROOF.md').write_text(report,encoding='utf-8')
    with (ROOT/'program/Leva/Leva.exe').open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert digest==packaged['exe_sha256'], 'packaged probe must match final executable'
    (OUT/'release-check.json').write_text(json.dumps({'exe_sha256':digest,'lora_inference':proof['status'],
        'packaged_inference':packaged['status'],'tests_app':91,'tests_experiments':61,
        'native_ui_verified':True,'native_ui_ticks':ui['observed_ticks'],
        'full_duplex_audio_verified':False,'microphone_opened':False,'speaker_opened':False},indent=2),encoding='utf-8')
    print(json.dumps({'report':str(ROOT/'MICROTURN_LORA_PROOF.md'),'metrics':metrics}))

if __name__=='__main__':main()
