# Memakai dan melanjutkan Leva Live2D R0.1

## Kandidat lokal

Executable terpisah: `D:\AI\AI Lokal Asisten\Leva\program\0.42.0\Leva\Leva.exe`.

Pada ruang **Leva ♡**, perluas **Leva ♡ · pratinjau VTuber & model eksperimen**. Pilih **2D native · Cubism lokal**, lalu **Leva 2D · rig awal R02 · miring kepala & poni** pada Model Live2D. Pilihan sumber tetap tersedia sebagai **Leva GFL2 SSR · Live2D cerita · rig terbatas**. Simpan opsi bila ingin menerapkannya; build ini tidak mengganti preferensi produksi secara otomatis.

SDK dan aset hanya tersedia di laptop pengguna. Salinan repository tanpa SDK/model akan menampilkan ketersediaan yang sesuai; tidak mengunduh atau menyamarkan model contoh menjadi Leva.

## Proyek editabel privat

Folder: `D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D\Leva_Editable_R01`.

- `Leva_SSR_recovered_r01.aom`: baseline pemulihan yang telah dibuka ulang.
- `Leva_SSR_initial_rig_r02c.aom`: fork rig yang lulus pemeriksaan posisi wajah dan ekspor MOC3.
- `Leva_AI_Fringe_R02b.physics3.json`: preset eksternal yang dapat diedit; tidak mengaku berasal dari model game.
- `runtime_roundtrip`: ekspor baseline untuk pembanding.
- `runtime_initial_rig_r02c`: ekspor rig yang didaftarkan pada aplikasi.

File R02/R02b tanpa akhiran c adalah kandidat ditolak. Jangan memilihnya sebagai hasil akhir. CMO3 belum tersedia karena kegagalan validasi penulis editor.

## Jalur reproduksi

Ayatsuri2D 0.5.8 portable diperlukan untuk impor/ekspor GUI; Python `msgpack` hanya diperlukan oleh skrip authoring, bukan oleh aplikasi Leva. Gunakan environment kerja terpisah bila memasang dependensi tambahan.

1. Buka salinan model3 di Ayatsuri, Save As ke AOM baru. Buka ulang dan periksa bentuk serta parameter.
2. Jalankan `experiments/prepare_leva_live2d_rig_r02.py --input <baseline.aom> --output <fork-baru.aom>`. Skrip menolak overwrite.
3. Buka fork tersebut di Ayatsuri, ekspor MOC3 5.0 ke folder baru. Jangan menimpa folder sumber.
4. Tinjau `experiments/attach_leva_live2d_rig_r02_physics.py` bila mengubah lokasi. Skrip ini memakai path kandidat privat yang tercatat; jangan dijalankan ulang tanpa meninjau file yang sudah ada.
5. Preview baseline: `python experiments/preview_live2d_roundtrip.py --out <folder-QA-privat>`.
6. Preview rig: tambahkan `--initial-rig`; port loopback 20293, tanpa model AI atau mikrofon. Bootstrap pairing ditulis ke `fixture-url.txt`; jangan membagikan file/token itu.
7. Rekam ekspresi, kepala, poni dan suara yang benar-benar diputar; periksa video/frame serta metrik sebelum memperbarui hash manifest kandidat.

Mengganti ke renderer **3D · VRM** mengembalikan jalur 3D. Kedua aset tidak saling menimpa. Profil render Eco tersedia untuk preview saat laptop ditinggal; hentikan fixture dengan file `stop-fixture` pada folder QA.
