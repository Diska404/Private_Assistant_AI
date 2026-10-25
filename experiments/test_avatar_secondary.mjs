import assert from 'node:assert/strict';
import * as V from '../app/leva_web/avatar-vendor.js';
import {SecondaryMotionLayer,secondaryCategory,PoseDiscontinuityGuard}from'../app/leva_web/avatar_secondary.js';
const {THREE,VRMSpringBoneManager,VRMSpringBoneJoint}=V;
const scene=new THREE.Scene(),head=new THREE.Bone(),hair=new THREE.Bone(),tip=new THREE.Bone();
head.name='Head';head.position.y=1.4;hair.name='BackHairC1';hair.position.set(.10,.04,0);tip.position.set(-.08,-.06,0);scene.add(head);head.add(hair);hair.add(tip);scene.updateMatrixWorld(true);
const manager=new VRMSpringBoneManager(),joint=new VRMSpringBoneJoint(hair,tip);manager.addJoint(joint);manager.setInitState();
const vrm={scene,springBoneManager:manager,humanoid:{getRawBoneNode:name=>name==='head'?head:null}};
const before={...joint.settings},groups=joint.colliderGroups;
const locked=new SecondaryMotionLayer(vrm,V,{allowModification:false});assert.equal(locked.setEnabled(true),false);assert.equal(manager.colliders.length,0);assert.deepEqual(joint.settings,before);
const layer=new SecondaryMotionLayer(vrm,V,{allowModification:true});assert.equal(layer.setEnabled(true),true);assert.equal(manager.colliders.length,1);assert.equal(joint.settings.stiffness,1.15);
for(let i=0;i<1200;i++){head.rotation.y=Math.sin(i*.03)*.4;manager.update(1/120)}
assert(layer.calls>0);assert(layer.contacts>0);assert(Number.isFinite(hair.quaternion.w));assert(Math.abs(hair.quaternion.length()-1)<1e-6);
layer.restore();assert.equal(manager.colliders.length,0);assert.deepEqual(joint.settings,before);assert.equal(joint.colliderGroups,groups);layer.setEnabled(true);assert.equal(manager.colliders.length,1);layer.dispose();assert.equal(manager.colliders.length,0);
assert.equal(secondaryCategory('joint_bone_Collar_R01'),'collar');assert.equal(secondaryCategory('other'),'unclassified');
console.log(JSON.stringify({passed:17,uses_actual_three_vrm_solver:true,simulation_steps:1200,collision_observed:true,permission_gate_enforced:true,reversible:true}));

const guard=new PoseDiscontinuityGuard(),pos=new THREE.Vector3(),q=new THREE.Quaternion();assert.equal(guard.check(pos,q),false);pos.x=1;assert.equal(guard.check(pos,q),true);guard.reset();assert.equal(guard.check(pos,q),false);q.setFromAxisAngle(new THREE.Vector3(0,1,0),2);assert.equal(guard.check(pos,q),true);
