# R04 artwork audit

Checkpoint 0.44.0 / R04-A, 26 October 2026. **R04 and R05 are not complete.** Source artwork and R03 remain preserved; no generative images or new model downloads.

The actual R03 AOM, native export and source atlas were inspected. Forty-four parameters and fifty-nine deformers remain. The base illustration was one mesh containing face base, hair, shoulders, body and arms. Existing eye/mouth/brow overlays and the optional reconstructed eye were already separate.

A manually traced, reversible partition now produces **twelve visible layers** from that base mesh. Original overlays are retained, giving **57 ArtMesh**. There are no added parameters or deformers merely to increase counts. Two 2048×2048 atlases use about 32 MiB of uncompressed RGBA texture storage, versus 16 MiB before; this excludes renderer overhead. Tight crops are packed with MaxRects and four-pixel gutters. There is no upscaling, sharpening filter or claim of premium repainting.

OpenRaster layered source, individual PNGs, editable SVG mask paths, new AOM and MOC3 5.0 are private. The source atlas and twelve expressions are unchanged. The original base raster equals the assembled separated raster pixel-for-pixel. GPU resampling and new tessellation mean this is not a claim that all screenshot pixels are identical.

**Remaining:** precise artistic refinement of cut boundaries, separated remaining hair, new hidden-surface art, perspective correctives and premium face/costume repainting. File `ARTWORK_TASKS.json` and a layered UNPAINTED task ORA identify real missing artwork. They contain no completed new hands or legs.

See [layer inventory](LEVA_LIVE2D_R04_LAYER_SEPARATION.md), [QA](LEVA_LIVE2D_R04_VISUAL_QA.md) and [acceptance](LEVA_LIVE2D_USER_ACCEPTANCE.md).

Authoring dependencies used locally: msgpack 1.1.2 and Pillow 13.0.0; see root requirements-avatar-authoring.txt. No dependency installation or SDK redistribution was performed.
