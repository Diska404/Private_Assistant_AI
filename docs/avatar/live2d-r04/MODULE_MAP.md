# R04-A module relationships

```mermaid
flowchart LR
  A[Private R03 AOM / source atlas] --> B[Manual trace ownership masks]
  B --> C[OpenRaster + editable paths]
  B --> D[Packed second atlas + separated ArtMesh]
  D --> E[Private R04-A AOM]
  E --> F[Ayatsuri round-trip / MOC3 5.0]
  F --> G[Hash-pinned local registry]
  G --> H[Authenticated WebBridge]
  H --> I[Native renderer]
  J[Shared reactive performance] --> I
  K[Developer RigOverrides] --> I
  I --> L[Selected mesh wireframe / metrics]
  I --> M[Actual audio lip-sync / recording]
  C --> N[Unpainted corrective tasks]
  N -. pending artwork .-> O[Perspective / arm gesture / full-body rig]
```

The second atlas contains cut source pixels, not newly painted hidden surfaces. The QA module receives a schema from Core, clamps only known IDs and does not create unsupported controls. Source switching re-applies chosen native settings. Original artwork, 3D and runtime selection remain preserved. No new avatar agent runtime was added.
