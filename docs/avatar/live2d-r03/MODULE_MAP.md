# R03 module relationships

```mermaid
flowchart LR
 A[Private R02 AOM + source expressions] --> B[Core geometry baking]
 B --> C[R03 AOM builder]
 C --> D[Ayatsuri MOC3 5.0 export]
 D --> E[Hash-pinned private asset registry]
 P[External editable physics3] --> E
 E --> F[Authenticated WebBridge]
 F --> G[Native Cubism renderer]
 R[Reactive performance / voice levels] --> H[R03 numeric controls]
 H --> G
 G --> I[Post-render event]
 I --> J[Opaque recording compositor]
 G --> K[Bounded metrics / rig QA]
```

`live2d_rig_controls.js` supplies limited head/body/breath motion and the opt-in eye. The provider applies source expression recipes first, overlays blink/gaze and audio mouth, applies R03 controls, then the fixed-step Cubism physics solver, and renders. A frame event captures native WebGL before its buffer may be discarded. On disposal the recording removes its event listener and tracks; source media and SDK remain external.
