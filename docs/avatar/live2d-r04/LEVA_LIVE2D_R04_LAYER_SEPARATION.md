# R04 layer separation

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

| Visible extracted layer | Source pixels | Hidden surfaces |
|---|---:|---|
| BODY/Torso and hair remainder · still fused | 747892 | Unpainted |
| COSTUME/Collar and tie · partial | 48517 | Unpainted |
| HEAD/Neck · visible only | 7627 | Unpainted |
| HEAD/Face base · nose; no corrective side art | 79187 | Unpainted |
| HAIR/Side hair · visible left silhouette | 16158 | Unpainted |
| HAIR/Back hair · visible silhouette | 73250 | Unpainted |
| HAIR/Hair ribbon · visible only | 16725 | Unpainted |
| BODY/Left upper arm and cuff | 126367 | Unpainted |
| BODY/Left forearm · cropped; hand absent | 32068 | Unpainted |
| BODY/Right upper arm · partial sleeve | 32640 | Unpainted |
| BODY/Right forearm · bionic | 39499 | Unpainted |
| BODY/Right hand · visible fist | 21856 | Unpainted |

Original face overlays, brows, fringe and mirrored left-eye construction remain separate and untouched. Labels distinguish character-left from viewer-left. The bionic fist is character-right.

Binary ownership masks are manually authored in base-sprite coordinates, 1182×1686. A two-pixel underlap only inside fully opaque source pixels prevents bilinear seams without inventing hidden surfaces. New grids use the existing UV-to-parent mapping and inherit the R03 parent chain. No separate arm-angle parameter is claimed.

The torso remainder is explicitly still fused. The left forearm ends at the image crop, and no complete left hand is available. Cut PNGs are not a finished premium PSD or proof of movable joints. Refine ownership masks in the editable SVG and paint occluded surfaces in a raster editor before assigning large motions.
