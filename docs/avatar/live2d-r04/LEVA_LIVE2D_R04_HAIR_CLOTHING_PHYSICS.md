# R04 hair and clothing physics

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

The four verified R03 groups are reused: front hair, back hair, side hair and jacket. No unsupported extra pendulum channels were added. R04-A extracts visible back/side hair, ribbon and collar sections into layers, enabling later independent bindings.

Independent ribbon roots/tails, collar motion and clothing collision are **pending**. Complete underlying artwork and corrective masking first. Two-pixel texture underlap is a sampling fix, not a joint-contact or cloth-collision solution.

The real 60 Hz solver ran in the native renderer; combined-parameter tests stayed finite. CPU timing is reported separately from frame pacing. Native model switching now restores chosen freeze, speed, expression, solver rate, adaptive mode and render scale.
