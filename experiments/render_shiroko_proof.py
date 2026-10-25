"""Build a local listening page with no autoplay, scripts, external assets or uploads."""
import html
import json
from pathlib import Path

OUT = Path(r"D:\AI\AI Lokal Asisten\Leva\verification\shiroko-voice-proof")
ROOT = Path(__file__).resolve().parents[1]


def main():
    proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
    parts = []
    for base in proof["base"]:
        choices = [base] + [row for row in proof["converted"] if row["id"] == base["id"]]
        cards = []
        for row in choices:
            pitch = row.get("pitch_semitones")
            label = "Piper / suara dasar" if pitch is None else f"Shiroko / pitch +{pitch}"
            elapsed = row.get("synthesis_seconds", row.get("conversion_seconds"))
            cards.append(f'<article><h3>{label}</h3><audio controls preload="none" src="{html.escape(Path(row["path"]).name, quote=True)}"></audio>'
                         f'<small>{row["duration_seconds"]:.2f} detik audio · {elapsed:.3f} detik proses</small></article>')
        parts.append(f'<section><h2>{html.escape(base["id"].replace("_", " / "))}</h2><p class="script">{html.escape(base["text"])}</p><div class="grid">'+"".join(cards)+'</div></section>')
    css = """*{box-sizing:border-box}body{margin:0;background:#080d12;color:#e2ecee;font:16px/1.55 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:46px 24px}header{border-bottom:1px solid #294238;padding-bottom:22px}.eyebrow{color:#70e3b7;font:12px monospace;letter-spacing:3px}h1{font-size:36px;line-height:1.2;margin:14px 0}h2{font-size:21px}h3{font-size:15px;margin:0 0 14px;color:#70e3b7}p,small{color:#a1b1b9}.script{color:#e2ecee;background:#152128;padding:16px;border-radius:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:12px}section{margin:34px 0}article{background:#101b22;border:1px solid #253943;border-radius:12px;padding:20px}audio{width:100%;height:38px}small{display:block;font-size:12px;margin-top:12px}.note{padding:18px;border-left:3px solid #f7c66d;background:#141b20}a{color:#70e3b7}footer{color:#84959d;font-size:13px;margin-top:35px}"""
    page = '<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Leva — Uji suara Shiroko</title><style>'+css+'</style><main><header><div class="eyebrow">LEVA / LOCAL VOICE BENCH</div><h1>Uji suara Indonesia & Shiroko</h1><p>Bandingkan ucapan dasar dan hasil konversi model Anda. Tekan putar pada satu sampel setiap kali.</p></header><p class="note">Contoh audio yang dibuat dari teks. Ini belum percakapan langsung atau eksekusi perintah desktop. Kemiripan suara memerlukan penilaian Anda. Waktu proses adalah sintesis/konversi file, bukan latensi percakapan.</p>'+"".join(parts)+'<footer>Seluruh file berada di komputer ini. Halaman tidak memakai skrip, aset luar, autoplay, atau unggahan. <a href="proof.json">Hasil pengukuran</a> · <a href="asr-check.json">Pemeriksaan ASR otomatis</a></footer></main></html>'
    (OUT / "comparison.html").write_text(page, encoding="utf-8")
    rows = proof["converted"]
    report = """# Uji pertama suara lokal dan Shiroko

Tanggal: 18 Oktober 2026 WIB. Status: konversi berkas selesai; kualitas dan kemiripan karakter belum ditinjau manusia.

Ini uji Piper Indonesia → RVC Shiroko menggunakan tiga kalimat dan tiga nilai pitch. Tidak membuka mikrofon/speaker, mengunggah audio, menjalankan LLM, mengubah suara Google Live, atau mengintegrasikan percakapan langsung ke executable Leva.

"""
    report += f"Piper memakai ONNX CPU. Konversi memakai {proof['gpu_name']} dengan PyTorch {proof['torch_version']}, CUDA {proof['cuda_runtime']}, Applio 3.6.2 commit `c7be7282af0f7b6382cbb2ac780b11242da12916`. Model suara RVC v2, 40 kHz; f0 RMVPE, index rate 0,5, protect 0,33, volume envelope 1,0. Tidak ada training.\n\n"
    report += f"[Buka halaman perbandingan](<{OUT / 'comparison.html'}>) · [Hasil pengukuran](<{OUT / 'proof.json'}>) · [ASR otomatis belum ditinjau](<{OUT / 'asr-check.json'}>)\n\n"
    report += "| Sampel | Pitch | Audio (detik) | Konversi (detik) | RTF |\n| --- | --- | --- | --- | --- |\n"
    for row in rows:
        report += f"| {row['id']} | +{row['pitch_semitones']} | {row['duration_seconds']:.3f} | {row['conversion_seconds']:.3f} | {row['real_time_factor']:.3f} |\n"
    report += f"\nMedian RTF konversi setelah panggilan pertama: {proof['warm_conversion_median_rtf']:.4f}. RTF kurang dari satu berarti konversi berkas lebih cepat daripada durasi audionya; tidak membuktikan streaming atau full duplex siap pakai. Panggilan pertama meliputi pemuatan submodel/kompilasi dan tidak dipakai sebagai statistik warm. Proses RMVPE pada backend ini dapat dimuat lagi per panggilan.\n\n"
    report += f"Puncak alokasi PyTorch pada sampel: {max(r['torch_peak_allocated_mib'] for r in rows):.2f} MiB; puncak reserved {max(r['torch_peak_reserved_mib'] for r in rows):.2f} MiB. Ini metrik allocator PyTorch, bukan seluruh penggunaan GPU. Snapshot nvidia-smi dan keterangannya tersedia dalam proof.json; nilai total GPU termasuk proses lain.\n\n"
    report += "## Mendengarkan\n\nBandingkan sampel suara dasar dengan Shiroko pitch +0, +6 dan +12. Nilai pitch adalah pergeseran nada input, bukan tingkat kemiripan karakter. Jangan memilih berdasarkan angka pitch saja. Nilai pelafalan Indonesia, kejelasan konsonan, intonasi, artefak dan identitas suara. Sampel dasar juga membatasi kualitas hasil konversi.\n\n"
    report += "## Batas dan langkah sesudahnya\n\nASR otomatis digunakan hanya sebagai pemeriksaan kasar keterbacaan file sintetis. Ejaan nama, segmentasi kata dan salah pengenalan bukan bukti pasti kesalahan suara; ASR tidak memvalidasi kemiripan Shiroko. Audio belum dinilai langsung oleh pengguna.\n\nSetelah pemilihan suara, tahap selanjutnya adalah pembagian audio pendek, worker persisten yang dapat dibatalkan, pengenalan ucapan dari mikrofon yang dinyalakan eksplisit, pengosongan seluruh antrean saat interupsi, dan sinkronisasi orb dengan audio yang benar-benar diputar. Benchmark ini tidak menjalankan Qwen, Whisper GPU, game atau OBS bersamaan.\n\n"
    report += "Model dan salinannya berada di D:\\AI\\AI Lokal Asisten\\AI Models; original ZIP dipertahankan. Dependensi hanya dipasang pada environment voice-proof di D. Source uji dan vendor berlisensi berada di experiments pada workspace C. Model publik dipin ke revisi dan hash tersimpan dalam voice-proof-download-manifest.json.\n"
    (ROOT / "SHIROKO_VOICE_PROOF.md").write_text(report, encoding="utf-8")
    print(str(OUT / "comparison.html"))


if __name__ == "__main__":
    main()
