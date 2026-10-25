// Pinned dependencies: three 0.186.1, @pixiv/three-vrm 3.5.5; esbuild 0.28.2.
import * as THREE from 'three';
export {THREE};
export {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
export {OrbitControls} from 'three/addons/controls/OrbitControls.js';
export {VRMLoaderPlugin,VRMUtils} from '@pixiv/three-vrm';
export {VRMSpringBoneCollider,VRMSpringBoneColliderShapeSphere,VRMSpringBoneJoint,VRMSpringBoneManager,
 VRMSpringBoneColliderHelper,VRMSpringBoneJointHelper} from '@pixiv/three-vrm';
