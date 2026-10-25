# Physics R2

The actual three-vrm solver is used. The category presets cover long hair, bangs, side hair, ribbon, collar, jacket, hem and accessories; name-based classification is heuristic, not a rigging authoring substitute. Unknown joints retain original settings. Nine spherical collider zones follow humanoid head, neck, shoulders, chest/back, hips and legs where those bones exist.

The layer restores original joint settings and collider groups, removes only its own colliders and updates the manager dependency order. Fixed-step work is capped at four steps per frame; discarded time is reported. Visibility changes, stalls and large root pose discontinuities reset simulation to limit instability.

Real browser fixture observations: 57 joints and 13 source colliders become 22 colliders. A recorded fast-turn window observed 240 contacts in 25,380 collision tests before projection. This demonstrates solver interaction, not absence of hair/body or clothing penetration. The collider debug helper was corrected to use constructors from the same bundled three-vrm module as the loader; mixing bundled class identities previously raised “Unknown collider shape”.

Actual Leva has 302 source joints and zero colliders. Its material/physics edits remain gated off. No new mesh weights, cloth mesh simulation or corrective blendshapes have been authored on that source. The fixture clips are explicitly labeled pixiv, not final Leva.

Before and after clips, rig audits and collision telemetry are in the private R2 verification folder. Long-running motion/clipping review and user acceptance remain open. Older torso-framed fixture clips are retained as preliminary evidence; corrected-framing clips are separately named.
