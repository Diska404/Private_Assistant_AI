# Rambut, pita dan collision — R1 / 0.40.0

IMPLEMENTED: fixed-step source solver tetap bounded; kontrol enable/disable/reset, slow motion, dan pose freeze untuk QA. Transisi masuk/keluar gerakan uji memakai envelope 600 ms, sehingga tes tidak memulai ayunan lengan secara mendadak. Rekaman menoleh cepat memakai Leva sebenarnya.

KNOWN LIMIT: 0 collider pada sumber dan runtime; tidak menambahkan sphere/capsule, tidak mengganti stiffness/drag/weights atau menambah tulang pita. Tidak mengklaim hair-to-body collision maupun ribbon simulation baru. Source SpringBone tetap dapat menembus tubuh. Lihat videos/r1-fast-turn-source-physics.webm pada bukti lokal.

Kandidat R1 0.40.0; model Leva asli. Sumber tidak ditulis ulang. Penilaian visual pengguna masih PENDING. Bukti di `verification/leva-premium-avatar-r1` pada penyimpanan lokal; ringkasan yang aman dipublikasikan ada di verification-summary.json.
