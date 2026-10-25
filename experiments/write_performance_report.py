"""Assemble the reviewable report from measured evidence, never estimated metrics."""
import difflib
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\performance-20261024')
def read(name):return json.loads((OUT/name).read_text('utf-8-sig'))
def n(value):return f'{value:.2f}'
def table_row(label,before,after):
    return f'| {label} | {n(before)} | {n(after)} | {n((before-after)/before*100)}% |'

def main():
    before=read('baseline.json');after=read('after.json');paired=read('paired.json')['results']
    webbefore=read('web-baseline.json')['results'];webafter=read('web-after.json')['results']
    discovery=read('discovery.json');regression=read('regressions.json');packaged=read('packaged-self-test.json');llm=read('inference-validation.json')
    table=['| Pengukuran median, ms kecuali dinyatakan lain | Sebelum | Sesudah | Penurunan biaya |','| --- | ---: | ---: | ---: |']
    table.append(table_row('Publikasi host web, n=60',before['results']['host_publish']['median_ms'],after['results']['host_publish']['median_ms']))
    for key,label in [('orb_idle','Orb idle'),('orb_thinking','Orb thinking'),('orb_listening','Orb listening'),('orb_speaking','Orb speaking')]:
        table.append(table_row(label+', n=80 berpasangan',paired[key]['before']['median_ms'],paired[key]['after']['median_ms']))
    for key,label in [('physics_120','Fisika graf 120 node'),('physics_300','Fisika graf 300 node'),('physics_600','Fisika graf 600 node'),('draw_300','Biaya JS draw 300 node'),('hit_300','Hit testing 300 node')]:
        table.append(table_row(label,webbefore[key]['median_ms'],webafter[key]['median_ms']))
    http=paired['http']
    table.append(table_row('Payload status berubah, byte, 120 pesan sintetis',http['before']['median_changed_bytes'],http['after']['median_changed_bytes']))
    table.append(table_row('HTTP status berubah, n=30',http['before']['changed']['median_ms'],http['after']['changed']['median_ms']))
    table.append(table_row('HTTP 204 tidak berubah, n=30',http['before']['unchanged']['median_ms'],http['after']['unchanged']['median_ms']))
    with zipfile.ZipFile(OUT/'source-before.zip') as archive:
        diff=[];changes=[]
        for name in archive.namelist():
            path=ROOT/name
            if path.is_file() and path.read_bytes()!=archive.read(name):
                previous=archive.read(name).decode('utf-8-sig');current=path.read_text('utf-8-sig')
                changes.append({'file':name,'before_sha256':hashlib.sha256(archive.read(name)).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                diff.extend(difflib.unified_diff(previous.splitlines(True),current.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
        known=set(archive.namelist())
        for base in ('app','experiments'):
            for path in (ROOT/base).rglob('*'):
                name=path.relative_to(ROOT).as_posix()
                if path.is_file() and name not in known and '__pycache__' not in path.parts and 'graphify-out' not in path.parts and path.suffix in ('.py','.js','.mjs'):
                    changes.append({'file':name,'before_sha256':None,'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
                    diff.extend(difflib.unified_diff([],path.read_text('utf-8-sig').splitlines(True),fromfile='/dev/null',tofile='after/'+name))
    (OUT/'LEVA_PROJECT.before.json').write_text(json.dumps(discovery['application'],indent=2),encoding='utf8')
    (OUT/'changes.diff').write_text(''.join(diff),encoding='utf8');(OUT/'changes.json').write_text(json.dumps(changes,indent=2),encoding='utf8')
    tests_passed=regression['tests']-len(regression['skipped'])-len(regression['failures'])-len(regression['errors'])
    text=fr'''# LEVA PERFORMANCE OPTIMIZATION REPORT

Tanggal: 24 Oktober 2026, Asia/Jakarta. Versi source/hasil build: **0.34.1**. Pekerjaan mengikuti direktif pengguna “LEVA AI — FULL SYSTEM PERFORMANCE OPTIMIZATION”.

**Hasil:** bottleneck UI dan sinkronisasi web terukur diperbaiki, visual dipertahankan dan build terpisah lolos pengujian. Tidak ada perubahan model, quantization, context produksi, voice pack, rute GPU pengguna atau konfigurasi remote. Ini bukan klaim seluruh kategori performa sudah diuji atau Flash Next sudah stabil.

## A. System Discovery

- Source aktual: `{ROOT}`. Marker awal menunjukkan versi 0.34.0. Pembacaan proses awal menemukan executable 0.34.0 PID 88412. Pada discovery terperinci berikutnya, proses Leva sudah tidak ditemukan; agent tidak menghentikannya dan tidak membuka instance produksi baru.
- Folder source utama **bukan Git repository**: branch, commit dan working tree Git utama adalah N/A. Checkpoint source sebelum perubahan: `{OUT/'source-before.zip'}`. Salinan terpisah `github-export` berada pada branch `{discovery['export_git_branch']}`, commit `{discovery['export_git_commit']}`, working tree awal bersih. Tidak diubah, dipush atau dimerge.
- Inventaris AST: {len(discovery['modules'])} modul Python aplikasi, termasuk tes. Manifest SHA dan import berada pada `discovery.json`; dependency build diperiksa dari `app/build.ps1`, Python runtime dan environment terpisah. Tidak ditemukan manifest requirements tunggal untuk seluruh ekosistem; web memakai ES modules tanpa dependency npm (`app/leva_web/package.json`).
- Perangkat terdeteksi: RTX 4050 Laptop 6141 MiB dan RTX 5070 12227 MiB; NVIDIA driver 616.56. RAM fisik {discovery['physical_ram_bytes']/2**30:.2f} GiB; 24 logical CPU. Windows 11, Python 3.12.0, PowerShell 7.6.5, Node.js 24.19.0. Backend inferensi b11721 CUDA 13.4 sudah tersedia, tidak diganti.
- Preferensi produksi dibaca read-only dengan allowlist: agent Saluki, provider agent Dual GPU, ASR Qwen3-ASR 0.6B/RTX5070, suara Higgs Leva/Jepang. Ini tidak berarti semua komponen sedang dimuat; pilihan dan pemakaian aktual dibedakan.
- Graphify digunakan sebagai navigasi: graf lengkap 2521 node/8480 edge, bukan graf visual pengetahuan runtime. CLI gagal karena `networkx` tidak tersedia pada interpreter navigasi; pembacaan adjacency JSON stdlib disimpan di `graph-navigation.json`, lalu alur diverifikasi di source. Kosakata yang dipakai berasal dari graf: chat, session, gpu, poll, snapshot, neural, hardware, voice, worker. Snapshot graf bersifat historis, bukan bukti runtime.

### Peta komponen aktual

| Komponen | Modul dan hubungan utama | Hasil audit |
| --- | --- | --- |
| Desktop UI | `gui.py` → `hud_view.py`, `room_ui.py`, `neural_orb.py` | Tkinter Canvas; poll host 100 ms, tick 1 detik; worker terpisah untuk inferensi. |
| Web UI | `leva_web/app.js`, `graph.js`, `physics.js`, `messages.js` | Vanilla ES modules, Canvas 2D dengan proyeksi 3D; bukan Three.js/React. |
| Agent orchestration | `agent_runtime.py`, `assistant_tools.py`, `task_progress.py` | Tool call, validasi, receipt, progres dan pemulihan tetap dipertahankan. |
| LLM inference | `chat_service.py` → `experiments/hybrid_engine.py`, `saluki_backend.py` | Owned subprocess dengan ProcessJob; persistent session dan idle timeout sudah ada. |
| Model routing | `provider_chain.py`, `pipeline_routing.py`, `conversation_rooms.py` | Google/9Router/lokal; ruang Chat/Secret tanpa executor alat. |
| GPU manager | `speech_resources.py`, `speech_configuration.py`, backend GPU visibility | UUID dan buffer model diverifikasi; kartu yang dipilih eksplisit tidak diam-diam diganti. |
| STT | `speech_asr.py`, `local_mic_worker.py`, `remote_speech.py` | ASR lokal terpisah; perangkat mikrofon pengguna tidak dibuka selama pekerjaan ini. |
| TTS | `reply_voice.py`, `voice_pack_service.py`, `voice_pack_worker.py` | Potongan, persistent voice worker, retry dan pembatalan; identitas suara dipertahankan. |
| Voice interaction | `local_mic_service.py`, `speech_turns.py`, `speech_stream.py` | Queue/meter coalescing dan interupsi tersedia; duplex/AEC akustik belum diuji ulang. |
| Context/memory | `conversation_memory.py`, `room_memory.py`, `second_brain.py` | Retrieval/catatan terpisah dari instruksi; tidak ada konteks permanen yang dihapus. |
| Persistence | `preferences.py`, `task_journal.py`, `web_store.py`, SQLite stores | Basis data tes di direktori sementara; produksi dibaca read-only untuk discovery saja. |
| Automation | `desktop_service.py`, `feature_bridge.py`, `terminal_service.py`, `project_workspace.py` | Permission boundary, hasil alat, cancellation dan rollback tidak diubah. |
| Web/desktop communication | `web_host.py` → `web_bridge.py` → polling HTTP | Bukan WebSocket; desktop menerbitkan state 250 ms, browser poll 800 ms. Delta pesan ditambahkan dengan opt-in. |
| Background | `autonomy_services.py`, `image_jobs.py`, `presence_companion.py` | Hardware worker 2 detik; tugas dan kegiatan proaktif tidak dijalankan untuk benchmark. |
| Visualization | `neural_orb.py`, `leva_web/graph.js`, `physics.js` | Jumlah partikel/node/bintang, proyeksi, gaya dan warna dipertahankan; perhitungan berulang dikurangi. |

## B. Baseline dan metode

Source sebelum optimasi diarsipkan **sebelum perubahan aplikasi**. Ukuran publikasi host diukur 60 tick menggunakan preference/room database sintetis dan cProfile. Biaya Canvas Tk diukur pada widget tersembunyi; pembandingan akhir memakai urutan old/new bergantian dalam satu proses dengan waktu animasi identik, 80 sampel terukur per state sesudah 20 warm-up. Posisi dan warna node diperiksa sama.

Fisika/proyeksi web memakai Node.js, 45–60 sampel setelah warm-up. Canvas draw calls merupakan fixture no-op: angka tersebut **bukan FPS browser, input latency pengguna atau biaya GPU paint**. Perintah gambar old/new dibandingkan identik, termasuk bintang dan label. HTTP memakai port loopback acak, autentikasi nyata dengan token fixture, 120 pesan sintetis dan state 5 KB. Tidak mengakses akun/provider online atau prompt pribadi.

Ada aplikasi lain dan layanan remote yang tetap berjalan. Background load, scheduler Windows dan cache filesystem dapat memengaruhi angka. p95 adalah statistik fixture, bukan SLA. Sampel inferensi hanya empat, sehingga p95 inferensi tidak dilaporkan.

## C. Identified Bottlenecks

| Prioritas | Lokasi | Penyebab dan bukti | Dampak |
| --- | --- | --- | --- |
| P1 | `ConversationRooms.snapshot`, `model_choices` | cProfile: 0,378 dari total 0,467 detik/60 tick berada pada snapshot ruang; 968 pembacaan manifest, sekitar 2.600 stat. | I/O drive model berulang pada thread UI saat publikasi status. |
| P1 | `WebBridge.snapshot`, `/api/state` | Snapshot penuh, delivery SELECT dan deepcopy dilakukan sebelum mendeteksi revision yang sama. | Kerja yang langsung dibuang untuk HTTP 204. |
| P1 | State polling dan riwayat | Update hardware mengirim ulang seluruh riwayat; fixture sekitar 180 KB per update. | Payload dan parsing besar pada HP/remote meskipun tidak ada pesan baru. |
| P3 | `NeuralOrb.animate`, `particle` | Geometri sphere dan trigonometri frame dihitung berulang per titik; Canvas style disetel meski nilainya sama. | Tambahan kerja Python/Tcl pada UI thread. |
| P3 | `physics.step` | Array dan destructuring dibuat pada setiap pasangan node O(n²). | Alokasi/GC dan perhitungan mahal ketika graf belum stabil. |
| P3 | `NeuralGraph.draw`, `hit` | Proyeksi dipanggil ulang oleh pembanding sort; 4.456 panggilan draw/300 node dan 4.443 untuk hit fixture. | Kerja berulang pada main thread browser. |
| P3 | Animasi pengetahuan | Graf yang sudah stabil terus dijadwalkan walau visualnya statis; geometri 520 bintang dihitung ulang. | Background rendering yang tidak menghasilkan perubahan visual. |

Runtime AI sudah mempunyai persistent session, cache prefix dan cleanup; tidak ditemukan alasan untuk mengganti model atau menurunkan kualitas demi angka. Flash Next mempunyai kendala RAM terpisah yang didokumentasikan di `HERMES_FLASH_RETRY_20261024.md`; tidak dipaksakan kembali dalam pekerjaan ini.

## D. Implemented Optimizations

| File | Perubahan | Batas/risiko dan validasi |
| --- | --- | --- |
| `conversation_rooms.py` | Cache label/availability dua ruang selama 3 detik. Pengaturan model/GPU tetap dibaca langsung. | Hanya tampilan ketersediaan dapat terlambat ≤3 detik; validasi path saat launch tetap langsung. Tes memastikan cache tidak dapat dimutasi oleh pemakai. |
| `web_bridge.py` | Short circuit revision sebelum deepcopy/DB; opsi `messages_since` mengirim delta. | Client lama tetap full snapshot. Cursor tak ditemukan, riwayat direset/dipangkas atau instance berubah → replace penuh. Origin/cookie/pairing tidak dilonggarkan. |
| `leva_web/messages.js`, `app.js` | Merge delta dengan deduplikasi ID, pemangkasan sesuai first ID server dan replace eksplisit. | Empty reset tetap menghapus tampilan yang lama; perubahan ruang mendapat history baru. Regression mencakup reset/reconnect/trim. |
| `neural_orb.py` | Geometri sphere LRU maksimal 8 ukuran; koefisien trigonometri per frame; update style Canvas hanya ketika warna berubah. | Cache style dibatasi oleh item canvas yang tetap. Jumlah node/edge dan persamaan animasi sama. |
| `leva_web/physics.js` | Hilangkan alokasi array pada setiap pasangan node. | Persamaan dan urutan aritmetika sama, bukan aproksimasi force/spatial pruning. Posisi akhir diuji exact equality. |
| `leva_web/graph.js` | Gunakan proyeksi per node untuk sorting, hit scan linear, cache geometri bintang, hentikan jadwal ketika graf statis. | Hover/drag/zoom/state aktif menjadwalkan ulang; aliran edge tetap aktif pada state terkait. Canvas drawing commands diperiksa identik. |
| Tes dan alat audit | Tambah test invariant dan benchmark; perbaiki fixture lama yang bergantung pada model/voice runtime terpasang. | Tes cancellation suara kini memakai worker tidur sintetis, bukan runtime voice sungguhan. Ini tidak mengubah kemampuan produksi. |
| `LEVA_PROJECT.json`, `hud_view.py`, `web_host.py` | Versi 0.34.1 dan laporan baru. | Tidak ada database migration atau perubahan default model/pengaturan. |

## E. Performance Comparison

{chr(10).join(table)}

Payload turun sekitar 97%. Proyeksi draw/hit turun menjadi tepat **300 panggilan** per 300 node. Pada 35 request HTTP 204, query delivery ledger turun dari **35 menjadi 0**. Query pengaturan pada fixture publikasi tetap 1020/60 tick: tidak ada klaim penghapusan I/O preferences.

**Tail latency belum membaik menyeluruh:** p95 HTTP status berubah naik dari {n(http['before']['changed']['p95_ms'])} ms ke {n(http['after']['changed']['p95_ms'])} ms pada rangkaian lokal ini, meskipun median hampir sama. Hasil ini tidak dipakai untuk mengklaim HTTP selalu lebih cepat. Manfaat yang terbukti adalah payload dan kerja pengulangan yang berkurang. File JSON memuat median/p95/min/max seluruh fixture.

### Validasi inferensi lokal yang tidak diubah

Profil uji Qwen3.5 4B Q4_K_M, RTX5070, konteks 8192, K/V q8, non-thinking; prompt sintetis aritmetika singkat. Profil ini dipakai untuk validasi terbatas, **bukan mengganti Saluki yang dipilih pengguna**. Streaming dipakai oleh alat ukur untuk TTFT, bukan klaim streaming UI produksi sudah ditambahkan.

- Load proses baru: {n(llm['load_seconds'])} detik. Ini cold process start, bukan bukti cold disk cache.
- TTFT respons pertama setelah load: {llm['cases'][0]['ttft_ms']} ms; total {llm['cases'][0]['total_ms']} ms, di luar waktu load.
- Dua warm repeat: TTFT {llm['cases'][1]['ttft_ms']} / {llm['cases'][2]['ttft_ms']} ms; cache reuse 41 token. Warm prompt berubah: {llm['cases'][3]['ttft_ms']} ms.
- Keempat jawaban numerik benar dan selesai `stop`. Decode yang dilaporkan backend sekitar 60–76 token/detik, hanya empat output token per respons: terlalu pendek untuk mewakili generasi panjang.
- Buffer model GPU 2603,5 MiB; worker dilepas. Pemantau membatasi total 180 detik dan menghentikan worker uji bila RAM tersedia <4 GiB. Durasi aktual {llm['total_seconds']} detik.
- Perbandingan kecepatan LLM sebelum/sesudah: **NOT TESTED**; engine/config tidak diubah sehingga validasi ini bukan bukti peningkatan TTFT akibat patch UI.

## F. Regression Tests dan status cakupan

- Aplikasi: **{tests_passed} passed, {len(regression['failures'])} failed, {len(regression['errors'])} errors, {len(regression['skipped'])} skipped; {regression['tests']} total**. Satu modul membutuhkan torch pada interpreter lain. DATA diarahkan ke direktori sementara sebelum import.
- JavaScript: delapan skrip semuanya exit 0, termasuk 13 assertion baru untuk numerik/visual/delta/scheduling; detail pada `javascript-tests.json`.
- Frozen executable: **{packaged['total']} checks passed**, exit {packaged['exit_code']}, tidak ada check gagal. Pipe worker, UI fixture, storage, routing dan receipt diuji tanpa membuka mic atau menjalankan model.
- Model nyata: empat inferensi sintetis lokal selesai; tidak ada panggilan provider online.
- Regresi mencakup cancellation, idle unload, ganti model, GPU hilang/headroom, worker timeout, queue suara, reset riwayat, origin/auth, reconnect dan HTTP 204 melalui fixture. Ini tidak berarti semua skenario pernah diuji pada perangkat fisik.
- Rangkaian isolasi pertama mengungkap tes lama bergantung pada aset terpasang (3 failure/2 error); fixture diperbaiki, lalu seluruh rangkaian dijalankan ulang dan lulus. Error cleanup DB pada salah satu tes diperbaiki dengan finally.

| Metrik/skenario tambahan | Status |
| --- | --- |
| Startup desktop produksi sebelum/sesudah | NOT TESTED; produksi tidak direstart. Build/package smoke check terpisah lulus. |
| Foreground input latency dan event-loop blocking seluruh desktop saat agent aktif | NOT TESTED; biaya Canvas/host fixture sudah diukur. |
| Browser FPS, long task, heap dan RAM sesi berjam-jam | NOT TESTED; Node/Tk cost bukan pengganti profiling browser/sesi panjang. |
| Input/keluaran suara headset, STT, TTS/TTFA dan AEC akustik | NOT TESTED; mikrofon/speaker pengguna tidak dibuka. Fixture suara/interupsi lulus. |
| Model switching nyata Saluki/27B/35B/Flash dan dual GPU | NOT TESTED pada patch ini; kebijakan dan kontrak diuji fixture, data eksperimen historis terpisah. |
| Gaming + inference dan mode power/driver | NOT TESTED; tidak ada perubahan daya/driver global. |
| Latensi Internet/Tailscale HP fisik | NOT TESTED; HTTP diukur loopback, protokol pairing/auth tetap diuji. |
| Kualitas jawaban kompleks/agent | NOT TESTED ulang; model, prompt, konteks, tool permission dan sampling produksi tetap sama. |

## G. Remaining Recommendations

1. Profil browser desktop/Android dengan frame pacing, long tasks dan heap selama sesi representatif. Jangan menyatakan 60 FPS sudah tercapai dari angka Node.
2. Jalankan uji idle/sesi 30–60 menit setelah pengguna memilih waktu yang sesuai; ukur CPU/RAM/VRAM proses, bukan sistem agregat saja. Belum ada bukti leak sesi panjang atau klaim leak telah dihilangkan.
3. Profil Saluki dan TTS terpilih dengan permintaan sama, ukur TTFT/TTFA dan pergantian workload. Persistent cache sudah tersedia; cache suara tidak boleh dipertahankan bila membuat LLM spill/VRAM penuh.
4. Streaming token end-to-end UI masih pekerjaan terpisah; perlu backpressure, generation ID dan pembatalan sebelum dapat dianggap selesai. Patch ini tidak menambahkan streaming jawaban produksi.
5. Scheduler Performance/Balanced/Gaming/Eco lintas engine belum ditambahkan. Kebijakan idle/hemat dan GPU eksplisit yang ada dipertahankan; benchmark game diperlukan sebelum kebijakan baru.
6. Flash Next tetap belum stabil di Hermes; konteks besar/DIO dan tekanan RAM bukan diperbaiki oleh optimasi visual. Lihat laporan khusus; jangan menutup aplikasi atau mengubah pagefile untuk memaksakan tes.

### Paket dan rollback

Paket terpisah: `D:\AI\AI Lokal Asisten\Leva\program\0.34.1\Leva\Leva.exe`. Tidak mengganti binary 0.34.0, shortcut produksi atau memulai ulang Leva otomatis. Pemilihan paket baru dilakukan saat pengguna siap membuka versi tersebut. Source utama sudah diperbarui; membuka source langsung memakai 0.34.1.

Executable SHA256: `{packaged['executable_sha256']}`. Staging asli dan versi 0.34.0 dipertahankan. `changes.diff` serta `changes.json` dapat diperiksa. Untuk rollback source, pulihkan hanya file terkait dari `source-before.zip` setelah membandingkan hash dan memastikan tidak ada perubahan baru pengguna; jangan menghapus database atau mengekstrak secara buta menimpa pekerjaan baru. Modul tambahan `messages.js` tidak perlu dihapus untuk menjalankan source lama yang tidak mengimpornya.

## H. Remote Safety Verification

- Tidak ada restart/shutdown Windows, perubahan konfigurasi jaringan/firewall/VPN, driver, Thunderbolt, power plan atau pagefile.
- Tidak ada penghentian sengaja terhadap layanan remote atau aplikasi pengguna. `remoting_host.exe` PID 5192/5648 dan `tailscaled.exe` PID 18388/68328 tetap ditemukan pada pemeriksaan akhir.
- Tidak ada model, voice pack, memori percakapan atau database pengguna dihapus. Tidak ada API key/token disalin ke laporan atau dikirim ke layanan lain.
- Basis data fixture dan endpoint uji terisolasi; hanya worker inferensi milik probe yang dibuka/dilepas. Tidak ada mic otomatis atau layanan online berbayar dipanggil.
- Paket produksi lama tidak ditimpa, tidak ada Git push/merge, dan tidak ada restart Leva untuk aktivasi patch.

Artefak pembuktian berada pada `{OUT}`: `discovery.json`, `graph-navigation.json`, `baseline.json`, `after.json`, `paired.json`, `web-baseline.json`, `web-after.json`, `inference-validation.json`, `regressions.json`, `javascript-tests.json`, `packaged-self-test.json`, `changes.diff`, serta checkpoint source.
'''
    (ROOT/'LEVA_PERFORMANCE_OPTIMIZATION_REPORT.md').write_text(text,encoding='utf8')
    print(json.dumps({'report':str(ROOT/'LEVA_PERFORMANCE_OPTIMIZATION_REPORT.md'),'changed_checkpoint_files':len(changes),'tests_passed':tests_passed}))

if __name__=='__main__':main()
