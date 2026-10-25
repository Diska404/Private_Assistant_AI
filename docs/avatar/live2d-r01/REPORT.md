# Leva 0.42.0 — Live2D R0.1 dan rig awal R02

Tanggal pemeriksaan: 26 Oktober 2026. Status: kandidat lokal yang sudah dirender, mempunyai proyek editabel dan bukti audio/video. Avatar VTuber premium lengkap belum selesai.

## Hasil yang benar-benar tersedia

Pencarian menemukan model Live2D **Leva GFL2 SSR**, `CHA_Levva_SSR_01`, pada [viewer komunitas GFL2](https://srpg-kr.github.io/live2d/) dan [repositori asetnya](https://github.com/srpg-kr/l2d-assets). Ini model ilustrasi cerita game dengan rig wajah terbatas. Pencarian belum membuktikan adanya unduhan fan rig Leva lengkap sekelas AAA. Tidak memakai image generation, menamai ulang Hiyori/AAA, atau merender VRM lalu mengakuinya sebagai artwork Live2D baru.

| Artefak | Bukti dan batas |
|---|---|
| Sumber Leva SSR | 19 berkas, 2.471.302 byte; moc3 630.336 byte, atlas 2048×2048, 12 ekspresi dan tiga motion mulut |
| Rig sumber | 32 parameter, 52 deformer, 35 mesh; tanpa parameter menoleh kepala dan tanpa physics3 |
| AOM hasil pemulihan | 2.072.914 byte; disimpan lalu dibuka kembali di Ayatsuri2D 0.5.8 |
| Ekspor ulang baseline | 19 berkas MOC3 5.0; berhasil dimuat di Cubism native Leva dengan 32 parameter/35 drawable |
| Fork rig R02c | 34 parameter, 54 deformer, 35 mesh; dua parameter baru untuk kemiringan kepala dan poni |
| Kemiringan kepala | Warp bertahap dengan batas desain sekitar ±4°, bukan rekonstruksi perspektif atau yaw |
| Poni | Deformer ringan dan preset Cubism physics dua partikel; output parameter berubah pada uji nyata |
| Tekstur | Atlas sumber dipertahankan byte demi byte. Tidak ada gambar baru atau pengecatan ulang |
| Pilihan aplikasi | Hiyori, Leva SSR sumber, dan Leva 2D rig awal R02 terpisah; pilihan produksi tidak diganti otomatis |

Model ditemukan pada sumber komunitas; lisensi open-source untuk artwork dan izin redistribusi/modifikasi belum terverifikasi. Aset asli, salinan editabel, runtime turunan, SDK dan media pemeriksaan disimpan privat. Repository publik hanya menerima kode, dokumentasi dan hasil agregat. Kontribusi rig baru tidak memindahkan kepemilikan artwork asli.

SHA-256 moc3 sumber: `7b2d62a785e646a63f27ad8ef47c3bee01598e804259b9c91c7412882c8d9cc7`.

SHA-256 atlas sumber: `bbd050ba45d64aa19f11a1cbce467cd31908510b73c469e790fb8130028987c1`.

## Pemulihan proyek dan kegagalan yang ditangani

Ayatsuri portable berasal dari rilis resmi v0.5.8; SHA-256 ZIP cocok dengan checksum rilis. Pengguna menyetujui peluncurannya. Model diimpor dari salinan privat dan AOM disimpan pada folder baru. AOM berhasil dibuka kembali dengan struktur rig yang sama.

Ekspor **CMO3 gagal**, karena pemeriksaan internal editor menolak `CPhysicsSettingsSourceSet.selectedCubismPhysics = null`, yang diharapkan berupa referensi `CPhysicsSettingsGuid`. Tidak ada klaim CMO3 sudah tersedia atau lolos Cubism Editor resmi. [Dokumentasi penulis Ayatsuri](https://ayatsuri-2d.org/docs/export/) memang menyebut penulis CMO3 masih memerlukan validasi dari Cubism Editor. AOM dan jalur MOC3 terbukti dapat dipakai.

Fork pertama ditolak eksportir karena parent deformer berada sesudah child. Hierarki kemudian diurutkan dan semua indeks dirujuk ulang. Pemeriksaan rekaman berikutnya menangkap wajah yang bergeser akibat normalisasi skala rotation deformer. R02c mempertahankan skala lokal rotasi dan memperbaiki hasil tersebut. Kandidat gagal dipertahankan sebagai bukti privat; tidak didaftarkan sebagai pilihan aplikasi.

Pemeriksaan video juga menemukan RGB transparan dari atlas muncul pada rekaman mentah. Decoder kini meminta `premultiplyAlpha` secara eksplisit untuk ImageBitmap, sesuai [aturan WebGL](https://registry.khronos.org/webgl/specs/latest/1.0/). Perekam mengomposisikan avatar ke latar opaque sebelum encoding video. Rekaman akhir diperiksa kembali; garis putih pada rekaman mentah sebelumnya tidak terlihat pada frame akhir. Atlas tidak diedit.

## Integrasi dan pengukuran

Renderer memuat model3/moc3, atlas, resep ekspresi, dan physics melalui rute terautentikasi. Setiap anggota manifest harus memiliki hash yang sesuai dan tetap berada pada root model yang ditetapkan. Tidak ada pembacaan path arbitrer. Profile reaksi R2 dipetakan ke ekspresi sumber; 24 profile aplikasi bukan 24 ekspresi artwork baru.

Framing memakai batas mesh yang benar-benar terlihat, sehingga sumber Leva tidak mengikuti asumsi origin Hiyori. Kontrol 3D yang tidak relevan dinonaktifkan. Parameter kemiringan kepala, fisika tersedia/tidak, identitas model dan GPU aktual masuk ke metrik.

| Window pengukuran | Hasil |
|---|---|
| Leva sumber, 1232×432, 240 sampel | 60,00 FPS rata-rata; frame p95 16,7 ms; tanpa solver karena sumber tidak mempunyai physics |
| Rig R02c, 1232×432, 240 sampel | Sekitar 60,00 FPS; frame p95 16,8 ms; physics p95 0,1 ms pada solver 60 Hz |
| Rig terdaftar `leva_rig_r02`, 1745×727, 240 sampel akhir | 59,30 FPS; frame p95 18,3 ms, p99 24,2 ms; dua frame >25 ms; physics p95 0,1 ms |
| Identitas perangkat renderer | RTX 5070 teramati oleh WebGL; permintaan RTX 4050 belum cocok |
| Rekaman final | Target rekaman 30 FPS terpisah dari render target 60; FPS aktual dicatat di `verification-summary.json` |

Angka tersebut window pendek pada laptop yang tetap menjalankan aplikasi pengguna, bukan perbandingan terkontrol atau jaminan 60 FPS terkunci. Ukuran framebuffer berbeda; tabel tidak digunakan untuk menyimpulkan rig lebih cepat/lambat dari sumber. 120 FPS tersedia sebagai target pengaturan, tetapi belum disertifikasi pada rig Leva 2D ini. Pembagian render RTX 4050 dan inferensi RTX 5070 belum terbukti.

## Suara, ekspresi dan Stop

Uji memakai WAV Jepang Leva A yang sudah tersedia, bukan inferensi TTS baru. Audio diputar melalui jalur RemoteVoice/WebBridge yang sama dengan aplikasi. Video akhir sekitar 12 detik menyertakan suara, gerak kepala/poni dan pergantian empat ekspresi QA. Status speaking dan interrupted diamati. Setelah Stop dan keadaan stabil, `ParamMouthOpenY` kembali 0. Snapshot metrik tepat setelah klik bisa masih berisi sampel sebelum Stop; tidak dipakai sebagai ukuran latensi interupsi.

Video QA tidak membuktikan model bahasa memilih ekspresi secara kontekstual, akurasi STT, latensi sintesis suara, acoustic echo cancellation, atau interupsi mikrofon otomatis. Tidak membuka mikrofon/kamera. Android fisik dan pemuatan kandidat ini di VTube Studio belum diuji pada tahap ini. Paket VTS sumber sudah disiapkan privat; native web berjalan tanpa VTS/API.

## Validasi perangkat lunak

- 622 tes Python pada DATA terisolasi: 0 gagal/error, satu skip yang memerlukan environment engine gambar.
- 17 skrip JavaScript, termasuk resource guard, ekspresi, alpha bitmap, perekaman opaque, dan cleanup lifecycle.
- 104 pemeriksaan executable; aset web disinkronkan dan hash dibandingkan dengan source.
- Build kandidat terpisah 0.42.0. Tidak menjalankan ulang aplikasi produksi, mengganti pilihan model/voice, mengubah UV/driver, me-reboot laptop, atau mengubah jaringan remote.

Hasil frozen, rekaman, matriks penerimaan dan batas disimpan bersama laporan. File model, SDK Core, token, audio dan tangkapan layar privat tidak masuk ke snapshot GitHub.

## Pekerjaan berikutnya untuk kualitas sekelas AAA

1. Pisahkan artwork kepala, leher, badan, rambut depan/samping/belakang dan pakaian menjadi layer yang memadai. Sumber saat ini menaruh sebagian besar badan/rambut pada satu gambar dasar.
2. Gambar area yang tertutup dan bentuk mata kiri yang diperlukan untuk pose netral dua mata. Pose sumber memang mengedip sebelah; slider tidak menciptakan artwork yang tidak ada.
3. Buat keyform yaw/pitch dan corrective bentuk wajah; periksa wajah pada semua kombinasi ekspresi, bukan hanya saat netral.
4. Tambahkan rantai rambut dan pakaian beserta pemeriksaan clipping. Fisika poni dua partikel bukan simulasi seluruh rambut/kostum.
5. Uji Cubism Editor/VTube Studio, Android fisik, beban bersama suara/LLM, durasi panjang, dan penilaian visual pengguna.

Rig R02c merupakan hasil awal yang dapat diedit dan diuji; belum avatar premium lengkap. Versi 3D R2 dan eksperimen suara sebelumnya tetap terpisah dan dipertahankan.
