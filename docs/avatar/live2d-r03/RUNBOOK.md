# R03 runbook

1. Start the validated 0.43.0 application when ready; the current remote session was not restarted.
2. In Leva ♡ settings choose native Live2D and **Leva 2D · rig R03 · kepala, badan, napas & rambut**, then save.
3. Studio → enable **Mata kiri · rekonstruksi dari mata kanan** to compare both eyes with the original wink. This preview option resets on reload; it does not replace source artwork.
4. Select Premium, run **Uji rig & ekspresi 2D · 12 dtk**, and inspect head, eyelids, hair and jacket. The old 3D-only motion selector remains disabled for native Live2D.
5. Compare physics enabled/disabled; test Jeda pose, slow motion and reset. Model motion is limited parallax, not a camera yaw.
6. Use device audio enable/test with an existing sample. Stop should interrupt playback; silence should close the mouth.
7. Download renderer metrics and optionally record 12 seconds. Requested GPU and actual ANGLE GPU must be compared. A 120 FPS target is not a measured guarantee.

Local working files remain under `D:\AI\AI Lokal Asisten\Model Avatar Leva\Live2D\Leva_Advanced_R03`. AOM plus external physics3 are editable. The runtime subfolder is a MOC3 5.0 export. The private archive is `Leva_2D_R03_Editable_Private.zip` beside that folder. SDK Core is separately installed and not bundled or redistributed.

To reproduce numeric acceptance, run `experiments/verify_leva_rig_r03.cjs` with the private Core path, R02 MOC3, R03 MOC3 and an output JSON. `register_leva_live2d_r03.py` pins the local runtime and writes editable physics. It does not change production preferences. Its hardcoded local paths must be adjusted for another computer.

For an isolated preview run `preview_premium_avatar_r2.py --out <private-output> --native --leva --advanced-rig --port 20294`. Use the privately written fixture URL; do not share its bootstrap token. Stop with the fixture's `stop-fixture` file. No microphone or LLM is started.
