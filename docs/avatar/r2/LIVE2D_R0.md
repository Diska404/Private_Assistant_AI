# Native Live2D R0 and optional VTS

The user downloaded `CubismSdkForWeb-5-r.4.zip` from Live2D and placed it in the local SDK folder. Its SHA-256 is `d78904d908bd232b800219e01732e4ea2f0562b5e9f35a2670742a1c16d22942`. Runtime logs identify Core 5.1.0. The SDK is extracted and its Framework bundled locally; no package registry install was necessary.

`prepare_live2d_runtime_r0.py` builds a private Framework adapter and writes a 20-resource hash manifest. `live2d_assets.py` serves allowlisted members only after WebBridge session authentication. No user-supplied absolute path, remote texture URL or arbitrary script from a model is accepted. SDK files, Core, moc3 and textures are not included in the GitHub source snapshot. Existing Core/Framework/sample license files remain alongside the local SDK.

The native provider loads the official Hiyori model3, moc3, two texture atlases, physics and pose. It animates gaze, head/body parameters, blink, basic facial expression and playback-driven mouth movement. The pose file is essential to hide alternate arm drawings. Browser WebGL renders the model on the client; HP performance depends on its own graphics hardware. The laptop still supplies model/voice/agent services. Physical Android validation is pending.

Web and packaged web UI now expose three backends: VRM 3D, VTube Studio external, and native Live2D sample. Switching preserves the selected VRM. The native option clearly names Hiyori and does not call the sample Leva. Unsupported 3D rig/material controls are disabled in 2D modes. Missing local SDK returns a clear error rather than a fake avatar.

VTS was separately authorized by the user, using a DPAPI-encrypted local token and a client fixed to 127.0.0.1:8001. The real VTS UI recorded 4,800 requests during the handshake/stream test. VTS itself bound 0.0.0.0, so its API was disabled again after testing. No firewall change or public tunnel was created. VTS external rendering appears in its laptop window; that backend does not stream its avatar video to HP. Native Cubism has no VTS dependency.

## Leva-specific production still required

The generated Leva concept is one original illustration for design review. It is not a layered PSD, cmo3 or moc3. The AAA model is a different character and lacks editable artwork/project sources; it is only a reference audit. The next production steps are layered Leva artwork with concealed areas painted, Cubism mesh/deformers and face parameters, hair/accessory physics, official moc3 export, and registration with an asset-specific parameter map. No sample is renamed to satisfy this requirement.

The production layer/parameter checklist is in `avatar-production/live2d-r0/PRODUCTION_PLAN.md`. Final Leva design, 3D/2D identity match and quality acceptance remain with the user.
