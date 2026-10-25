# Reactions and audio R2

The R1 controller remains available as a comparison. R2 has 24 profiles and nine bounded event reactions, including greeting, nod, ponder, comfort, celebrate, playful, apology, surprise and interrupted. Room-scoped ephemeral tags supply enum hints. Reaction IDs, generation IDs, age guards and cooldowns prevent replay of stale events.

Head/body offsets restore the base pose before each update. Wink/blink channels are used only when supported. Existing morphs are blended; profile count is not the count of newly authored facial shapes. Audio-dependent mouth channels are mixed separately from emotional expression to limit conflicts.

Lip movement follows actual browser playback, with smoothing, silence gating and zero-crossing-based shape variation. There is no generated talking animation when audio is absent. No ASR or TTS model is loaded by the preview. The voice test reuses the existing Japanese Leva A sample rather than regenerating audio.

Native Cubism evidence: `ParamMouthOpenY` measured 0.585 during the voice test and 0 after interruption. The final sample clip also loads the SDK pose file, which hides alternate arm drawings; the first preliminary clip without that pose is not acceptance evidence. The 3D interruption report separately records AA/IH/OU at zero after stopping playback.

This does not establish phoneme-accurate lip-sync, multilingual pronunciation quality, stable full-duplex microphone/AEC, or completion of every voice directive. Those remain separate acceptance tracks.
