"""Write measured evidence from the completed bilingual experiment."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(r'D:\AI\AI Lokal Asisten\Leva')
OUT=DATA/'verification/leva-bilingual-v3'
proof=json.loads((OUT/'proof.json').read_text('utf-8'))
asr=json.loads((OUT/'asr-check.json').read_text('utf-8'))
manifest=json.loads(Path(proof['manifest']).read_text('utf-8'))
assert proof['status']=='file_inference_completed_requires_listening'
assert len(proof['converted'])==18
assert len({r['id'] for r in proof['converted']})==18
assert len(asr['rows'])==30

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

for category in ('base','converted','references','prompts'):
    for row in proof[category]:
        assert sha(row['path'])==row['sha256'], row['path']

preserved=json.loads((DATA/'backups/20261019-leva-voice-priority/shiroko-preservation-hashes.json').read_text('utf-8'))
if isinstance(preserved,dict):
    preserved=preserved.get('files',preserved)
if isinstance(preserved,list):
    checked=[]
    for item in preserved:
        path=item.get('path') or item.get('original') or item.get('source')
        expected=item.get('sha256')
        if path and expected:
            assert sha(path)==expected, 'Shiroko preservation mismatch'
            checked.append(path)
else:
    checked=[]
    for path,expected in preserved.items():
        assert sha(path)==expected, 'Shiroko preservation mismatch'
        checked.append(path)
assert len(checked)==23, 'historical manifest must verify all 23 files'

packages=['kokoro','misaki','pyopenjtalk-plus','fugashi','unidic-lite','torch','torchaudio','transformers','huggingface-hub','numpy','soundfile','munch','faster-whisper']
versions={name:importlib.metadata.version(name) for name in packages}
validation={'audio_hashes_checked':sum(len(proof[k]) for k in ('base','converted','references','prompts')),
    'source_references_unchanged':proof['source_hashes_unchanged'], 'shiroko_files_hash_verified':len(checked),
    'packages':versions,'status':'completed','identity_similarity_validated':False}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')

rows=proof['converted']
report=f'''# Leva — percobaan suara Indonesia dan Jepang v3

19 Oktober 2026, WIB. **18 hasil konversi baru berhasil dibuat: enam Indonesia dan dua belas Jepang.** Ini pembanding Seed-VC terhadap OpenVoice sebelumnya, bukan klaim kemiripan sudah meningkat atau checkpoint Leva hasil fine-tuning sudah dilatih.

## Perubahan yang diuji

- Indonesia: tiga WAV Piper yang sama digunakan kembali agar perbandingan engine lebih terkontrol.
- Jepang: tiga teks baru, masing-masing dibuat Kokoro-82M dengan `jf_alpha` dan `jf_nezumi`, lalu dikonversi. Alpha/Nezumi adalah suara dasar sebelum konversi, bukan nama model Leva.
- Seed-VC Whisper-small / BigVGAN menggantikan OpenVoice pada kandidat ini. Model umum dipakai tanpa fine-tuning, dengan dua prompt referensi Nexus: A satu dialog lengkap; B gabungan dua dialog lain. Kedua susunan referensi tersedia untuk didengar.
- Pengaturan: 30 diffusion steps, CFG 0,7, length adjust 1,0, FP16 pada DiT, pitch shift 0. Tidak menaikkan pitch sebagai pengganti kemiripan karakter.
- Bacaan `四時` diperjelas menjadi `よじ` (yoji) pada input pengucapan. G2P semula membacanya yonji. Hanya dua WAV dasar terkait dan empat hasil konversinya dibuat ulang; hasil sebelum koreksi tersimpan di `revisions/before-time-reading-fix`.

## Hasil dan pengukuran aktual

| Ukuran | Hasil |
|---|---|
| GPU | {proof['gpu_name']} |
| Torch / CUDA | {proof['torch_version']} / {proof['cuda_runtime']} |
| Teks sumber | 3 Indonesia + 3 Jepang; 2 suara dasar Jepang |
| WAV dasar | {len(proof['base'])}; 3 lama dipakai kembali, 6 Jepang baru |
| WAV kandidat final | {len(rows)} |
| Durasi kandidat | {min(r['duration_seconds'] for r in rows):.3f}–{max(r['duration_seconds'] for r in rows):.3f} detik |
| Waktu konversi | {min(r['conversion_seconds'] for r in rows):.3f}–{max(r['conversion_seconds'] for r in rows):.3f} detik |
| Median waktu konversi seluruh kandidat final | {statistics.median(r['conversion_seconds'] for r in rows):.3f} detik |
| Median RTF konversi seluruh kandidat final | {statistics.median(r['real_time_factor'] for r in rows):.3f} |
| Peak allocated CUDA maksimum per konversi | {max(r['torch_peak_allocated_mib'] for r in rows):.2f} MiB |
| Peak reserved CUDA maksimum per konversi | {max(r['torch_peak_reserved_mib'] for r in rows):.2f} MiB |
| Hash hasil/referensi diperiksa | {validation['audio_hashes_checked']} berkas |
| Hash arsip Shiroko cocok | {len(checked)} berkas |

Waktu konversi mencakup pemrosesan berkas dan penyimpanan dalam pemanggilan engine, tidak mencakup load model, TTS dasar, pembentukan teks, STT atau playback. Nilai mencakup konversi pertama pada proses; bukan benchmark warm-only. Peak CUDA adalah statistik allocator Torch, bukan VRAM seluruh sistem. RTF sekitar satu menunjukkan konfigurasi kualitas ini belum merupakan pipeline percakapan berlatensi rendah. RTX 5070 tidak diuji atau dipakai oleh worker ini.

## Pemeriksaan artikulasi

Whisper-small lokal CPU int8 memeriksa sembilan sumber, delapan belas kandidat dan tiga referensi. ASR bukan penilai identitas suara; encoder keluarga Whisper juga dipakai Seed-VC sehingga pemeriksaan ini tidak independen. WER Indonesia/CER Jepang mentah hanya diagnostik kecil; angka dan ejaan kanji tidak dinormalisasi.

| Kandidat | Transkrip ASR | Metrik mentah |
|---|---|---|
'''
for row in asr['rows']:
    if row['category']=='converted':
        report+=f"| {row['id']} | {row['transcript'].replace('|','/')} | {row['metric'].upper()} {row['error_rate']:.4f} |\n"
report+='''
## Reproduksibilitas dan penyimpanan

Semua model baru berada di `D:\\AI\\AI Lokal Asisten\\AI Models\\Leva-Bilingual-v3`. Revisi sumber, revisi HF dan SHA-256 tercatat di `manifest.json`; bobot LFS diverifikasi dengan hash sumber. Profil referensi/config ada di `AI Models\\Leva-GFL2\\SeedVC-bilingual-candidate-v3`.

Environment `D:\\AI\\AI Lokal Asisten\\Leva\\environments\\voice-leva-bilingual` memakai dependency lama melalui path baca-saja dan paket tambahan terpisah. Tidak mengganti paket environment Shiroko/OpenVoice. Versi aktual ada pada `validation.json`.

Sumber Seed-VC dipin; patch menunda impor DAC yang tidak dipakai preset ini dan menyebut sampling rate 16 kHz secara eksplisit pada ekstraktor Whisper (sama dengan nilai default processor). Saat memuat checkpoint, awalan DDP `module.` dihapus. Tiga buffer deterministik (`input_pos`, dua frekuensi timestep) diinisialisasi dari kode untuk kompatibilitas versi; tabel f0 lama yang tidak dipakai preset non-f0 dikeluarkan. Semua tensor tersisa harus cocok secara strict; tidak melakukan pemuatan parsial bobot terlatih secara diam-diam. Detail migrasi ada pada `proof.json`. WAV referensi asli tidak dimodifikasi.

Halaman `D:\\AI\\AI Lokal Asisten\\Leva\\verification\\leva-bilingual-v3\\comparison.html` menyertakan audio dalam HTML, pemilihan bahasa/suara dasar, pembanding OpenVoice lama, penghentian playback, skor pendengaran lokal dan ekspor JSON. Tidak ada autoplay, analitik atau endpoint unggahan. Referensi merupakan hasil audio mod yang disediakan pengguna; kesetaraan dengan rekaman Leva resmi belum diautentikasi.

## Status produk

Suara baru sudah berhasil disintesis untuk uji pendengaran Indonesia/Jepang. Belum fine-tuning khusus Leva, belum suara default Leva.exe, belum streaming, interupsi atau percakapan suara lokal lengkap. Identitas Leva perlu dinilai pengguna; jika kedua suara dasar masih terdengar dominan, pertimbangkan fine-tuning/engine TTS berreferensi setelah memilih dan memvalidasi sumber yang paling dekat.

Pesan kedua pembuat Nexus telah ditarik aksesnya atas permintaan pengguna; lihat `LEVA_VOICE_CONTACT_LOG.md`. Eksperimen ini tidak bergantung pada balasan mereka dan tidak mengirim pesan baru atau audio ke layanan eksternal. Eksperimen Shiroko dan kandidat v1/v2 tetap dipertahankan.

Sumber engine: [Seed-VC resmi](https://github.com/Plachtaa/seed-vc), [Kokoro-82M resmi](https://huggingface.co/hexgrad/Kokoro-82M). Lisensi engine tidak diperlakukan sebagai lisensi aset referensi.
'''
(ROOT/'LEVA_BILINGUAL_VOICE_PROOF.md').write_text(report,encoding='utf-8')
print(json.dumps(validation))
