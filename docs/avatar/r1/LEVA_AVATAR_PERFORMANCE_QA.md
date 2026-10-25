# Performa dan validasi — R1 / 0.40.0

610 tes aplikasi dijalankan, 1 skip khusus engine gambar; 12 skrip JS dan 102 frozen/package checks lulus. Profil render/physics berubah nyata: Premium 60/60, Balanced 30/30, Gaming 30/15, Eco 15/10. Toggle off teramati 0 Hz dan physics time 0.00 ms.

Window pendek teramati: Premium p95 16.8 ms; Balanced 33.4 ms; Gaming 33.5 ms; Eco 66.8 ms. Sampel lengkap di verification-summary.json. RTX5070 teramati; request4050 masih mismatch. UV tidak diubah. Sampel tanpa LLM, bukan stress test, sertifikasi 60 FPS, atau bukti Android fisik.

Buffer timing memakai ring Float32Array 120 sampel dan bobot controller dipakai ulang. Adaptive automatic quality belum diimplementasikan. Source collision, long session, game concurrency dan precise VRAM attribution masih pending.

Kandidat R1 0.40.0; model Leva asli. Sumber tidak ditulis ulang. Penilaian visual pengguna masih PENDING. Bukti di `verification/leva-premium-avatar-r1` pada penyimpanan lokal; ringkasan yang aman dipublikasikan ada di verification-summary.json.
