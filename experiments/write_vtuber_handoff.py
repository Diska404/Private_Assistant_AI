"""Build evidence-linked reports from completed, local synthetic trials."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app')]
from model_registry import REGISTRY
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
def load(name):return json.loads((OUT/name).read_text('utf8'))
def main():
 summary=load('summary.json');bench=load('benchmark-status.json');assets=load('acquisition.json');tools=load('tool-qualification.json');app=load('app-adapter.json')
 if not all(v['status']=='completed' for v in (bench,tools,app)):raise RuntimeError('incomplete_evidence')
 # Models rejected at the proposal gate never start another child.
 if not all(m.get('owned_worker_released') or m.get('reason')=='native_proposal_gate_failed' for m in bench['models']+tools['models']+app['models']+app['gpu_smoke']):raise RuntimeError('owned_worker_not_released')
 registry=json.loads(REGISTRY.read_text('utf8'))
 ratings={'hauhau_qwen35_4b':{'chat':'recommended','secret':'recommended','companion_avatar':'recommended'},
  'hauhau_qwen35_9b':{'chat':'recommended','secret':'balanced','companion_avatar':'balanced'},
  'rocinante_x_12b':{'chat':'balanced','secret':'discouraged','companion_avatar':'discouraged'}}
 for key,row in registry['models'].items():
  row.update(context_tested=8192,ratings=ratings[key],tool_policy='none',not_default=True,
    evidence='vtuber-model-trial-20261024',agent_fixture_gate=next(m['status'] for m in tools['models'] if m['id']==key))
 REGISTRY.write_text(json.dumps(registry,indent=2),encoding='utf8')
 rows=[]
 for m in summary['models']:
  for mode,r in m['modes'].items():
   rows.append(f"| {m['id']} | {mode} | {r['all_checks_pass']}/{r['n']} | {r['ttft_ms'].get('median')} / {r['ttft_ms'].get('p95')} | {r['tokens_per_second'].get('median')} | {r['total_ms'].get('median')} | {r['length_stops']} |")
 table='| Model | Mode | Kasus lolos semua check | TTFT median / p95 ms | Median tok/s | Total median ms | Batas 256 token tercapai |\n|---|---|---:|---:|---:|---:|---:|\n'+'\n'.join(rows)
 provenance=[]
 for a in assets['assets']:
  provenance.append(f"### {a['repo']}\n\n- Revision: `{a['revision']}`\n- File: `{a['name']}`\n- Bytes: {a['bytes']}\n- SHA-256: `{a['local_sha256']}`\n- Sumber: https://huggingface.co/{a['repo']}\n- Path lokal: `{a['path']}`\n")
 gpu='| Rute 4B | Sampel | TTFT median / p95 ms | Total median ms | Median tok/s | Buffer bobot MiB |\n|---|---:|---:|---:|---:|---|\n'
 for r in app['gpu_smoke']:
  gpu+=f"| {r['mode']} | {len(r['samples'])} | {r.get('ttft_ms',{}).get('median')} / {r.get('ttft_ms',{}).get('p95')} | {r.get('total_ms',{}).get('median')} | {r.get('tokens_per_second',{}).get('median')} | {r.get('gpu_buffers_mib',r.get('error'))} |\n"
 evidence=f"Bukti mentah tersimpan di `{OUT}`. Dataset ini seluruhnya sintetis; percakapan, credential dan rekaman pengguna tidak dipakai. `model-trial-report.html` dapat dibuka offline; paket blind review tersedia, tetapi belum dinilai oleh manusia independen."
 def write(path,text):
  target=ROOT/'docs'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text.strip()+'\n',encoding='utf8')
 write('evaluation/LEVA_MODEL_TRIAL_FEASIBILITY.md',f'''# Kelayakan trial Leva · 24 Oktober 2026

Workspace aktual: `{ROOT}`. Versi awal 0.34.1; hasil pengembangan 0.35.0. Root source tidak memiliki `.git`. Folder `github-export` adalah checkout terpisah, branch `main`, commit `910d5952fdede6642ed80fa7ddd49f9de741889a`; tetap bersih dan tidak di-push. Source publik bukan acuan versi runtime.

Checkpoint sebelum perubahan: `source-before.zip` dalam folder bukti. Seluruh 39 dokumen paket terbaru dibaca; file 31–38 menjadi prioritas. Hash empat ZIP dan pemeriksaan 38 hash internal tersedia di `references/VTUBER_BLUEPRINT_20261024/SOURCE.json` dan `blueprint-integrity.json`.

RTX 4050 laptop 6141 MiB, RTX 5070 12227 MiB, RAM 64 GB. Awal audit menunjukkan GPU memakai sekitar 258/2185 MiB; angka ini merupakan observasi sesi, bukan boot idle terkontrol. D tersedia sekitar 5.92 GiB sehingga dua file baru ditempatkan di Y. Rocinante Q4 yang sudah ada dipakai kembali. Jaringan WinRT teramati Unrestricted; roaming/over-limit/approaching-limit false. Unduhan serial dibatasi 6 MiB/detik, resume, hash penuh sebelum rename. Tidak ada model vision/mmproj baru atau skrip repo model yang dijalankan.

Tidak ada reboot, perubahan driver/UV, firewall, Tailscale, akun, startup Windows atau penghentian layanan remote. Normal GUI tidak dinyalakan; pengujian Tk memakai fixture tersembunyi. {evidence}''')
 write('evaluation/MODEL_ASSET_PROVENANCE.md','# Provenance aset model\n\n'+'\n'.join(provenance)+'''
HauhauCS 4B/9B: model card menyatakan Apache-2.0. Rocinante: publisher dan quantizer tidak memberikan field lisensi eksplisit pada metadata yang diperiksa; base model yang disebut adalah Mistral-Nemo-Instruct-2407. Lisensi turunan/redistribusi belum dipastikan. Tidak ada bobot model yang dibundel atau diterbitkan ulang. Label uncensored bukan izin alat OS atau kebijakan keamanan baru.

Manifest terverifikasi disimpan sebagai data lokal di `model-trial-registry.json`, di luar source. Status awal semua model experimental dan not_default; pemilihan produksi tidak berubah.''')
 write('evaluation/MODEL_RUNTIME_COMPATIBILITY.md',f'''# Kompatibilitas runtime

Ketiga model benar-benar dimuat dan menghasilkan teks pada llama.cpp b11721 CUDA 13.4, RTX 5070, context 8192, KV q8_0, non-thinking. File GGUF dan tensor descriptor dibaca tanpa menjalankan kode publisher. Metadata dan template yang benar-benar dipakai server disimpan di `gguf-inspection.json` dan tiga `*-template.json`.

Qwen memakai template metadata Qwen3.5 dengan `enable_thinking=false`. Rocinante memakai template bawaan GGUF Mistral/Tekken; tidak ditumpuk dengan format Metharme atau tag SYSTEM_PROMPT manual. Text inference berhasil; tool-native Rocinante gagal dalam dua proposal, sehingga template teks yang bisa berjalan tidak dianggap bukti dukungan agent.

Qwen 4B/9B: native proposal 2/2, core harness 9/9 tujuan per model (3 tugas × 3 trial). Browser/jam merupakan fixture; tulis dan baca berkas benar-benar terjadi di folder verification. Tidak menguji pengendalian browser pengguna. Cancellation mematikan child milik eksperimen dan menghentikan thread request: sekitar 346 ms untuk 4B dan 571 ms untuk 9B. Ini bukan benchmark interruption audio.

Adapter aplikasi dengan persona produksi diuji lima balasan per model: semua berhasil menyebut identitas Leva dan mengingat kode fixture. Semua worker dilepas. Uji awal adapter menemukan import Path hilang; diperbaiki, ditambah regresi, lalu uji asli diulang. Bukti gagal awal dipertahankan sebagai `app-adapter-first-run.json`.

{gpu}

Rute dual menunjukkan buffer pada CUDA0 dan CUDA1; jalur tunggal hanya satu buffer GPU. Dalam uji singkat yang sama, 5070 tunggal lebih cepat daripada split. Tidak menyimpulkan semua model atau semua beban lebih cepat pada satu GPU. GPU UUID/mapping asli ada dalam `app-adapter.json`.
''')
 write('evaluation/LEVA_THREE_MODEL_BENCHMARK_REPORT.md',f'''# Benchmark tiga model Q4_K_M

48 fixture berbeda, empat mode × 12 kasus, masing-masing diulang 3 kali untuk tiap model: 432 respons. Tambahan tiga sesi 40 turn per model: 360 respons. Ada 6 proposal alat native terpisah. Urutan model diacak deterministik, eksekusi serial. Sampling .25 untuk Asisten/Chat, .7 untuk Secret/Companion, top_p .8, top_k 20. Satu persona sintetis sama untuk semua. Dataset diadaptasi dari cakupan dokumen 33; bukan benchmark umum kecerdasan.

{table}

TTFT adalah first content token dari HTTP streaming ke server yang sudah dimuat. Token/s adalah nilai generated token server, bukan kata/detik. Sampel first-request model dikeluarkan dari perhitungan TTFT; tiap mode masih memiliki 35–36 sampel. P95 memakai nearest-rank, bukan confidence interval. Total ms mencakup jawaban dengan panjang berbeda. Download selesai sebelum pengukuran; browser preview sempat berjalan selama sebagian pengujian, sehingga resource sistem bukan isolasi laboratorium sempurna.

Ketiga model menyelesaikan baseline tanpa transport error atau OOM. Output yang mencapai batas 256 token tetap dihitung sebagai truncation, bukan jawaban lengkap. Nilai check berbasis schema, hasil fungsi matematika terbatas, kata, panjang dan beberapa fakta; **tidak membuktikan naturalitas, akurasi umum, atau keberhasilan tugas PC**.

Review editorial terbatas oleh Codex menemukan angka desimal 9B benar namun alasan posisi angkanya keliru; pemeriksa otomatis tidak menangkapnya. 4B sesekali menyalin frasa “Namamu Leva” dari persona minimal dan kurang presisi memberi API SQLite; persona aplikasi menyebut nama dengan benar. Rocinante beberapa kali beralih ke bahasa Inggris, mengulang batas persona, dan lemah pada recall. Beberapa check kata dapat menolak parafrasa yang sebenarnya benar. Ketiga model masih memerlukan validasi makna dan host sanitizer sebelum suara.

Skor gabungan 0–100 dengan bobot dokumen 35 **belum diberikan**: dimensi naturalitas/kreativitas belum dinilai manusia independen. Tidak dibuat confidence interval atau juara kualitas palsu. Chat 4B vs 9B: TIE / NEED_MORE_TESTS untuk kualitas umum. Rekomendasi kecepatan companion mempunyai bukti hardware lebih kuat.

{evidence}
''')
 write('evaluation/LEVA_PERSONA_CONSISTENCY_REPORT.md',f'''# Konsistensi persona

Tiga sesi 40 turn setiap model memakai nama fixture Raka, minuman teh melati, proyek Langit, koreksi panggilan Kak Raka dan kutipan instruksi tak tepercaya. Lima probe terarah per sesi menghasilkan 15 probe/model: 4B 15/15, 9B 15/15, Rocinante 8/15. Seluruh jawaban tersedia di `benchmark-status.json`; ini recall/identitas terarah, bukan skor seluruh kualitas dialog.

Adapter persona produksi juga diuji terpisah, lima turn/model, termasuk kode KUPU-24 dan batas tools. Semua lulus smoke identitas/recall. 4B mempertahankan nada singkat dan cepat; 9B lebih panjang dan kadang terlalu banyak panggilan/emoji; Rocinante masih canggung pada sebagian bahasa Indonesia. Penilaian ini editorial Codex, bukan blind review manusia.

Mode companion menggunakan service/history sendiri, maksimal 80 pesan/18.000 karakter, hanya di RAM selama sesi; mode Chat/Secret dan basis data persisten dipertahankan. History diteruskan sampai worker, bukan hanya disimpan pada widget. Ini jendela konteks terbatas, bukan ingatan tak terbatas. Memori privat tidak disalin otomatis. Kamera tidak dinyalakan. Tidak ada klaim bahwa persona adalah manusia atau karakter resmi game.

{evidence}''')
 write('evaluation/LEVA_MODE_MODEL_ROUTING_DECISION.md','''# Keputusan routing

| Mode | Keputusan saat ini | Pilihan trial | Alasan dan batas |
|---|---|---|---|
| Asisten | Pertahankan binding produksi | 4B/9B lulus fixture terbatas; agent eksperimen belum diaktifkan | 9/9 fixture bukan bukti kendali semua aplikasi; trial tetap tanpa tools dalam aplikasi |
| Chat | Default pengguna dipertahankan | 4B dan 9B direkomendasikan; kualitas umum TIE | Keduanya 36/36 check Chat; 9B dapat lebih terperinci, 4B lebih cepat; bukan pembuktian reasoning kompleks |
| Secret ♡ | Default pengguna dipertahankan | 4B direkomendasikan, 9B seimbang, Rocinante tidak direkomendasikan | Kecepatan, scope dan recall lebih kuat pada Qwen dalam suite ini |
| Leva ♡ avatar | Feature off; ketika diaktifkan tetap model existing qwen4b | Hauhau4B direkomendasikan; 9B seimbang; Rocinante tidak direkomendasikan | 4B latency/throughput cocok companion; kualitas gaya masih perlu pendengaran/pilihan pengguna |

“Seimbang” Rocinante pada Chat adalah pilihan kreatif eksperimen, bukan rekomendasi teknis umum. Tidak ada default produksi yang ditukar diam-diam.

Registry memvalidasi ID, quant, nama file, size dan SHA sebelum loading. Kehilangan file atau perubahan hash menjadi error eksplisit; tidak beralih ke cloud. UI memerlukan opt-in model eksperimen sebelum menyimpan atau menjalankan pilihan tersebut. Menonaktifkannya mempertahankan pilihan tersimpan dalam tampilan tetapi memblokir eksekusi. Worker juga menolak peningkatan trial menjadi agent, termasuk reuse session. Emosi/persona tidak menambah hak alat. Receipt model mencantumkan selected_model, provider local, experimental, tool_policy dan context_tested; tidak mencatat prompt pribadi.

RTX 5070 tunggal adalah rekomendasi respons cepat 4B pada pengukuran ini. Dual tetap tersedia dan terbukti memakai dua GPU, tetapi tidak menjadi default kecepatan. Voice engine/ASR tetap pada pengaturan pengguna; tidak diload bersamaan dalam benchmark ini.''')
 write('roadmap/LEVA_CURRENT_STATE.md',f'''# Kondisi aktual Leva 0.35.0

Source lokal berkembang dari 0.34.1; export GitHub terpisah tidak diubah. Asisten, Chat, Secret, voice pack, Obsidian, alat aplikasi/browser/terminal, workflow gambar dan jalur Android dipertahankan. Paket 0.35.0 berada di `D:\\AI\\AI Lokal Asisten\\Leva\\program\\0.35.0\\Leva\\Leva.exe`, terpisah dari 0.34.1; normal GUI tidak dijalankan otomatis.

Tambahan: companion avatar opt-in, placeholder orisinal responsif, registry lokal tiga model, batas memori/alat, event generation cancellation dan laporan benchmark. Integrasi ini merupakan langkah pertama VTuber; belum avatar karakter Leva final. Tidak ada pelatihan model, modifikasi suara, atau perubahan konfigurasi produksi.

```mermaid
flowchart TD
 UI[Desktop / Web / Android] --> B[Workspace boundary]
 B --> A[Asisten existing: executor dan receipt]
 B --> C[Chat / Secret / Companion: tanpa executor]
 C --> H[ChatService: history dan cancellation]
 H --> R[Registry trial: file, SHA, status eksperimen]
 R --> L[LocalEngine: satu model / GPU route pilihan]
 H --> T[TTS existing di laptop]
 T --> V[RemoteVoice: playback PCM browser]
 V --> P[PlaceholderAvatar: mouth envelope]
 B --> D[AvatarDirector: state, generation, TTL]
 D --> P
```

{evidence}''')
 write('roadmap/LEVA_COMPANION_IMPLEMENTATION_STATUS.md','''# Status implementasi companion

| Bagian | Status | Bukti / batas |
|---|---|---|
| Ruang keempat desktop/web | PASS | Flag default off, label editable, tab native dan web; tombol desktop membuka panggung web |
| Placeholder offline | PASS | Canvas orisinal, blink/breath, mulut amplitude envelope, quality target, dispose ketika tidak aktif |
| State/cancellation | PASS terbatas | idle/listening/thinking/speaking/interrupted/sleeping/error, generation, enum, TTL ekspresi dan late-event rejection |
| Mic dan memori | PASS unit/fixture | Tidak auto mic pada companion; mic HP tetap tekan-tahan; riwayat hanya sesi; maksimum 80 pesan/18K karakter |
| Lip sync audio browser | PASS unit | RMS dari PCM yang benar-benar diputar browser, nol bila stop/mute; bukan viseme fonetik |
| Avatar desktop native | SEBAGIAN | Native punya ruang/kontrol dan membuka panggung web; renderer belum tertanam dalam Tk |
| Reaksi emosi dari dialog nyata | BELUM | Kontrak enum tersedia; demo simulasi terpisah; belum pemetaan emosi LLM produksi |
| VRM/Live2D | BLOCKED aset + implementasi renderer | Provider stub menolak load secara jelas; bukan integrasi selesai |
| Voice+avatar+ASR serentak | NOT TESTED | Tidak mengklaim duplex, gema/AEC atau latensi ujung-ke-ujung sudah beres |
| OBS/VTuber live dan mocap | BELUM | Tidak memasang virtual camera, capture webcam, atau streaming otomatis |
| Persist memori companion opsional | BELUM | Default hanya sesi; belum UI retensi/ekspor memori permanen |

Uji lifecycle sintetis 50 mount/unmount meninggalkan nol observer/listener/rAF. Screenshot desktop dan viewport 390 px diperiksa; bukan uji Android fisik. Browser preview teramati dapat diturunkan ke sekitar 1 FPS saat dibatasi browser host; target 30/60 FPS bukan klaim performa tercapai. Mouth envelope pada suara nyata dan penilaian manusia tetap dibutuhkan.''')
 write('roadmap/LEVA_AVATAR_ASSET_STATUS.md','''# Status aset avatar

Paket blueprint tidak membawa aset VRM/Live2D Leva yang disertai hak pakai memadai. Referensi karakter/VRoid pada dokumen tidak dianggap izin untuk memodifikasi atau mendistribusikan. Tidak ada avatar final yang diunduh atau dipaketkan.

Placeholder saat ini digambar melalui kode Canvas orisinal, bukan karakter Leva GFL2 resmi. Aset final memerlukan file beserta sumber/lisensi penggunaan, kemudian pemeriksaan ukuran, mesh/material, ekspresi, spring bones, mobile budget dan bundling renderer. VRM dan Live2D masing-masing mempunyai kebutuhan lisensi aset/runtime sendiri. Setelah tersedia, ukur load time, frame p95, pemakaian GPU dan mouth sync dengan suara Leva yang dipilih.''')
 write('roadmap/LEVA_CAPABILITY_INTEGRATION_MATRIX.md','''# Kandidat framework VTuber

| Kandidat | Sumber diaudit | Peran yang sesuai | Keputusan |
|---|---|---|---|
| AIRI | moeru-ai/airi, f1b81967f0d476eecf4e8848760f4de106310a9e | Acuan lifecycle avatar, state, companion desktop/web | Dokumentasi, tree, LICENSE disimpan; framework tidak diinstal/dijalankan |
| Open-LLM-VTuber | Open-LLM-VTuber/Open-LLM-VTuber, 992309c0aa19845960228f880013d4685fde93b5 | Referensi voice interruption dan integrasi Live2D | Dokumentasi/tree diaudit; runtime terpisah belum dibenchmark |
| three-vrm | pixiv/three-vrm, 3caf7a21ee68f0d5dfa363ab3d577450bbf60136 | Kandidat renderer VRM di panggung web Leva | Arah teknis utama untuk VRM setelah aset tersedia; belum dipasang atau diukur |

Ketiganya berbeda lapisan: dua aplikasi companion vs library renderer. Tidak ada klaim “paling cepat” dari audit README. Ketiga LICENSE perangkat lunak yang dibaca berisi MIT; Open-LLM-VTuber mengecualikan sample Live2D yang memiliki lisensi terpisah. Lisensi kode tidak otomatis berlaku untuk avatar/suara.

Sumber primer: [AIRI](https://github.com/moeru-ai/airi), [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber), [three-vrm](https://github.com/pixiv/three-vrm). Salinan audit berada di `D:\\AI\\AI Lokal Asisten\\Github\\VTuber-reference-audit\\20261024`; tidak ada skrip pihak ketiga yang dijalankan. Integrasi pola state dibuat sendiri dalam Leva; tidak mengaku seluruh framework sudah diintegrasikan.''')
 write('roadmap/LEVA_PERFORMANCE_BASELINE_AND_AFTER.md',f'''# Baseline dan batas perbandingan

Baseline inference tiga model: {table}

Uji hardware tambahan dengan 20 prompt identik per rute setelah warmup:

{gpu}

Tidak ada nilai before/after kualitas avatar yang valid karena versi sebelumnya belum mempunyai mode avatar. Optimasi 0.34.1 terdahulu tetap dipertahankan dan laporannya tidak ditimpa. Penggunaan RAM/GPU pada baseline adalah total sistem (display, proses remote dan aplikasi lain termasuk), bukan seluruhnya milik model.

Peak GPU total RTX 5070 sekitar 5539 MiB untuk 4B, 8708 MiB untuk 9B, 10392 MiB untuk Rocinante pada masing-masing run. Buffer bobot server berbeda: sekitar 2572/4810/6763 MiB. Peak suhu teramati hingga 70 C. Tidak mengubah UV/clock/power untuk mengejar angka ini.

Avatar/TTS/ASR belum dibenchmark serentak dengan model; hasil ini tidak menjamin target frame atau latensi audio. Jangan menggunakan angka TTFT sebagai waktu mulai suara.''')
 write('performance/LEVA_CLEAN_BOOT_READINESS_AND_POLICY.md','''# Kesiapan clean boot

Tidak ada reboot, clean-boot msconfig, pengubahan services/startup, registry Windows, Tailscale atau software remote. “Clean boot” pada paket diperlakukan sebagai pengukuran observasional setelah pengguna sendiri memutuskan restart.

Fitur avatar dan model trial default off, tidak prewarm tiga model, tidak mengaktifkan mic/kamera/OBS dari mode companion. Preferensi global existing seperti pendengar dan keep-warm tidak ditukar diam-diam. Kesiapan baru tidak berarti Leva lama seluruhnya bebas background load.

Paket 0.35.0 terpisah, rollback dengan kembali membuka 0.34.1 setelah menutup instance milik Leva. Data pengguna tidak dipulihkan dari source ZIP. Jangan menimpa database saat rollback. Menonaktifkan companion/model trial lewat pengaturan cukup untuk mengembalikan penggunaan ruang lama.''')
 write('performance/LEVA_BOOT_COLD_WARM_BENCHMARK.md','''# Boot, cold dan warm

BOOT_IDLE setelah restart: **NOT TESTED**. COLD_APP sesudah reboot: **NOT TESTED**. Angka load server 2.1–3.7 detik berasal dari worker baru pada sesi Windows berjalan; cache OS mungkin hangat. Tidak menyebutnya cold boot.

Warm inference: tersedia 35–36 TTFT per mode/model, plus 20 sampel per rute GPU Qwen 4B. Frame p95 placeholder ditampilkan dari browser aktual, tetapi host browser dapat throttle tab; tidak menjadi pembanding GPU/native renderer. Tidak mengukur power/battery/fan atau frame game.

Untuk audit pascarestart nanti: pengguna menyalakan ulang secara manual; baca-only sampel BOOT_IDLE, APP_IDLE, first response, warm response dan release. Biarkan koneksi remote dan driver tetap. Simpan profile daya/UV aktual bersama sampel agar perbandingan bermakna.''')
 write('performance/LEVA_STARTUP_HOTSPOTS_AND_FIXES.md','''# Hotspot dan perubahan

Mode avatar dibuat lazy dan opt-in. Renderer dibuang saat ruang tidak aktif; timer draw berhenti pada dokumen tersembunyi/di luar viewport. Target default 30 FPS, performance 60 target, DPR dibatasi 2. Envelope mulut memakai buffer PCM yang sudah diputar; tidak membuka microphone atau memuat engine speech browser kedua.

Metadata/choices model mengikuti cache display tiga detik yang sudah ada; hash model dibaca sebelum pertama dipakai dalam worker dan dicache berdasarkan path, size dan mtime pada proses tersebut. Pembacaan hash penuh dapat menambah waktu awal aplikasi di luar angka load server.

Koreksi integrasi yang dibuktikan saat pengembangan: history companion diteruskan ke worker dan diperluas terbatas sampai 80 pesan; memilih model lalu menonaktifkan opt-in tidak merusak UI; policy model tetap ditolak saat reuse worker menjadi agent; tab Tk tersembunyi perlu state normal saat diaktifkan. Tidak membuat klaim penurunan startup tanpa baseline cold yang setara.''')
 # Test/release reports generated again after final regression/package verification.
 checks=load('regressions.json');package=load('packaged-check.json') if (OUT/'packaged-check.json').exists() else None
 js=load('javascript-tests.json')
 experiments=load('experiment-regressions.json') if (OUT/'experiment-regressions.json').exists() else {}
 write('roadmap/LEVA_TEST_EVIDENCE.md',f'''# Bukti pengujian

- Python: {checks['tests']} tes, success={checks['successful']}, skipped={len(checks['skipped'])}; DATA dialihkan sebelum import, database produksi tidak dibaca untuk fixture.
- Runtime/helper experiments: {experiments.get('tests','PENDING')} tes, successful={experiments.get('passed','PENDING')}; DATA terisolasi.
- JavaScript: {len(js)} skrip, seluruh exit_code nol={all(r['exit_code']==0 for r in js)}; lifecycle 50 siklus dan audio envelope memakai fake context, tanpa speaker.
- Baseline model: 432 respons single-turn + 360 respons dialog; tiga model completed dan worker dilepas.
- Native tool proposals: Qwen 2/2 per model; Rocinante 0/2. Core harness: Qwen 9/9 per model, tidak membuka browser nyata.
- Adapter aplikasi: 5 turn/model; tiga smoke identitas/recall berhasil. Tiga rute GPU 4B × 20 sampel.
- Frozen package: {package['passed'] if package else 'PENDING'} checks; aset web parity diperiksa byte-for-byte.
- Screenshot desktop dan viewport mobile disimpan di folder verification. Tidak menguji HP fisik, VRM/Live2D, camera, OBS atau duplex audio live.

File utama: regressions.json, javascript-tests.json, benchmark-status.json, summary.json, tool-qualification.json, app-adapter.json, packaged-check.json, source-diff.json dan system-final.json. Bukti gagal awal disimpan terpisah; laporan akhir memakai pengujian setelah koreksi.
''')
 write('evaluation/LEVA_MODEL_TRIAL_FINAL_HANDOFF.md',f'''# Handoff Leva 0.35.0 · VTuber preview dan tiga model

**Tersedia:** mode keempat companion opt-in pada desktop/web, placeholder orisinal, state + generation cancellation, demo/mouth amplitude dari audio browser, riwayat sesi terpisah, registry terverifikasi tiga model Q4 dan pengujian lokal nyata. **Belum:** avatar karakter Leva final, renderer VRM/Live2D, ekspresi otomatis dari dialog, viseme fonetik, OBS/mocap, serta pembuktian duplex/AEC dan audio-avatar serentak.

**Keputusan trial:** Hauhau4B untuk respons companion cepat; Hauhau9B alternatif lebih panjang/analitis, keduanya direkomendasikan pada Chat sebagai kandidat tanpa juara kualitas mutlak. Rocinante masih eksperimen kreatif dan tidak direkomendasikan sebagai personal utama pada suite Indonesia ini. Asisten produksi dipertahankan; dua Qwen lulus core fixture 9/9, tetapi akses agent trial belum dibuka dalam aplikasi.

Baseline lengkap: 432 single-turn + 360 turn dialog. Persona probe 4B 15/15, 9B 15/15, Rocinante 8/15. Registry tersedia di data lokal, flag eksperimen off, tanpa perubahan binding default. RTX 5070 tunggal lebih cepat daripada dual untuk uji 4B yang sama; dua GPU benar-benar mendapat bobot pada split.

Paket staged: `D:\\AI\\AI Lokal Asisten\\Leva\\program\\0.35.0\\Leva\\Leva.exe`. Tidak mengganti shortcut, menjalankan GUI normal, merestart laptop atau mengganggu remote. Tombol **VTuber ↗** mengaktifkan ruang companion dan membuka panggung web; pengaturan web memungkinkan label dan opt-in model eksperimen. Pilih model/GPU lalu simpan secara eksplisit. Voice pack sebelumnya tetap; playback browser memerlukan aktivasi suara seperti sebelumnya.

Laporan terkait: [benchmark](LEVA_THREE_MODEL_BENCHMARK_REPORT.md), [runtime/GPU](MODEL_RUNTIME_COMPATIBILITY.md), [routing](LEVA_MODE_MODEL_ROUTING_DECISION.md), [persona](LEVA_PERSONA_CONSISTENCY_REPORT.md), [status fitur](../roadmap/LEVA_COMPANION_IMPLEMENTATION_STATUS.md), [aset](../roadmap/LEVA_AVATAR_ASSET_STATUS.md), [framework](../roadmap/LEVA_CAPABILITY_INTEGRATION_MATRIX.md), [tes](../roadmap/LEVA_TEST_EVIDENCE.md), [clean boot](../performance/LEVA_CLEAN_BOOT_READINESS_AND_POLICY.md).

Rollback: tutup hanya instance Leva baru lalu buka paket 0.34.1 yang tetap disimpan. Jangan menghapus data/database atau menghentikan remote. Source awal disimpan di source-before.zip; tidak otomatis mengekstraknya di atas data pengguna. Tidak melakukan Git push.

Langkah berikutnya memerlukan aset avatar yang hak pakainya jelas, bundling renderer VRM/Live2D, pengukuran audio + avatar + ASR serentak, dan blind review pendengaran/gaya oleh pengguna. Tidak menganggap seluruh proyek VTuber selesai pada tahap placeholder ini.

{evidence}''')
 print(json.dumps({'reports_written':16,'registry_updated':True,'production_preferences_changed':False}))
if __name__=='__main__':main()
