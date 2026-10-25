# Hubungan modul Live2D 0.42.0

Peta ini mengikuti source 0.42.0. Graf Graphify historis 0.28.0 tetap merupakan arsip terpisah.

```mermaid
flowchart LR
  Source[Leva SSR sumber privat] --> Editor[Ayatsuri / AOM editabel]
  Editor --> Rig[prepare_leva_live2d_rig_r02.py]
  Rig --> Export[MOC3 5.0 hasil ekspor GUI]
  Physics[attach_leva_live2d_rig_r02_physics.py] --> Export
  Export --> Manifest[Manifest privat dan hash]
  Manifest --> Guard[live2d_assets.py]
  Preferences[preferences.py / companion_avatar.py] --> Bridge[web_bridge.py terautentikasi]
  Guard --> Bridge
  Bridge --> Stage[avatar.js / CompanionStage]
  Stage --> Native[live2d_avatar.js]
  Expressions[live2d_expression.js] --> Native
  Framing[live2d_framing.js] --> Native
  Reactions[avatar_reactions.js] --> Native
  Timing[avatar_timing.js / avatar_dynamics.js] --> Native
  Playback[audio.js / audio yang diputar] --> Reactions
  Native --> Cubism[SDK Cubism lokal / WebGL]
  Stage --> Recording[OpaqueAvatarCapture / MediaRecorder]
  Cubism --> Recording
  Playback --> Recording
```

`leva_ssr` dan `leva_rig_r02` mempunyai root serta manifest berbeda. Perekam mengambil canvas dan audio Leva saja; tidak merekam mikrofon, kamera, seluruh layar atau audio sistem. SDK dan artwork tidak dibundel di source publik.
