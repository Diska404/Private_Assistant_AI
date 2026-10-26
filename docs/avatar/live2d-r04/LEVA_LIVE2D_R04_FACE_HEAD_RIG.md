# R04 face and head rig

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

The R03 head X/Y/Z controller and source expressions are retained. The face-base/nose region and visible neck are now separate artwork layers, but **new perspective-aware keyforms are not finished**. Eye reconstruction remains opt-in; source wink remains default.

The real exported model passed 54 combined X/Y/Z and eye-open poses. Forty-five original non-base mesh geometries match R03 exactly at neutral (maximum delta 0). This validates preservation, not new perspective.

Needed next: left/right cheek and jaw silhouettes, near/far eye artwork, nose positions, exposed ear edges and chin-up/down correctives. First support a restrained yaw range; validate matching eyes/nose/jaw/hair as one projection before expanding to extremes. No full yaw or hidden-side illustration has been fabricated.

Developer sliders expose only actual model parameter limits; they do not create missing eyelid, mouth-corner or arm channels.
