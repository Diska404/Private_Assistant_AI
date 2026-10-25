# Kalibrasi ekspresi — R1 / 0.40.0

NaturalPerformance mencampur existing morph channels dengan profil soft smile, happy, laugh, curious, confused, thinking, shy, playful, sad, sleepy dan lainnya. Ini kombinasi bobot, bukan 16 morph baru. Unsupported surprised morph ditandai limited; tidak dipalsukan.

Transisi berbasis waktu, cooldown 350 ms, variasi interval blink, eyelid easing, pembagian kanal blink/emotion/mouth dan penurunan bobot mood ketika audio aktif tersedia. Dialog balasan dapat memberi tag konservatif melalui avatar_emotion.py. Tag berupa pattern rules, bukan neural training atau pemahaman emosi menyeluruh. Teks tidak disimpan pada hint.

QA: baseline dan R1 dibandingkan pada kamera/pose/light Default yang sama. 15 JS behavior checks meliputi frame-rate consistency, silence/cancel gates, blink bounds dan unsupported morph.

![Senyum dari rekaman](media/smile-frame.png)

Kandidat R1 0.40.0; model Leva asli. Sumber tidak ditulis ulang. Penilaian visual pengguna masih PENDING. Bukti di `verification/leva-premium-avatar-r1` pada penyimpanan lokal; ringkasan yang aman dipublikasikan ada di verification-summary.json.
