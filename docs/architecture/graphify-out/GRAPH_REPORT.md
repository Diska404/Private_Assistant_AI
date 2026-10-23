# Graph Report - app  (2026-10-23)

## Corpus Check
- 167 files · ~74,979 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: .css 2, .webmanifest 1)

## Summary
- 2356 nodes · 7381 edges · 106 communities (61 shown, 45 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 1286 edges (avg confidence: 0.87)
- Token cost: 11,836 input · 4,254 output

## Community Hubs (Navigation)
- Workflow ComfyUI Fooocus
- Duplex Eksperimental Lokal
- Segmentasi dan Catatan Suara
- Thread dan Server Lokal
- Balasan dan Antrean Audio
- Perintah dan Penjadwalan
- Registry Alat dan Dispatch
- Ruang Chat dan Secret
- Orkestrasi Jendela Utama
- Pengukuran ASR Lab
- Proses dan Infrastruktur Pengujian
- Gateway dan Provider 9Router
- Vault dan Indeks Pengetahuan
- Panel Pusat dan Pengetahuan
- Streaming Google Live
- Preferensi dan Kebiasaan
- Integritas dan Runtime Program
- Penyimpanan dan Jurnal Pengujian
- Kebijakan GPU dan Model
- Antarmuka Web Utama
- Dashboard Evaluasi ASR
- Startup Jendela dan Rute
- Entrypoint dan Pemeriksaan Paket
- Rute Percakapan dan Delegasi
- Siklus Agent dan Alat
- Jurnal Tugas dan Redaksi
- HUD dan Tampilan Penuh
- Worker Fitur dan Memori
- Eksekusi Skill Host
- Rantai Inferensi dan Fallback
- Jembatan Desktop Web
- Graf HUD dan Navigasi
- Pengelolaan Voice Pack
- Antrean Generasi Gambar
- Sintesis Voice Pack Lokal
- Terminal dan Proses Tugas
- Sesi Model dan Containment
- Akses Berkas dan PDF
- Patch Proyek dan Rollback
- Meter dan Indikator Mikrofon
- Validasi Provider dan Alat
- Layanan Mikrofon Lokal
- Katalog Steam dan Game
- Antrean Pemutaran Streaming
- Pairing dan Antrean Web
- Panel Suara Google Live
- Render Graf Neural Web
- Runtime Pengenalan Suara
- Render Orb Desktop
- Memori Percakapan Persisten
- Sesi Perangkat dan Avatar
- Pemulihan Pendengar Lokal
- Skill Workflow dan Integrasi
- Panel Pengaturan Desktop
- Gateway Pribadi Tailscale
- Pembaca Internet Publik
- Panel Koneksi Android
- Kendali Lampu LAN
- Draf Ucapan dari HP
- Runtime Browser Terkelola
- Siklus Worker Live
- Katalog Aplikasi Windows
- Fisika Graf dan Kamera
- Pengujian Cache Model Hangat
- Worker Fitur dan Riset
- Antrean Event Suara
- Worker Generasi Fooocus
- Jendela Catatan Ucapan
- Output Audio dan Telemetri
- Pemulihan Tugas Agent
- HTTP dan Validasi Origin
- Pengujian Lifecycle Server Web
- Operasi Berkas dan Undo
- Sinkronisasi HUD dan Model
- Pemutar Suara Browser
- Mikrofon Push To Talk
- Pengujian HTTP Mobile
- Sesi Engine Voice Pack
- Preferensi Memori Pribadi
- Foto Profil Lintas Antarmuka
- Telemetri Level Suara
- Pemilihan GPU TTS
- Ruang Percakapan Web
- Konversi Identitas Suara
- Kebijakan Gaya Personal
- Autentikasi dan Pairing HTTP
- Lokasi Perangkat Windows
- Dokumen Rilis Awal
- Kehadiran Perangkat Terhubung
- Polling Web dan Data
- Worker Pengujian Model Hangat
- Peluncuran dan Identitas Proses
- Audio Worklet ASR Lab
- Pengaturan Engine Web
- Audio Worklet Mikrofon HP
- Metadata Paket Web
- Bukti Asisten Versi Awal
- Bukti Retest Otonomi
- Bukti Efisiensi Rilis Lama
- Kajian Video Full Duplex
- Kajian Video Jarvis Awal
- Kajian HUD dan REA
- Bukti Adapter Duplex LoRA
- Bukti Saluki dan Suara

## God Nodes (most connected - your core abstractions)
1. `LevaWindow` - 115 edges
2. `main()` - 98 edges
3. `AssistantTools` - 65 edges
4. `Preferences` - 60 edges
5. `VoicePackService` - 57 edges
6. `run_agent()` - 53 edges
7. `TaskJournal` - 49 edges
8. `route_spec()` - 48 edges
9. `WebBridge` - 48 edges
10. `ReplyVoice` - 45 edges

## Surprising Connections (you probably didn't know these)
- `ASR Evaluation Lab` --conceptually_related_to--> `Leva Desktop 0.13`  [AMBIGUOUS]
  asr_lab_web/index.html → RELEASE_NOTES.md
- `AdvancedWindow` --uses--> `TaskJournal`  [INFERRED]
  advanced_window.py → task_journal.py
- `LevaWindow` --uses--> `AdvancedWindow`  [INFERRED]
  gui.py → advanced_window.py
- `known_folders()` --indirect_call--> `key()`  [INFERRED]
  file_workspace.py → agent_contract.py
- `_run_agent()` --uses--> `InferenceRoute`  [INFERRED]
  agent_runtime.py → provider_chain.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **9Router Integration Flow** — release_notes_leva_desktop_0_13, release_notes_leva_desktop_0_13_1, release_notes_leva_desktop_0_13_2 [EXTRACTED 1.00]
- **Local Voice & TTS Evolution** — release_notes_leva_desktop_0_8, release_notes_leva_desktop_0_9, release_notes_leva_desktop_0_10, release_notes_leva_desktop_0_11 [INFERRED 0.90]

## Communities (106 total, 45 thin omitted)

### Community 0 - "Workflow ComfyUI Fooocus"
Cohesion: 0.05
Nodes (15): ComfyClient, ComfyError, ComfyService, validate_graph(), visit(), FooocusClient, FooocusService, NoRedirect (+7 more)

### Community 1 - "Duplex Eksperimental Lokal"
Cohesion: 0.05
Nodes (20): DuplexCoordinator, parse_decision(), replay_scenarios(), SpeechGate, StableTranscript, Tick, TranscriptDelta, DuplexService (+12 more)

### Community 2 - "Segmentasi dan Catatan Suara"
Cohesion: 0.05
Nodes (19): transcribe(), EchoGuard, Segmenter, self_transcript(), WakePolicy, emit(), run(), commit() (+11 more)

### Community 3 - "Thread dan Server Lokal"
Cohesion: 0.06
Nodes (11): main(), main(), setup_link(), validate_wav(), receive_pcm(), wav_bytes(), event(), Response (+3 more)

### Community 4 - "Balasan dan Antrean Audio"
Cohesion: 0.06
Nodes (13): check(), ReplyVoice, speech_chunks(), chosen_acceleration(), check(), prepare_spoken_text(), SpeechPresentationTests, ReplyTests (+5 more)

### Community 5 - "Perintah dan Penjadwalan"
Cohesion: 0.07
Nodes (8): DesktopExecutor, DesktopService, digest(), parse_schedule(), ScheduleStore, DesktopCommandTests, ScheduleTests, idle_milliseconds()

### Community 6 - "Registry Alat dan Dispatch"
Cohesion: 0.07
Nodes (19): exact_requested_text(), image_open_only(), requested_url(), requested_urls(), requested_voice_language(), safe_url(), Skill, BrowserLauncher (+11 more)

### Community 7 - "Ruang Chat dan Secret"
Cohesion: 0.08
Nodes (21): bounded_history(), compose_message(), ConversationUploads, extract_upload(), intent(), needs_web(), parse_route(), ConversationRooms (+13 more)

### Community 8 - "Orkestrasi Jendela Utama"
Cohesion: 0.09
Nodes (8): LevaWindow, recolor(), launch_selected(), open_selected(), prepare(), run(), start_agent_gateway(), VoicePrivacyLifecycleTests

### Community 9 - "Pengukuran ASR Lab"
Cohesion: 0.06
Nodes (22): hardware(), Lab, run(), main(), alignment(), percentile(), score(), summary() (+14 more)

### Community 10 - "Proses dan Infrastruktur Pengujian"
Cohesion: 0.11
Nodes (5): session_worker(), baseline_messages(), duplex_worker(), SalukiEngine, verify()

### Community 11 - "Gateway dan Provider 9Router"
Cohesion: 0.06
Nodes (12): base_url(), reachable(), RouterGateway, NoRedirect, RouterClient, RouterWindow, check(), AdditionalRoadmapTests (+4 more)

### Community 12 - "Vault dan Indeks Pengetahuan"
Cohesion: 0.11
Nodes (7): clean_note(), metadata(), relative_note(), SecondBrain, VaultIndex, SecondBrainTests, make()

### Community 13 - "Panel Pusat dan Pengetahuan"
Cohesion: 0.08
Nodes (3): AdvancedWindow, run(), SecondBrainPanel

### Community 14 - "Streaming Google Live"
Cohesion: 0.10
Nodes (15): classify_voice_error(), connect_live(), voice_worker(), event(), on_input(), on_output(), receive(), main() (+7 more)

### Community 15 - "Preferensi dan Kebiasaan"
Cohesion: 0.12
Nodes (4): router_call(), Preferences, configured_client(), PreferenceTests

### Community 16 - "Integritas dan Runtime Program"
Cohesion: 0.10
Nodes (12): synthesize(), synthesize_japanese(), generate(), verify_assets(), cache_key(), cached_reaction(), prepare_reaction(), run() (+4 more)

### Community 17 - "Penyimpanan dan Jurnal Pengujian"
Cohesion: 0.09
Nodes (8): checked_path(), comfyui(), project_root(), gpu_snapshot(), patched_text(), dispatch_verified(), unresolved_receipts(), completion_status()

### Community 18 - "Kebijakan GPU dan Model"
Cohesion: 0.09
Nodes (12): validate_setting(), vault_root(), apply_pipeline_settings(), configuration_snapshot(), validate_pipeline_settings(), SpeechPipelineWindow, agent_mode(), gpu_rows() (+4 more)

### Community 19 - "Antarmuka Web Utama"
Cohesion: 0.10
Nodes (36): action(), apply(), applyAvatar(), card(), categories, chatPanel, command(), drawer() (+28 more)

### Community 20 - "Dashboard Evaluasi ASR"
Cohesion: 0.13
Nodes (31): api(), base64(), capture, devices(), disable(), drawDetail(), drawSelected(), enable() (+23 more)

### Community 21 - "Startup Jendela dan Rute"
Cohesion: 0.09
Nodes (7): effective_speech_language(), HardwareMonitor, run(), ProactiveService, MemoryWindow, local_voice_route(), visible_route()

### Community 22 - "Entrypoint dan Pemeriksaan Paket"
Cohesion: 0.13
Nodes (15): briefing_request(), correction_goal(), development_evidence(), knowledge_question(), website_creation(), _run_agent(), comfy_generation_requested(), selected_skills() (+7 more)

### Community 23 - "Rute Percakapan dan Delegasi"
Cohesion: 0.11
Nodes (5): conversation_request(), parse_frontend(), route_spec(), GPUContractTests, SpeechPipelineTests

### Community 24 - "Siklus Agent dan Alat"
Cohesion: 0.12
Nodes (5): run_agent(), ensure_task(), tracked_emit(), SkillTests, emit()

### Community 25 - "Jurnal Tugas dan Redaksi"
Cohesion: 0.17
Nodes (4): redact(), TaskJournal, ContinuityTests, RoutingRegressionTests

### Community 27 - "Worker Fitur dan Memori"
Cohesion: 0.14
Nodes (18): audio_devices(), caption(), capture(), computer(), describe(), dispatch(), inspect(), location() (+10 more)

### Community 28 - "Eksekusi Skill Host"
Cohesion: 0.17
Nodes (3): AssistantTools, PluginManager, AutonomyTests

### Community 29 - "Rantai Inferensi dan Fallback"
Cohesion: 0.17
Nodes (6): make_local(), run_worker(), router_call(), InferenceRoute, ProviderChainTests, TranslationFallbackTests

### Community 30 - "Jembatan Desktop Web"
Cohesion: 0.13
Nodes (5): add(), WebDataTests, WebData, DesktopWebHost, start()

### Community 31 - "Graf HUD dan Navigasi"
Cohesion: 0.16
Nodes (8): assistant_state(), coordinates(), filtered(), inventory(), Node, project(), shortest_path(), HUDTests

### Community 32 - "Pengelolaan Voice Pack"
Cohesion: 0.12
Nodes (6): VoicePackTests, VoicePackWindow, candidate_available(), catalog(), resolve_pack(), voice_error_notice()

### Community 33 - "Antrean Generasi Gambar"
Cohesion: 0.16
Nodes (4): ImageJobs, ImageSessionTests, lost(), emit()

### Community 35 - "Terminal dan Proses Tugas"
Cohesion: 0.22
Nodes (3): TerminalService, monitor(), TerminalTests

### Community 36 - "Sesi Model dan Containment"
Cohesion: 0.18
Nodes (6): ChatService, WorkerTests, __init__(), send(), start(), ProcessJob

### Community 37 - "Akses Berkas dan PDF"
Cohesion: 0.16
Nodes (5): FileWorkspace, known_folders(), normalized_name(), source_redact(), FileAccessTests

### Community 38 - "Patch Proyek dan Rollback"
Cohesion: 0.24
Nodes (4): ProjectWorkspace, run(), sha(), ProjectTests

### Community 39 - "Meter dan Indikator Mikrofon"
Cohesion: 0.22
Nodes (5): resource(), dbfs(), MicTelemetry, pcm_measurements(), MicIndicatorTests

### Community 40 - "Validasi Provider dan Alat"
Cohesion: 0.14
Nodes (6): validate_call(), available(), load_key(), _protect(), save_key(), higgs_text()

### Community 43 - "Antrean Pemutaran Streaming"
Cohesion: 0.16
Nodes (3): StreamPlayback, Sink, SpeechStreamTests

### Community 44 - "Pairing dan Antrean Web"
Cohesion: 0.17
Nodes (3): DurableTests, WebBridge, PairingGate

### Community 47 - "Runtime Pengenalan Suara"
Cohesion: 0.14
Nodes (3): main(), normalized_transcript(), SpeechASR

### Community 48 - "Render Orb Desktop"
Cohesion: 0.16
Nodes (5): color(), NeuralOrb, particle(), main(), NeuralGeometryTests

### Community 50 - "Sesi Perangkat dan Avatar"
Cohesion: 0.26
Nodes (3): post(), digest(), WebStore

### Community 54 - "Gateway Pribadi Tailscale"
Cohesion: 0.26
Nodes (4): run(), GatewayError, RemoteGateway, GatewayTests

### Community 55 - "Pembaca Internet Publik"
Cohesion: 0.22
Nodes (7): fetch(), news(), public_url(), read(), Redirect, weather(), weather_coordinates()

### Community 57 - "Kendali Lampu LAN"
Cohesion: 0.22
Nodes (3): NoRedirect, RoomLamp, LampTests

### Community 58 - "Draf Ucapan dari HP"
Cohesion: 0.29
Nodes (3): RemoteSpeech, work(), PhoneDraftTests

### Community 62 - "Fisika Graf dan Kamera"
Cohesion: 0.24
Nodes (8): setChatHeight(), chatHeight(), orbit(), rotatePoint(), COLORS, hash(), initialize(), step()

### Community 63 - "Pengujian Cache Model Hangat"
Cohesion: 0.24
Nodes (3): Model, WarmTests, __next__()

### Community 64 - "Worker Fitur dan Riset"
Cohesion: 0.27
Nodes (5): authorized(), public_research(), read(), search(), FeatureBridge

### Community 66 - "Worker Generasi Fooocus"
Cohesion: 0.31
Nodes (9): main(), execute(), launch_with_api(), authorize(), generate(), inspect(), queue(), status() (+1 more)

### Community 70 - "HTTP dan Validasi Origin"
Cohesion: 0.45
Nodes (9): authenticated(), do_GET(), do_POST(), request_origin(), send(), server_bind(), session(), setup() (+1 more)

### Community 73 - "Sinkronisasi HUD dan Model"
Cohesion: 0.28
Nodes (3): sync(), MicIndicator, sync_room_controls()

### Community 77 - "Sesi Engine Voice Pack"
Cohesion: 0.22
Nodes (3): diagnostic_error(), emit_delta(), session()

### Community 81 - "Pemilihan GPU TTS"
Cohesion: 0.33
Nodes (3): AudioCppVoice, choose_gpu(), fits()

### Community 83 - "Konversi Identitas Suara"
Cohesion: 0.33
Nodes (3): asset_stamp(), convert(), synthesize()

### Community 87 - "Dokumen Rilis Awal"
Cohesion: 0.33
Nodes (6): APP_README.md, Leva Desktop 0.1, Leva Desktop 0.2, Leva Desktop 0.3, SETTINGS_AND_MEMORY.md, VOICE_MODE.md

### Community 89 - "Polling Web dan Data"
Cohesion: 0.80
Nodes (5): api(), initialize(), loadGraph(), notice(), poll()

### Community 91 - "Peluncuran dan Identitas Proses"
Cohesion: 0.50
Nodes (3): key(), startup(), steam_executable()

### Community 95 - "Metadata Paket Web"
Cohesion: 0.50
Nodes (3): description, private, type

## Ambiguous Edges - Review These
- `Leva Desktop 0.13` → `ASR Evaluation Lab`  [AMBIGUOUS]
  asr_lab_web/index.html · relation: conceptually_related_to

## Knowledge Gaps
- **23 isolated node(s):** `Leva Desktop 0.13.2`, `Leva Desktop 0.13.1`, `Leva Desktop 0.12`, `Leva Desktop 0.11`, `Leva Desktop 0.10` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 458 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **45 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Bagaimana LevaWindow menghubungkan ruang Chat/Secret, suara, web/HP, dan agent?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Apakah 38 hubungan INFERRED pada LevaWindow sesuai kode sebenarnya?**
  _`LevaWindow` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Bagaimana dokumen rilis lama terhubung dengan kode Leva saat ini?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Perlukah Workflow ComfyUI Fooocus dipisah lebih jauh? Cohesion: 0.05039193729003359.**
  _Cohesion score 0.05039193729003359 - nodes in this community are weakly interconnected._
- **Mengapa main() menghubungkan startup, worker, dan pemeriksaan paket?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Apakah 39 hubungan INFERRED pada main() sesuai kode sebenarnya?**
  _`main()` has 39 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **Apakah hubungan ASR Evaluation Lab dengan rilis Leva 0.13 benar-benar terbukti?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
## Scope and Integrity Audit

- Scope: app/ only; no executable/model weights or sibling project documentation were analyzed. AST and semantic extraction are static evidence, not runtime verification.
- Missing file-level representation: voice_packs.json. The detector additionally lists two CSS files and one web manifest as unclassified; their contents have no graph representation.
- Raw extraction diagnostics: 1056 dangling-endpoint references; 0 missing-endpoint references; 13 self-loops; 189 undirected same-endpoint merges. Graph is useful for navigation but is not a complete call graph. These are graph diagnostics, not proven Leva runtime defects.
- Semantic audit: the provider proposed an ASR-lab/release-0.13 relationship based on shared Qwen naming. It was retained as AMBIGUOUS at confidence 0.2, not a historical fact. One README citation was checked against RELEASE_NOTES.md line 156 and two script references were extracted directly from markup.
- RELEASE_NOTES.md in app/ is historical (latest heading 0.13.2); it does not document all current 0.28.0 behavior. Referenced reports outside app/ are citation nodes only; their contents were not read.
- Semantic provider reported zero failed chunks and zero uncovered files. Source files were within the extraction input size.
- Exact cohesion scores are preserved in cohesion.json; rounded displays are navigation aids.
- Actual provider usage: 11836 input tokens, 4254 output tokens. AST extraction used no model tokens. This does not include host-assistant conversation or tool-orchestration tokens.

- SVG icon was interpreted through its source markup. No pixel-vision analysis is claimed.
- Benchmark uses its own corpus estimate (117,800 words), different from detect (74,979 words). The token-reduction figure is heuristic and excludes extraction setup; it is not measured billing or answer accuracy.
