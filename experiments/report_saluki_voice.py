"""Report measured Saluki acceleration and actual executable spoken replies."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(r'D:\AI\AI Lokal Asisten\Leva')

if __name__=='__main__':
    llm=json.loads((DATA/'verification/saluki-v08/proof.json').read_text('utf-8'))
    lab=json.loads((DATA/'verification/saluki-v08/lab-proof.json').read_text('utf-8'))
    speech=json.loads((DATA/'verification/spoken-replies-v08/proof.json').read_text('utf-8'))
    packaged=json.loads((DATA/'verification/spoken-chat-v08/proof.json').read_text('utf-8'))
    assert llm['status']=='comparison_completed' and llm['recommended']=='mtp'
    assert lab['status']=='packaged_saluki_lab_completed' and lab['worker_released']
    assert speech['status']=='synthesis_and_playback_completed'
    assert packaged['status']=='local_chat_synthesis_playback_completed' and packaged['workers_released']
    with (ROOT/'program/Leva/Leva.exe').open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert digest==packaged['exe_sha256']
    synthesis=next(e for e in speech['events'] if e['kind']=='generated')
    first_audio=next(r['seconds_since_tts_start'] for r in packaged['states'] if r['state']=='speaking')
    rows=[]
    for p in llm['profiles']:
        q=p['requests']
        speed=[r['timings']['predicted_per_second'] for r in q]
        total=sum(r['total_ms'] for r in q)/len(q)
        rows.append(f"| {p['acceleration']} | {min(speed):.1f}–{max(speed):.1f} | "+
            ', '.join(f"{r['ttft_ms']:.0f}" for r in q)+f" | {total:.0f} | {p['startup_seconds']} |")
    late=sum(r['backend_ms']>600 for r in lab['rows'])
    report='''# Leva 0.8 — Saluki, MTP/DFlash dan jawaban bersuara

19 Oktober 2026, WIB. Program Windows dibangun dan diuji dengan inferensi serta playback nyata. Tidak ada mikrofon, upload audio, training atau perubahan driver/clock/power dalam pekerjaan ini.

## Model dan akselerasi

Saluki adalah kandidat LLM percakapan/tool calling berbasis Qwen3.8-27B dengan kuantisasi IQ2-mix. Saluki tidak menghasilkan audio sendiri. Angka kualitas pada kartu sumber adalah pengujian penerbit, bukan validasi independen proyek. Varian komunitas Kujira menambahkan head MTP milik model dasarnya. Kami memakai berkas 8.349.689.920 byte dengan hash LFS yang cocok; tidak melatih atau merekayasa ulang bobot.

DFlash2 menggunakan drafter Qwen3.8-27B Q4_K_M 1.143.006.816 byte. Drafter untuk model dasar ini tidak dijamin optimal pada Saluki yang diubah/diquantisasi. MTP dan DFlash adalah pilihan decoding alternatif, tidak ditumpuk dalam satu konfigurasi. Runtime resmi llama.cpp b11721 CUDA13.4 dipasang terpisah pada D dan ZIP diverifikasi terhadap digest GitHub. Model lama/runtime Hermes dipertahankan.

Sumber: [Saluki resmi](https://huggingface.co/ConwayResearch/Underdog-Saluki-27B-1.0), [repack MTP](https://huggingface.co/Kujira/Underdog-Saluki-27B-1.0-MTP-GGUF), [drafter DFlash2](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2-GGUF), [runtime b11721](https://github.com/ggml-org/llama.cpp/releases/tag/b11721).

## Hasil pengujian pada laptop ini

Uji awal berjalan saat RTX5070 tercatat SM60MHz / memory810MHz dan gagal memperoleh jawaban lengkap dalam guard60detik. Hasil/log dipertahankan pada `verification/saluki-v08/runs/low-clock`; tidak dipakai untuk menyimpulkan kecepatan normal atau kualitas model. Penyebab keadaan clock tidak diisolasi. Setelah clock teramati normal kembali, tes yang sama diulang tanpa mengubah pengaturan daya oleh Codex.

Berikut dua request singkat per mode (Indonesia dan Inggris), target RTX5070, context4096, parallel1, thinking off, temperature0, q8 KV; runtime sama. TTFT diukur dari stream hingga delta konten pertama. Waktu startup/verifikasi model terpisah dan tidak termasuk TTFT/token per detik. Prompt kedua memakai sebagian cache, sehingga kedua baris request bukan perbandingan cold start yang identik. Aplikasi lain tetap berjalan; ini probe kecil dan bukan distribusi produksi.

| Mode | Decode token/detik | TTFT ID, EN / ms | Rata-rata total request / ms | Verifikasi + startup / detik |
|---|---|---|---|---|
'''+ '\n'.join(rows)+f'''

**MTP dipilih untuk auto** dari pengukuran ini. DFlash berjalan dan menghasilkan jawaban lengkap, tetapi lebih lambat; acceptance draft yang dilaporkan sekitar 11%, sedangkan MTP sekitar 50–72%. Penyebab perbedaan tidak diisolasi. Probe belum mencakup percakapan panjang, tool calling nyata atau penilaian kualitas menyeluruh. Balasan Indonesia pada probe terbaca wajar, bukan bukti semua tugas lebih baik dari Qwen4B.

## Duplex Lab tidak wajib 35B

Pilihan tersedia: Qwen35B dengan MicroTurn LoRA; Qwen4B prompt saja; Saluki27B prompt saja dengan akselerasi yang dipilih di Pengaturan. Adapter MicroTurn35B tidak dimuat pada Qwen4B atau Saluki. Memakai model kecil dengan policy terlatih serupa membutuhkan adapter yang sesuai atau pelatihan/distilasi tersendiri.

Worker executable Saluki+MTP diuji {len(lab['rows'])} tick Indonesia: {len(lab['rows'])-late} di bawah/tepat600ms, {late} terlambat. Seluruh keluaran memenuhi grammar, tetapi contoh `Bagaimana` / `Mengetahui` belum menjadi jawaban berkelanjutan yang koheren. Latensi yang baik belum membuktikan policy percakapan natural. Lab ini tetap teks, tidak membuka audio atau menerapkan persona/timbre suara.

## Jawaban chat dengan suara kandidat A

Alur: teks pengguna → Qwen4B atau Saluki/Google sesuai provider → jawaban teks → Piper Indonesia → Seed-VC referensi A pada RTX4050 → PCM16 mono22050Hz → playback. Voice pack netral melewati konversi dan menggunakan Piper CPU. Kandidat A dipilih pengguna sebelumnya; ini reference-conditioned conversion, bukan checkpoint Leva hasil fine-tuning dan bukan klaim validasi identitas/izin distribusi ulang.

Centang **Jawaban suara** untuk membacakan balasan baru. Default aktif; pesan startup dan transkrip dari sesi Google Live tidak dibacakan ulang. Teks panjang dipecah sampai480karakter; blok kode dirujuk sebagai tersedia dalam teks. Sintesis per potongan penuh, belum streaming engine. Teks asli tetap utuh. Pengiriman permintaan baru, Stop suara, jeda, tidur, percakapan baru, Lepaskan AI dan keluar membersihkan antrean serta worker. Model chat dilepas sebelum worker sintesis dimulai. Mikrofon lokal belum terhubung.

Uji adapter aplikasi: {synthesis['duration_seconds']} detik audio baru, {synthesis['total_seconds']} detik pemuatan+sintesis, lalu playback_started dan playback_finished tercatat. Uji executable Qwen4B → kandidatA → speaker juga selesai: chat {packaged['chat_seconds']} detik, suara mulai {first_audio} detik setelah tahap TTS dimulai. Jadi jeda ini masih besar dan belum seperti full duplex pada video. Worker satu kali per potongan membebaskan resource, tetapi menambah biaya inisialisasi berulang. Optimasi sesi terbatas, TTS streaming, STT mikrofon dan barge-in audio adalah tahap berikutnya.

## Cara memakai dan bukti

1. Buka `program/Leva/Leva.exe` atau shortcut.
2. Pilih **Lokal · Saluki RTX5070 · uji** atau **Lokal · RTX4050** (Qwen4B).
3. Pengaturan → Akselerasi Saluki: **auto** memakai MTP; plain/mtp/dflash dapat dipilih manual. Dua GPU di UI berlaku untuk Qwen4B.
4. Voice Packs → pilih kandidat Leva atau Indonesia netral → Simpan target. Aktifkan Jawaban suara di jendela utama, lalu kirim pesan.
5. Stop suara menghentikan sintesis/playback. Duplex Lab menyediakan tiga backend secara terpisah; berhentikan lab untuk memulai chat/sesi suara.

Verifikasi:98 tes aplikasi +61 tes eksperimen =159 lulus, self-test IPC/storage executable lulus, uji executable chat+sintesis+playback lulus, dan UI Windows diperiksa. Hash executable akhir `{digest}`. Model/runtime besar telah dilepas setelah pengujian.

Bukti mentah pada D: `verification/saluki-v08/proof.json`, `lab-proof.json`, `verification/spoken-replies-v08/proof.json`, `verification/spoken-chat-v08/proof.json` dan audio terkait. Manifest model: `AI Models/Saluki-27B/manifest.json`. Screenshot UI: `verification/spoken-chat-v08/leva-v08-ui.jpg`. Shiroko, semua pembanding lama dan pilihan A historis dipertahankan. Program0.7 dicadangkan pada `backups/20261019-before-spoken-v08`.
'''
    (ROOT/'SALUKI_AND_SPOKEN_REPLIES.md').write_text(report,encoding='utf-8')
    (DATA/'verification/spoken-chat-v08/release-check.json').write_text(json.dumps({'exe_sha256':digest,
        'app_tests':98,'experiment_tests':61,'saluki_auto':'mtp','saluki_speculative_inference':True,
        'candidate_A_spoken_chat_verified':True,'full_duplex_local_microphone_verified':False},indent=2),encoding='utf-8')
    print(json.dumps({'report':str(ROOT/'SALUKI_AND_SPOKEN_REPLIES.md'),'default_acceleration':'mtp','late_lab_ticks':late}))
