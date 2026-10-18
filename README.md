# Leva — Personal AI Assistant

Leva Desktop **0.3.0** adalah prototipe asisten Windows berbahasa Indonesia. Repository ini berisi source aplikasi dan eksperimen. Model AI, API key, data pribadi, arsip suara dan executable tidak disertakan.

## Kemampuan saat ini

- Chat teks online-first melalui Google Gemini, dengan fallback kuota/batas laju yang didukung ke model lokal.
- Inferensi lokal diprioritaskan pada RTX 4050; pilihan dua GPU RTX 4050 + RTX 5070 masih spesifik untuk konfigurasi yang diuji.
- Pemilihan profil Chrome nyata dan dispatch pembukaan Chrome/YouTube melalui parser perintah lokal.
- Jeda, aktifkan kembali, serta jadwal istirahat Leva selama aplikasi berjalan.
- Neural Voice melalui Google Live: capture dan playback bersamaan, interupsi, transkrip dan animasi neural prosedural.
- Pengaturan tersimpan, alias profil yang ditentukan pengguna, serta hitungan kebiasaan yang menawarkan profil dan menunggu konfirmasi.
- Status sistem, mode animasi hemat dan pembersihan konteks percakapan.

Identitas profil/login/isi halaman belum diverifikasi dari dalam browser. Deteksi jendela baru adalah bukti dispatch terbatas. Model percakapan tidak diberi akses shell atau tools komputer bebas.

## Menjalankan source

Diperlukan Windows 10/11 dan Python 3.12 dengan Tkinter. Jalankan dari root repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B app\main.py
```

Runtime Google saat ini dikonfigurasi memakai `gemini-3.5-flash-lite` untuk teks dan `gemini-3.8-live` untuk suara. Ketersediaan model dan kuota mengikuti akun. Repository ini tidak mengaktifkan billing.

Sediakan key sendiri melalui environment **GEMINI_API_KEY**, atau file lokal `API Key.txt` yang diabaikan Git. Jangan memasukkan credential ke source atau commit.

Konfigurasi lokal opsional:

| Environment | Fungsi |
| --- | --- |
| `LEVA_DATA_DIR` | Folder data/log/preferensi; default `%LOCALAPPDATA%/Leva` |
| `LEVA_LOCAL_SERVER` | Path lengkap `llama-server.exe` dari runtime llama.cpp yang mendukung model |
| `LEVA_LOCAL_MODEL` | Path lengkap model GGUF yang kompatibel |

Atur environment tersebut sebelum membuka aplikasi. Untuk hasil pengujian lokal awal, model yang digunakan adalah Qwen3.5-4B Q8_0. Deteksi GPU saat ini mengharapkan nama perangkat RTX 4050 dan, bila opsi dua GPU dipilih, RTX 5070; perangkat lain memerlukan penyesuaian adapter pemilihan GPU. Tidak ada jaminan performa lintas perangkat dari source snapshot ini.

## Neural Voice

Klik **Neural Voice**, pilih mikrofon/headset dan suara, lalu klik **Mulai suara · Google**. Saat sesi aktif, audio mikrofon dikirim ke Google. Mikrofon awalnya mati dan tidak diaktifkan ulang otomatis setelah error/restart. Sesi dibatasi 15 menit. Gunakan headset karena AEC speaker belum diimplementasikan.

Perintah desktop dari transkrip dapat ditinjau lewat tombol. Opsi perintah langsung berawalan Leva default nonaktif dan kembali nonaktif saat sesi berakhir. Dukungan intent masih terbatas. Animasi pratinjau dapat dilihat tanpa membuka mikrofon; level pada pratinjau disimulasikan.

## Pengaturan dan memori

Klik **Pengaturan** untuk memilih provider, dua GPU dan mode animasi, menetapkan alias profil, melihat/menghapus hitungan kebiasaan, atau memeriksa status lokal. Database preferensi tidak berisi audio, API key atau isi chat. Chat tetap berada dalam konteks sesi yang dibatasi.

Kebiasaan dicatat setelah permintaan pembukaan dikirim dan jendela baru terdeteksi. Profil dominan dengan minimal tiga penggunaan ditawarkan sebagai pertanyaan; pembukaan tetap menunggu konfirmasi. Ini agregasi penggunaan, bukan training model. Profil yang disebut eksplisit mengungguli kebiasaan.

## Pengujian

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s experiments -p 'test_*.py' -q
.\.venv\Scripts\python.exe -B -m unittest discover -s app -p 'test_*.py' -q
```

Snapshot 0.3 memiliki **99 tests** (61 eksperimen, 38 aplikasi). Tests memakai fixture/mocks/database sementara dan child process sintetis. Tidak membutuhkan API key/model, tidak merekam mikrofon dan tidak membuka browser. Pengujian Job Object memerlukan Windows.

## Build opsional

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name Leva --paths app --paths experiments --distpath program app\main.py
```

Tutup Leva sebelum mengganti hasil build. Pertahankan seluruh folder `program/Leva`, termasuk `_internal`, di bawah root repository yang memiliki marker `LEVA_PROJECT.json`. Executable ini belum merupakan installer umum. Untuk membuat GIF pratinjau opsional, pasang `requirements-preview.txt` dan jalankan `app/render_voice_preview.py`.

## Batas pengembangan

Suara Shiroko/RVC, duplex lokal dengan micro-turn/LoRA, fallback suara offline otomatis, AEC speaker, autostart/tray, pemulihan kelompok tab, penelusuran web nyata, skip iklan, kontrol Discord/game dan WhatsApp belum tersedia. Modul relevansi sumber di experiments bekerja pada fixture, bukan hasil pencarian web langsung.

Snapshot ini diekspor dari workspace pengembangan. Lokasi model/data pribadi diganti konfigurasi environment; arsip suara, API key, database kebiasaan, log, rekaman dan build lokal dikecualikan. Jangan menganggap folder kerja pribadi aman untuk ditambahkan seluruhnya dengan git add.
