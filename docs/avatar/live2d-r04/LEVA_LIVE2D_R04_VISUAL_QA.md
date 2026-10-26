# R04 visual QA

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

Real Core loaded the export: 44 parameters, 59 deformers, 57 ArtMesh. **54 combined poses passed** with finite coordinates. Source face geometry delta is zero for untouched meshes. Open → save → reopen → export was performed in Ayatsuri2D 0.5.8; the exported MOC3 is byte-identical before/after that round-trip. CMO3 remains unverified.

A live 12-second QA cycle sampled **720 frames**. At 1076×583, the 240-frame measurement window showed **60.02 FPS average**, p50 **18.20 ms**, p95/p99 **18.30/18.30 ms**. Physics p95 was **0.10 ms** at 60 Hz. No frame in that window exceeded 25 ms. This is not a locked 60 FPS or 120 FPS claim. Actual GPU: RTX 5070 via ANGLE; a request for RTX 4050 was not confirmed.

The developer slider was moved to AngleX=30 through the UI; downloaded metrics confirmed 30, and reset restored automatic ownership. Mesh wireframe was shown over the separate bionic hand. Native source switching restored UI-selected settings. No shoulder/elbow control is fabricated.

Existing Japanese Leva A audio was confirmed at the playback UI, then recorded with native avatar motion and manually stopped. The first recording was empty; the retry after playback started produced a valid file with nonzero audio. Empty recordings now get an explicit failure message instead of a false success. This does not establish new ASR, echo cancellation, TTS performance or automatic barge-in.

622 Python tests passed (one optional image-engine skip), 19 JavaScript scripts passed, and 104 frozen package checks passed. Source/web asset parity was verified. Production preferences, remote connections and UV settings were not changed.

The visible artwork still looks close to R03 deliberately: it was separated without premium repainting. Seams and precision at new articulation boundaries need artistic refinement before independent motion. No new full-body or four-gesture evidence exists yet.
