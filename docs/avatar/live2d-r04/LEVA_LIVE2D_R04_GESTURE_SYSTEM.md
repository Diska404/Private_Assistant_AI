# R04 gesture system

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

Existing shared reactive performance drives head, eyes, body and expression profiles. The R04-A checkpoint does **not** implement the four requested arm gestures. There are no false shoulder/elbow/wrist controls in the developer UI.

| Requested gesture | Concrete blocker |
|---|---|
| Thinking / chin contact | New pointing/relaxed hand shape, elbow fold, forearm overlap and chin-contact corrective |
| Greeting / wave | Open-palm artwork, wrist orientation variants and completed shoulder underlap |
| Happy | Two arm lift variants and sleeve/torso correction |
| Confused | Open palm and asymmetric shoulder/body pose art |

After artwork is ready, author anticipation → action → hold → recovery → cooldown. Use explicit state/intent and generation ID, cancel on interruption, and return smoothly to idle. Keep contact anchors separate from pendulum physics. Do not substitute a repeated fist rotation for these completed gestures.

The developer override layer has clear ownership: main parameters before physics; manually selected hair/jacket outputs after physics; audio mouth values take precedence while audio is actually playing. Overrides are local QA and off by default.
