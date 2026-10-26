# Leva Live2D advanced rig R03 — 0.43.0

Verified locally on 26 October 2026. This milestone extends the R02 copy; source artwork, atlas, twelve source expressions, original 3D and prior R02 remain preserved. No image generation.

| Capability | Result |
|---|---|
| Model | 44 parameters, 59 deformers, 46 meshes; previous R02 had 34 / 54 / 35 |
| Head | Angle X/Y shallow parallax plus existing Z tilt; natural motion and 12-second QA |
| Body | Small body sway/lean and breathing; bounded, with freeze/reset |
| Secondary motion | Four Cubism pendulum groups: front hair, back hair, side hair and jacket |
| Left eye | Optional mirrored/baked reconstruction from existing right-eye art, 54 sampled forms per cloned mesh; gaze, blink and happy/angry mood |
| Expressions / mouth | Twelve original expression recipes retained; lip-sync uses actual playback level |
| Controls | Source wink remains default; optional left-eye checkbox, pause pose, physics on/off, solver rates, slow motion and QA |
| Recording | Copy native WebGL output immediately after render, then composite opaque video; avoids blank frame races and alpha artifacts |

## Evidence

Real Cubism Core 5.1 loaded the exported MOC3 5.0. The 54 geometry poses passed. All nine tested movement controls changed vertices, all sampled values stayed finite, and neutral original-mesh displacement from R02 was only **8.94e-8 model units**. Existing Z-tilt extremes also preserved R02 geometry.

The live 12-second test collected **719 simulated frames**, covering head X ±30, Y ±24, Z ±30, body ±8 and both-eye blink range 0–1. Hair and jacket outputs changed through the real physics solver. The recorded range is test evidence, not a claim of full perspective head turning or independent cloth simulation.

At 1076 × 583, the 240-frame metrics window measured **60.02 FPS average**, frame p95/p99 **18.30 ms**, physics p95 **0.10 ms**, and zero frames above 25 ms. ANGLE identified **RTX 5070** although the fixture requested RTX 4050; the GPU mismatch remains visible. No 120 FPS hardware result is claimed. Video capture target 30 FPS produced approximately 29.92 FPS; renderer and encoded-video rates are distinct.

Japanese Leva A playback, animated mouth and expressions, and manual Stop were observed. This does not establish new TTS latency, ASR recognition, automatic barge-in or acoustic echo cancellation. Freeze was separately confirmed with all head/body/breath/secondary controls and mouth at zero.

622 Python tests passed (one optional image-engine test skipped), all 18 JavaScript scripts passed, and 104 frozen-package checks passed with source/web hash parity. Test data was redirected to an isolated fixture. The first Python run lacked the existing build-tools import path; the corrected run used the installed dependencies and passed.

## Boundaries

The source is a partial illustration rig with much body/hair on one base sprite. This upgrade provides restrained 2.5D deformation; it cannot expose unseen artwork or supply independent arm poses, large perspective yaw, clothing collision or full-body locomotion. Left-eye symmetry remains an approximation and is opt-in. More complete independent movement requires separately authored layers and corrective artwork.

Physics is an editable external physics3 preset. The AOM is editable in Ayatsuri2D; MOC3 runtime export is tested. Experimental CMO3 export remains unverified. Source availability does not establish an open artwork licence; raw assets, SDK and private recordings are not distributed in GitHub.

## Reproduction

See [RUNBOOK.md](RUNBOOK.md), [MODULE_MAP.md](MODULE_MAP.md), and [verification-summary.json](verification-summary.json). R02 history remains in [the prior report](../live2d-r01/REPORT.md).
