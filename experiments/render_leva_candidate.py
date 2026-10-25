"""Render actual candidate audio/metrics. No autoplay, remote media, or model execution."""
import html
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"D:\AI\AI Lokal Asisten\Leva\verification\leva-openvoice-candidate")
proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
asr = json.loads((OUT / "asr-check.json").read_text(encoding="utf-8")) if (OUT / "asr-check.json").exists() else {"rows": []}
asr_by_name = {r["file"]: r for r in asr["rows"]}
e = html.escape


def audio(path):
    return '<audio controls preload="none" src="' + e(Path(path).name, quote=True) + '"></audio>'


sections = []
for row in proof["references"]:
    sections.append('<article><h3>Referensi V dalam video · %.1f–%.1f detik</h3>%s<p>%s</p></article>' %
                    (row["start_seconds"], row["start_seconds"]+row["duration_seconds"], audio(row["path"]),
                     e(asr_by_name.get(Path(row["path"]).name, {}).get("transcript", ""))))
for base in proof["base"]:
    sections.append('<article><h2>' + e(base["text"]) + '</h2><p>Piper Indonesia dasar</p>' + audio(base["path"]))
    for row in [r for r in proof["converted"] if r["id"] == base["id"]]:
        check = asr_by_name.get(Path(row["path"]).name, {})
        sections.append('<h3>Kandidat referensi Leva · pitch %+d</h3>%s<p>Konversi %.3f s · audio %.3f s · RTF %.3f<br>ASR: %s</p>' %
                        (row["pitch_semitones"], audio(row["path"]), row["conversion_seconds"],
                         row["duration_seconds"], row["real_time_factor"], e(check.get("transcript", "belum diuji"))))
    sections.append('</article>')
page = '''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leva · Kandidat OpenVoice pertama</title><style>
body{background:#0b1120;color:#e7edf8;font:17px/1.6 system-ui;max-width:1050px;margin:32px auto;padding:0 22px}
article{background:#142033;padding:22px;border-radius:14px;margin:20px 0}h1,h2,h3{line-height:1.35}h2{font-size:22px}
audio{display:block;width:100%;max-width:700px}a{color:#7ce4ca}.notice{border-left:5px solid #e9b75c;padding:16px;background:#252031}
</style><h1>Leva · kandidat suara pertama</h1><p>19 Oktober 2026 · Piper Indonesia → OpenVoice V2 · RTX 4050</p>
<p class="notice">Ini profil cloning eksperimental dari video yang disediakan pengguna, bukan checkpoint Leva hasil training dari nol.
Kemiripan dan kebersihan referensi belum dinilai melalui pendengaran manusia. Belum terintegrasi ke percakapan Leva.exe.
Hak distribusi sumber/hasil belum ditetapkan. Semua audio lokal; tidak diputar otomatis.</p>
<p>Bandingkan identitas, pelafalan, pitch, noise dan kenyamanan. Pitch +6 hanya pembanding, bukan pilihan terbaik yang sudah ditetapkan.</p>'''
page += "\n".join(sections) + '<p><a href="proof.json">Metrik mentah</a> · <a href="asr-check.json">Pemeriksaan ASR</a></p></html>'
(OUT / "comparison.html").write_text(page, encoding="utf-8")
rows = proof["converted"]
warm = [r for r in rows if not r["first_conversion_in_process"]]
text = f'''# Pembuktian kandidat suara Leva — OpenVoice V2

19 Oktober 2026, WIB. **Enam berkas ucapan Indonesia baru berhasil dihasilkan menggunakan profil referensi dari video Leva yang disediakan pengguna. Kemiripan identitas suara belum tervalidasi oleh pendengaran manusia.** Ini keberhasilan inferensi kandidat, bukan klaim integrasi Leva.exe selesai.

## Yang dibuat

- Engine dasar [OpenVoice V2 resmi](https://github.com/myshell-ai/OpenVoice), commit `{proof['source_commit']}`; bobot [myshell-ai/OpenVoiceV2](https://huggingface.co/myshell-ai/OpenVoiceV2), revision `{proof['model_revision']}`. Bobot konverter 131.320.490 byte, hash cocok dengan LFS sumber.
- Piper membentuk tiga kalimat Indonesia baru. Konverter memindahkan karakter warna suara berdasarkan dua referensi V, bukan memutar ulang dialog video.
- Referensi dipilih pada 13,4–19,6 dan 64,0–67,8 detik melalui jendela subtitle V serta ASR. High-pass 70 Hz dan low-pass 10 kHz saja; belum pemisahan speaker atau pembersihan musik. Kemurnian speaker dan hasil perlu didengar. Delamain dalam video adalah suara lain.
- Profil target dan dua embedding sumber Piper (pitch 0/+6) disimpan di `D:\\AI\\AI Lokal Asisten\\AI Models\\Leva-GFL2\\OpenVoice-candidate-v1`. Ini profil reference-conditioned, **bukan checkpoint Leva hasil fine-tuning**.
- Bobot dasar berada di `D:\\AI\\AI Lokal Asisten\\AI Models\\OpenVoiceV2`. Environment baru menggunakan dependensi Torch/Piper lama secara baca-saja, dengan paket tambahan terpisah. Tidak mengganti paket environment proof Shiroko.
- Model dimuat dengan `weights_only=True`, state dict konverter cocok secara strict. Watermark WavMark aktif dengan pesan LEVA dan bobot dipin ke hash. Tidak membuka mikrofon/speaker atau mengunggah audio.

## Pengukuran aktual

| Ukuran | Hasil |
|---|---|
| GPU | {proof['gpu_name']} |
| Runtime | Torch {proof['torch_version']}, CUDA {proof['cuda_runtime']} |
| Load Piper | {proof['piper_load_seconds']:.3f} detik |
| Load konverter + watermark | {proof['engine_load_seconds']:.3f} detik |
| Ekstraksi embedding target pertama | {proof['target_embedding_seconds']:.3f} detik, termasuk inisialisasi preprocessing pertama |
| Durasi hasil | {min(r['duration_seconds'] for r in rows):.3f}–{max(r['duration_seconds'] for r in rows):.3f} detik |
| Konversi pertama | {rows[0]['conversion_seconds']:.3f} detik |
| Konversi berikutnya | {min(r['conversion_seconds'] for r in warm):.3f}–{max(r['conversion_seconds'] for r in warm):.3f} detik |
| Median RTF setelah konversi pertama | {statistics.median(r['real_time_factor'] for r in warm):.3f} |
| Peak allocated CUDA maksimum | {max(r['torch_peak_allocated_mib'] for r in rows):.2f} MiB |
| Peak reserved CUDA maksimum | {max(r['torch_peak_reserved_mib'] for r in rows):.2f} MiB |

Angka konversi tidak mencakup sintesis Piper, load dingin, pitch shift, ekstraksi embedding sumber atau seluruh latensi percakapan. Tidak ada klaim audio pertama/streaming. Peak CUDA diukur per konversi, bukan puncak seluruh tahap setup atau total pemakaian GPU oleh semua aplikasi. RTX 5070 belum diuji untuk engine ini.

## Perbandingan dan batas hasil

Hasil lengkap, referensi, tiga Piper dasar dan enam konversi: `D:\\AI\\AI Lokal Asisten\\Leva\\verification\\leva-openvoice-candidate\\comparison.html`. Halaman tidak menggunakan autoplay atau sumber jarak jauh. `proof.json` mencatat durasi, sample rate, peak/RMS, hash dan metrik setiap hasil. Semua enam WAV mono, finite, tidak senyap dan durasinya sesuai sumber.

`asr-check.json` adalah pemeriksaan pelafalan dengan faster-whisper-small CPU int8; ini bukan penilaian kemiripan Leva atau pengganti mendengarkan. Pitch +6 mengubah pitch suara dasar sebelum konversi, bukan fine-tuning tambahan. Jangan menyebut suatu pitch paling mirip sebelum dinilai pengguna.

Hak distribusi video/mod dan hasil turunan belum diperoleh. Eksperimen memakai video yang disediakan pengguna untuk evaluasi lokal, tanpa mengunggah model/referensi ke pihak lain. Permohonan checkpoint/izin terpisah sudah dikirim ke kedua pembuat; lihat `LEVA_VOICE_CONTACT_LOG.md`. Tidak mengklaim lisensi engine memberi izin aset suara.

Belum: fine-tuning dataset Leva, kualitas siap produksi, STT/TTS percakapan lokal, streaming, interupsi ujaran, adapter aktif/default pada Leva.exe atau benchmark RTX 5070. Setelah evaluasi pendengaran, perbaiki referensi/pitch atau bandingkan engine lain sebelum integrasi. Shiroko dan hasil historis tetap dipertahankan.
'''
(ROOT / "LEVA_VOICE_CANDIDATE_PROOF.md").write_text(text, encoding="utf-8")
print(json.dumps({"comparison": str(OUT / "comparison.html"), "report": str(ROOT / "LEVA_VOICE_CANDIDATE_PROOF.md"),
                  "outputs": len(rows), "max_allocated_mib": max(r["torch_peak_allocated_mib"] for r in rows)}))
