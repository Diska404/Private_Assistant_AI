import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from chat_service import ChatService
from speech_translation import translate_speech
OUT=Path(r'D:/AI/AI Lokal Asisten/Leva/verification/conversation-reliability-v029')
text="""Raizei, kita bisa membagi pekerjaan ini menjadi beberapa langkah. Pertama, periksa bahan yang tersedia, lalu susun rencana yang sesuai dengan tujuanmu. Jika ada bagian yang belum jelas, aku akan menjelaskannya sebelum melanjutkan. Setelah pekerjaan selesai, kita periksa hasilnya bersama. Kamu boleh menyela penjelasanku kapan saja tanpa harus menunggu sampai kalimat terakhir. Teks jawaban tetap tersedia walaupun suara dihentikan. Untuk tugas pemrograman, aku perlu membaca keluaran pengujian dan memperbaiki kesalahan yang benar-benar ditemukan. Aku tidak akan menyebut pekerjaan selesai hanya karena perintah sudah dikirim. Informasi dari halaman web juga perlu dibandingkan dengan sumber yang relevan. Untuk percakapan santai, kita bisa berbicara lebih pelan dan membahas hal yang sedang kamu pikirkan. Tidak semua pertanyaan memerlukan kendali laptop. Kita bisa tetap mengobrol tanpa membuka program atau mengubah berkas. Jika nanti kamu ingin melanjutkan tugas yang tertunda, tujuan dan hasil sebelumnya perlu diperiksa kembali agar tidak mengulang langkah yang sudah berhasil."""
service=ChatService();began=time.perf_counter();events=[]
try:
 result=translate_speech(service,text,'gpu5070',progress=lambda p:events.append({**p,'elapsed_s':round(time.perf_counter()-began,3)}))
 report={**result,'input':text,'wall_s':round(time.perf_counter()-began,3),'progress':events,'gpu':'RTX 5070','purpose':'translate','microphone_opened':False,'speaker_opened':False}
 (OUT/'translation-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in report.items() if k not in ('text','input')},ensure_ascii=True),flush=True)
finally:service.cancel()
