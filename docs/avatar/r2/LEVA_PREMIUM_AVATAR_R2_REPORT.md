# Leva 0.41.0 — R2 + Live2D R0 candidate

25 October 2026. This is an implemented candidate with measured evidence, not final visual acceptance.

## Delivered

- Ultra requests 120 render FPS. Physics defaults to 60 Hz and has an independent 15/30/60/120 Hz selector; 120 Hz physics remains experimental. Rendering cannot exceed the browser/display refresh rate.
- Bounded fixed-step physics, stall/visibility reset, teleport guard and adaptive 120→60 fallback. The fallback is unit-tested against sustained simulated overload; a live overload acceptance test remains open.
- Reversible category presets and nine bone-following collider zones on modification-permitted VRM assets. Solver contacts are measured before projection; this is not a skinned-mesh clipping certificate.
- 24 expression profiles and nine bounded event reactions. These blend existing channels; no new source blendshape geometry was authored.
- Mouth movement uses actual playback amplitude and zero-crossing features. No microphone is required. This is an audio heuristic, not phoneme recognition or forced alignment.
- Optional authenticated VTube Studio bridge and a native Cubism Web provider. The native provider loads actual model3/moc3/textures/physics/pose from the user's local SDK, not a flat illustration.
- Hash-pinned resource allowlist; no arbitrary disk path or public SDK distribution. Core and sample assets remain outside the source repository.
- Independent 0.41.0 executable candidate, isolated regressions, JavaScript checks and frozen-package checks.

## Measured limits

Actual Leva VRM rendered at about 120 FPS averaged over a short 240-frame window; p95 was about 11.2–11.4 ms. That exceeds the 8.33 ms interval required for uniformly paced 120 FPS. It is not a locked-120 claim. Final Ultra defaults to 60 Hz physics, even though the first experimental measurement used 120 Hz physics.

Native Hiyori sample: approximately 60 FPS at the 60 target; a separate Ultra window measured 118.35 FPS, p95 11.4 ms, with 60 Hz physics. These are local browser observations under the user's existing UV profile and background load, not a controlled cross-device benchmark. The observed renderer was RTX 5070; the request for RTX 4050 was not fulfilled by this browser. GPU binding remains unverified.

The older `over_budget_frames` metric counts intervals greater than 1.5× the target interval. New reports expose that threshold and `long_frame_count`; it is not a count of every interval above the exact frame budget. Estimated missed slots are derived estimates, not presentation-system dropped-frame counters. CPU render submission time is not GPU execution time.

## Asset boundaries and unfinished work

The original Leva source remains read-only and its no-modification restriction is enforced for secondary-motion/material layers. It has 302 spring joints and zero source colliders in this renderer. Collider tuning is demonstrated on the licensed pixiv fixture: 57 joints, 13 source colliders, 22 with the nine added zones. Permission to edit that fixture does not imply permission to edit the Leva source.

Native Live2D is proven using the official Hiyori sample. The VTS handshake/stream test used an existing Mari model. Neither is called Leva. The AAA archive is reference-only. An independently drawn Leva concept is still a single illustration: editable layered art, Cubism project, deformation mesh and final Leva moc3 are pending. Physical Android rendering and user visual acceptance are also pending.

Ray tracing is not enabled. Current VRM shading uses MToon/WebGL; the UI offers scene lights, resolution supersampling and permission-gated material tuning. This does not synthesize new texture detail, normals or a ray-traced animated MToon pipeline.

## Evidence and rollback

Private evidence resides in `D:\AI\AI Lokal Asisten\Leva\verification\leva-premium-avatar-r2`: metrics, videos, source audit and checkpoints. Source model hashes are preserved. The 0.40.0 candidate and production preferences remain intact; use the prior executable to roll back. R1/R2, physics, secondary layer and material controls are reversible. VTS API was turned off after the test; native Cubism needs no VTS listener.

See [performance](PERFORMANCE.md), [physics](PHYSICS.md), [reactions/audio](REACTIONS_AUDIO.md), [Live2D](LIVE2D_R0.md), and [graphics](GRAPHICS.md).
