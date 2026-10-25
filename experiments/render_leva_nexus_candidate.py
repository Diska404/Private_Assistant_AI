"""Render evidence from the actual Nexus-reference experiment, without rerunning inference."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
OUT = DATA / "verification/leva-nexus-candidate-v2"
audit = json.loads((DATA / "research/leva-gfl2/nexus-download-audit.json").read_text(encoding="utf-8"))
proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
checks = json.loads((OUT / "asr-check.json").read_text(encoding="utf-8"))
old = json.loads((DATA / "verification/leva-openvoice-candidate/asr-check.json").read_text(encoding="utf-8"))
asr = {r["file"]: r for r in checks["rows"]}
e = html.escape


def audio(path): return '<audio controls preload="none" src="' + e(Path(path).name, quote=True) + '"></audio>'


content = []
for row in proof["references"]:
    content.append('<section><h2>Referensi: '+e(Path(row["original_path"]).stem)+'</h2><p lang="ja">'+
                   e(row["reference_transcript"])+ '</p>'+audio(row["path"])+'</section>')
for base, converted in zip(proof["base"], proof["converted"]):
    item = asr.get(Path(converted["path"]).name, {})
    content.append('<section><h2>'+e(base["text"])+ '</h2><p>Piper dasar · belum konversi</p>'+audio(base["path"])+
                   '<p>Kandidat Leva · referensi Nexus · pitch 0</p>'+audio(converted["path"])+
                   '<p>Konversi %.3f detik · audio %.3f detik<br>ASR: %s</p></section>' %
                   (converted["conversion_seconds"], converted["duration_seconds"], e(item.get("transcript", ""))))
page = '''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kandidat Leva · Referensi Nexus</title><style>body{max-width:1000px;margin:30px auto;padding:0 22px;font:17px/1.6 system-ui;background:#0b1120;color:#e7edf8}
section{background:#142033;padding:22px;border-radius:14px;margin:20px 0}h1,h2{line-height:1.35}h2{font-size:21px}audio{width:100%;max-width:700px;display:block}
a{color:#7ce4ca}.notice{padding:16px;border-left:5px solid #e5b65e;background:#282132}</style><h1>Kandidat suara Leva · referensi Nexus</h1>
<p>19 Oktober 2026 · Piper Indonesia → OpenVoice V2 · RTX 4050</p><p class="notice">Inferensi ucapan baru berhasil. Ini profil cloning eksperimental,
bukan checkpoint GPT-SoVITS/RVC Leva dari pembuat. Kemiripan perlu penilaian pendengaran, hak distribusi belum ditetapkan,
dan percakapan Leva.exe belum memakai profil ini. Tidak ada autoplay, mikrofon atau unggahan audio.</p>
<p>Dengarkan referensi Jepang, Piper dasar dan kandidat Indonesia. Nilai kemiripan, artikulasi, noise dan kenyamanan secara terpisah.</p>'''
page += "\n".join(content) + '<p><a href="proof.json">Metrik</a> · <a href="asr-check.json">ASR lokal</a></p></html>'
(OUT / "comparison.html").write_text(page, encoding="utf-8")
summary = audit["audio_summary"]
alignment = audit["japanese_alignment"]
rows = proof["converted"]
text = f'''# Audit unduhan Nexus dan kandidat suara Leva v2

19 Oktober 2026, WIB. **Unduhan pengguna telah diperiksa secara baca-saja, kemudian tiga ucapan Indonesia baru berhasil dibuat memakai profil referensi Nexus dan OpenVoice V2 pada RTX 4050.** Kemiripan karakter belum dinilai melalui pendengaran pengguna; belum menjadi suara aktif pada Leva.exe.

## Isi folder pengguna

Sumber: `D:\\AI\\AI Lokal Asisten\\Model Suara Leva`.

| Temuan | Hasil pemeriksaan |
|---|---|
| Seluruh berkas | {audit['file_count']} |
| Audio SWATJudge | {summary['readable_count']} berkas, semuanya terbaca |
| Isi audio sebenarnya | Header WAV, PCM 16-bit, mono, 48.000 Hz, walaupun ekstensi `.ogg` |
| Durasi berkas total | {summary['total_seconds']:.2f} detik / {summary['total_seconds']/60:.2f} menit, termasuk jeda dan variasi dialog |
| Rentang durasi | {summary['min_seconds']:.2f}–{summary['max_seconds']:.2f} detik |
| Subtitle | 12 CSV bahasa |
| CSV Jepang | {alignment['csv_rows']} baris, {alignment['unique_keys']} key unik, {alignment['duplicate_key_count']} baris key duplikat |
| Pasangan subtitle | Semua audio punya key Jepang; {len(alignment['subtitle_without_audio'])} key subtitle tidak memiliki audio |
| Paket Cyberpunk | `000Leva_Voice.archive`, {audit['archives'][0]['bytes']:,} byte, magic RDAR |
| Checkpoint terpisah | Tidak ada `.pth`, `.ckpt`, `.index`, `.onnx`, `.safetensors`, `.pt` atau `.bin` pada pohon folder yang diperiksa |

Ini paket hasil audio/mod game; bukan bukti bobot GPT-SoVITS/RVC tersedia. Isi internal `.archive` Cyberpunk belum dibongkar/diindeks. Jangan menyimpulkan seluruh konten internalnya dari daftar luar. Tidak menjalankan executable atau installer dari folder pengguna.

Metadata lengkap dan hash arsip/CSV: `D:\\AI\\AI Lokal Asisten\\Leva\\research\\leva-gfl2\\nexus-download-audit.json`. File pengguna tidak diganti nama, dipindah, ditimpa atau dihapus.

## Profil dan inferensi baru

Referensi: `PanicRoom04_A_01`, `PanicRoom04_A_02`, `PanicRoom06_B_01`, dipilih karena mempunyai kalimat lengkap tanpa marker varian S. Dibaca dari header, dipotong jeda tepi pada ambang 35 dB dan di-resample ke 22.050 Hz pada salinan hasil. Tidak memakai suara kesakitan/teriakan sebagai target. Klaim bersih berdasarkan aset tanpa campuran gameplay; kemiripan dan kualitas tetap perlu didengar.

OpenVoice V2 memakai bobot umum resmi yang telah diverifikasi hash dan dimuat dengan state dict strict. Profil target disimpan di `D:\\AI\\AI Lokal Asisten\\AI Models\\Leva-GFL2\\OpenVoice-nexus-candidate-v2`, termasuk `target_se.pth`, embedding sumber Piper dan `profile.json`. Ini **profil cloning**, bukan training ulang seluruh model. Embedding sumber dan tiga WAV Piper dari uji v1 digunakan kembali tanpa mengulang sintesis dasarnya. Hasil v1 tetap disimpan.

| Metrik | Hasil aktual |
|---|---|
| GPU | {proof['gpu_name']} |
| Load konverter + watermark | {proof['engine_load_seconds']:.3f} detik |
| Ekstraksi profil target | {proof['target_embedding_seconds']:.3f} detik |
| Waktu konversi tiga sampel | {', '.join(format(r['conversion_seconds'], '.3f') for r in rows)} detik |
| Durasi hasil | {min(r['duration_seconds'] for r in rows):.3f}–{max(r['duration_seconds'] for r in rows):.3f} detik |
| Peak allocated CUDA maksimum per konversi | {max(r['torch_peak_allocated_mib'] for r in rows):.2f} MiB |
| Peak reserved CUDA maksimum per konversi | {max(r['torch_peak_reserved_mib'] for r in rows):.2f} MiB |
| Watermark | WavMark aktif, pesan LEVA |
| Sumber asli | Hash ketiga referensi sama setelah inferensi |

Angka konversi tidak mencakup load, preprocessing, STT, pembentukan teks, Piper atau latensi percakapan. Peak CUDA bukan pemakaian GPU seluruh sistem atau puncak seluruh setup. RTX 5070 belum diuji untuk konverter. Mikrofon/speaker tidak dibuka; audio tidak diunggah.

## Pemeriksaan ucapan

ASR menggunakan faster-whisper-small CPU int8. Ini indikator keterbacaan kecil, bukan skor kemiripan suara. Raw WER tidak menormalkan angka atau pemisahan kata Indonesia; jangan dianggap ukuran klinis/patokan produksi.

| Teks | Transkrip kandidat Nexus | Raw WER |
|---|---|---|
'''
for row in rows:
    check = asr[Path(row["path"]).name]
    text += '| ' + row['text'] + ' | ' + check['transcript'].replace('|', '/') + ' | ' + str(check.get('wer')) + ' |\n'
text += r'''
Percobaan v1 dari video sebelumnya menghasilkan enam sampel (pitch 0/+6). Pemeriksaan ASR menunjukkan pitch +6 jauh lebih sulit dikenali pada ketiga kalimat; tidak dijadikan default untuk v2. Pitch 0 dipakai agar perbandingan sumber referensi lebih terkontrol, bukan klaim bahwa pitch tersebut pasti paling mirip Leva.

Perbandingan audio lengkap: `D:\AI\AI Lokal Asisten\Leva\verification\leva-nexus-candidate-v2\comparison.html`. Referensi Jepang, dasar Piper dan tiga kandidat tersedia lokal tanpa autoplay. `proof.json` mencatat hash, peak/RMS dan waktu; `asr-check.json` mencatat transkrip. Hasil mono, finite, tidak senyap dan durasi sesuai sumber.

Izin pembuat untuk distribusi/pemakaian ulang belum diterima; unduhan mod bukan lisensi bobot/model. Semua percobaan ini lokal memakai berkas yang disediakan pengguna. Tidak ada training seluruh 92 menit, unggahan dataset atau publikasi profil. Dua pesan permohonan engine/checkpoint/izin sudah terkirim: lihat `LEVA_VOICE_CONTACT_LOG.md`.

Tahap berikutnya: nilai audio, perbaiki referensi jika perlu, lalu adapter preview/percakapan lokal dengan pembatalan dan ukur kualitas/latensi ujung-ke-ujung. Voice Pack Manager 0.6 masih memakai fallback netral; belum otomatis beralih ke kandidat ini. Eksperimen Shiroko tetap dipertahankan.
'''
(ROOT / "LEVA_NEXUS_VOICE_PROOF.md").write_text(text, encoding="utf-8")
print(json.dumps({"report": str(ROOT / "LEVA_NEXUS_VOICE_PROOF.md"), "comparison": str(OUT / "comparison.html")}))
