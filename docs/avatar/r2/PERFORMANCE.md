# Performance and verification

620 Python regressions, 1 engine skip, 16 JavaScript scripts, 104 frozen checks. Source VRM hash unchanged. Production was not restarted or promoted.

| Window | Target FPS | Observed mean FPS | p95 / p99 ms | CPU frame ms | Physics Hz |
|---|---:|---:|---:|---:|---:|
| leva-premium-r1.json | 60 | 60.00 | 17.10 / 17.30 | 1.67 | 60 |
| leva-premium-r2.json | 60 | 59.50 | 17.10 / 17.20 | 1.84 | 60 |
| leva-ultra-supersampling-1_5x.json | 120 | 120.00 | 11.20 / 11.30 | 1.25 | 60 |
| pixiv-r2-correct-framing.json | 60 | 60.00 | 22.20 / 22.30 | 1.24 | 60 |
| live2d-native-speaking.json | 60 | 60.00 | 21.80 / 22.10 | 2.58 | 60 |
| live2d-native-ultra-stopped.json | 120 | 118.35 | 11.40 / 11.70 | 3.22 | 60 |

Short windows of up to 240 frames are not a long-run acceptance test. Requested RTX4050 did not match the observed RTX5070. Existing UV and other applications were retained. p95 above 8.33 ms means 120 FPS was not uniformly paced. Frame CPU time excludes GPU execution. Corrected-framing fixture clips supersede preliminary torso-only clips. Older long-frame counts use a 1.5× budget threshold, not exact-budget misses. Global CPU/RAM/VRAM telemetry includes other applications and is not attributed solely to the avatar.

A 30-sample global telemetry log is retained privately. No new LLM/TTS throughput benchmark or simultaneous gaming acceptance run was performed. Physical Android, sustained overload fallback, exclusive GPU allocation and final visual approval remain open.
