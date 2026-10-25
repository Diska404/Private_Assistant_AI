"""Create only new starter notes in the user-approved Leva vault; never overwrite."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from second_brain import VaultIndex

vault=DATA/'SecondBrain';vault.mkdir(parents=True,exist_ok=True)
notes={
'00_Index/START_HERE.md':'''---
title: Peta pengetahuan Leva
tags: [leva, second-brain, index]
---
# Peta pengetahuan Leva

Vault ini dibuat pada 21 Oktober 2026 untuk catatan yang dapat dibaca Leva.
Catatan dapat diedit melalui Obsidian atau editor Markdown. Perubahan terindeks saat pencarian berikutnya; Refresh indeks memaksa pembacaan ulang.

- [[Leva]] — tujuan dan status proyek.
- [[Perangkat dan Model]] — perangkat serta pembagian peran model.
- [[ComfyUI dan Fooocus]] — lokasi aplikasi gambar.
- [[Preferensi Pemilik]] — pilihan pemilik yang sudah diberikan.
- [[Suara dan Prioritas]] — suara Jepang dan urutan pengembangan.

## Batas saat ini
Konektor Second Brain hanya membaca. Tidak ada sinkronisasi otomatis seluruh chat ke vault, training model, atau koneksi REST/MCP yang diasumsikan aktif.
Catatan menyimpan pengetahuan; perintah dan hasil runtime harus diperiksa pada sistem yang sedang berjalan.
''',
'01_Projects/Leva.md':'''---
title: Proyek Leva
tags: [proyek, asisten]
aliases: [Leva]
---
# Proyek Leva

## Tujuan pemilik
Leva dikembangkan sebagai asisten desktop lokal yang dapat membantu pekerjaan, browser, aplikasi, proyek kode, pengingat, serta workflow gambar. Adaptif dan mandiri merupakan tujuan pengembangan, bukan klaim seluruh pekerjaan sudah andal.

## Lokasi proyek
Source: C:\\Users\\Raizei\\OneDrive\\Documents\\Private WEB\\AI Lokal Asisten
Data dan model besar: D:\\AI\\AI Lokal Asisten
Repositori referensi: D:\\AI\\AI Lokal Asisten\\Github

## Second Brain VIDEO_001
Pembacaan catatan menggunakan indeks SQLite FTS lokal dan cuplikan terbatas. Hubungan pengetahuan memakai wikilink. Fitur tulis vault, plugin REST/MCP, dan embeddings belum menjadi jalur aktif.

Lihat [[Perangkat dan Model]], [[ComfyUI dan Fooocus]], dan [[Suara dan Prioritas]].
''',
'02_Knowledge/Perangkat dan Model.md':'''---
tags: [hardware, model, gpu]
---
# Perangkat dan Model

## Perangkat pemilik
Laptop memiliki NVIDIA RTX 4050 Laptop GPU 6 GB dan GPU NVIDIA RTX 5070 12 GB. Kapasitas bebas berubah sesuai aplikasi yang berjalan; catatan ini bukan telemetri saat ini.

## Peran model pada konfigurasi terakhir yang diuji
Qwen3-ASR 0.6B: pengenalan suara lokal. Saluki 27B IQ2 mix: agent lokal. Higgs Leva: keluaran suara Jepang yang dipertahankan. Google dan 9Router dapat menjadi rute online sesuai pengaturan aplikasi.

## Pembagian sumber daya
Dual ASR yang telah diuji membagi encoder pada RTX 4050 dan decoder pada RTX 5070. Model LLM dapat membagi bobot pada kedua GPU. TTS audio.cpp pada pipeline Dual masih memakai RTX 5070 saja. Konektor Second Brain tidak memuat model tambahan atau memakai GPU untuk pencarian.

[[Leva]] · [[Suara dan Prioritas]]
''',
'02_Knowledge/ComfyUI dan Fooocus.md':'''---
tags: [gambar, workflow]
---
# ComfyUI dan Fooocus

## Lokasi yang diberikan pemilik
ComfyUI: F:\\AI\\ComfyUI_windows_portable
Fooocus juga disimpan di bawah F:\\AI; path instalasi persis mengikuti pengaturan/katalog aplikasi, bukan tebakan dari catatan ini.

## Batas keputusan
Menyusun peta ComfyUI berbeda dari menjalankan generation. Permintaan langsung membuat gambar mengizinkan generation sesuai perintah. Model/checkpoint dipilih dari katalog nyata; nama dalam catatan bukan bukti file masih tersedia.

[[Leva]] · [[Perangkat dan Model]]
''',
'03_Agent_Context/Preferensi Pemilik.md':'''---
tags: [preferensi, pemilik]
---
# Preferensi Pemilik

## Pilihan yang diberikan dalam pengembangan
Nama asisten adalah Leva. Jawaban teks tetap berbahasa Indonesia; bahasa suara dapat dipilih Indonesia atau Jepang. Headset DAXA SL1 dipilih untuk uji input dan output suara terakhir.

## Penyimpanan
Pemilik memilih data besar di D agar tidak memenuhi drive C. Vault awal khusus Leva ini dibuat setelah pemilik memilih opsi tersebut, bukan mengambil vault pribadi yang sudah ada.

## Jawaban dan tindakan
Tautan, emoji, serta output teknis mentah tidak perlu dieja dalam jawaban suara. Pekerjaan panjang perlu reaksi awal dan laporan hasil sesudah pemeriksaan. Preferensi ini tidak membuktikan setiap kemampuan sudah berhasil.

[[Leva]] · [[Suara dan Prioritas]]
''',
'04_Decisions/Suara dan Prioritas.md':'''---
tags: [suara, prioritas]
---
# Suara dan Prioritas

## Identitas
Leva GFL2 menjadi target suara utama. Eksperimen Shiroko dipertahankan sebagai hasil historis, bukan diganti namanya menjadi Leva.

## Penilaian pemilik
Sampel Jepang panjang dinilai cocok untuk percakapan asisten sehari-hari. Sampel Jepang pendek menarik untuk percakapan personal. Penyesuaian variasi model/gaya suara dimasukkan ke antrean penting sementara kemampuan agent dan akses laptop diprioritaskan.

## Perbedaan pengetahuan dan kemampuan
Membaca catatan membantu konteks, tetapi tidak mengubah bobot model, membuat suara baru, atau otomatis memberi kemampuan mengendalikan setiap aplikasi. Hasil nyata diperiksa dari receipt alat dan laporan verifikasi.

[[Leva]] · [[Perangkat dan Model]] · [[Preferensi Pemilik]]
''',
'99_Templates/NOTE_TEMPLATE.md':'''---
title: Judul catatan
tags: [topik]
---
# Judul catatan

## Fakta / sumber
Tuliskan fakta beserta sumber dan tanggalnya. Bedakan rencana dari hasil yang telah diuji.

## Hubungan
[[Leva]]

## Pembaruan
Tanggal dan alasan perubahan.
'''}
created=[];preserved=[]
for relative,content in notes.items():
    path=vault/relative;path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('x',encoding='utf8',newline='') as f:f.write(content)
        created.append(relative)
    except FileExistsError:preserved.append(relative)
(vault/'.obsidian').mkdir(exist_ok=True)
for relative,content in {'.obsidian/app.json':'{"alwaysUpdateLinks": true}\n','.levaignore':'# Local exclusions for the read-only Second Brain index\nPrivate/\nSecrets/\n'}.items():
    try:
        with (vault/relative).open('x',encoding='utf8') as f:f.write(content)
    except FileExistsError:pass
index=VaultIndex(vault);stats=index.refresh();sources=index.search('prioritas suara Jepang Leva',3)
proof={'video_id':'VIDEO_001','vault':str(vault),'created':created,'existing_preserved':preserved,'metrics':stats,
    'sources':[s['path'] for s in sources],'obsidian_desktop_required_for_filesystem':False,'rest_mcp_connected':False}
out=DATA/'verification/second-brain-v022';out.mkdir(parents=True,exist_ok=True)
(out/'starter-vault.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof))
