// Reversible secondary-motion layer. A file remaining unchanged does not grant modification rights.
export function secondaryCategory(name=''){
 name=name.toLowerCase();
 if(/backhair|long.?hair/.test(name))return 'long_hair';
 if(/bang|hair_[lrm]?f|前髪/.test(name))return 'bangs';
 if(/hair|髪/.test(name))return 'side_hair';
 if(/ribbon|bow|リボン/.test(name))return 'ribbon';
 if(/collar|襟/.test(name))return 'collar';
 if(/coat|jacket/.test(name))return 'jacket';
 if(/skirt|cloth|cltoh|スカート/.test(name))return 'hem';
 if(/accessory|pendant|earring|飾/.test(name))return 'accessory';
 return 'unclassified';
}
export const SECONDARY_PRESETS=Object.freeze({
 long_hair:{stiffness:1.15,dragForce:.34,gravityPower:.08,hitRadius:.006},
 bangs:{stiffness:2.8,dragForce:.52,gravityPower:.035,hitRadius:.004},
 side_hair:{stiffness:1.8,dragForce:.42,gravityPower:.06,hitRadius:.005},
 ribbon:{stiffness:2.3,dragForce:.48,gravityPower:.045,hitRadius:.004},
 collar:{stiffness:4.6,dragForce:.65,gravityPower:.025,hitRadius:.004},
 jacket:{stiffness:3.1,dragForce:.58,gravityPower:.07,hitRadius:.006},
 hem:{stiffness:2.2,dragForce:.48,gravityPower:.11,hitRadius:.006},
 accessory:{stiffness:2.7,dragForce:.5,gravityPower:.08,hitRadius:.004},
});
// Artist tuning candidates, not measured material constants. Units are VRM metres at height~1.6m.
const BODY_ZONES=[
 ['head','head',[0,.025,0],.054],['neck','neck',[0,0,0],.030],
 ['leftUpperArm','left_shoulder',[0,0,0],.043],['rightUpperArm','right_shoulder',[0,0,0],.043],
 ['chest','upper_back',[0,.018,-.025],.061],['chest','chest',[0,-.005,.018],.056],
 ['hips','hips',[0,.015,0],.078],
 ['leftUpperLeg','left_hip',[0,-.04,0],.049],['rightUpperLeg','right_hip',[0,-.04,0],.049],
];
export class PoseDiscontinuityGuard{
 reset(){this.previous=null}
 check(position,rotation,height=1.6){
  const p=this.previous;const current=[position.x,position.y,position.z,rotation.x,rotation.y,rotation.z,rotation.w];
  if(!current.every(Number.isFinite)){this.reset();return true}
  let discontinuous=false;if(p){const distance=Math.hypot(current[0]-p[0],current[1]-p[1],current[2]-p[2]);const dot=Math.abs(current[3]*p[3]+current[4]*p[4]+current[5]*p[5]+current[6]*p[6]);discontinuous=distance>height*.2||2*Math.acos(Math.min(1,dot))>1.1}
  this.previous=current;return discontinuous;
 }
}
export class SecondaryMotionLayer{
 constructor(vrm,V,{allowModification=false,height=1.6}={}){
  this.vrm=vrm;this.V=V;this.height=height;this.allowed=allowModification===true;
  this.items=Array.from(vrm.springBoneManager?.joints||[],joint=>{
   let p=joint.bone,category='unclassified';for(let i=0;p&&i<8&&category==='unclassified';i++,p=p.parent)category=secondaryCategory(p.name);
   return {joint,category,settings:{...joint.settings,gravityDir:joint.settings.gravityDir.clone()},groups:joint.colliderGroups};
  });
  this.colliders=[];this.active=false;this.calls=0;this.contacts=0;this.maxPenetration=0;
  this.status=this.allowed?'source':'restricted_source_no_physics_edits';
 }
 setEnabled(enabled){
  if(!enabled){this.restore();return false}
  if(!this.allowed){this.status='restricted_source_no_physics_edits';return false}
  if(this.active)return true;
  const {THREE,VRMSpringBoneCollider,VRMSpringBoneColliderShapeSphere}=this.V;
  this.vrm.scene.updateMatrixWorld(true);const layer=this;
  class MeasuredSphere extends VRMSpringBoneColliderShapeSphere{
   calculateCollision(matrix,position,radius,target){const distance=super.calculateCollision(matrix,position,radius,target);layer.calls++;if(distance<0){layer.contacts++;layer.maxPenetration=Math.max(layer.maxPenetration,-distance)}return distance}
  }
  const scaleVector=new THREE.Vector3();
  for(const [humanoid,name,offset,radius]of BODY_ZONES){
   const bone=this.vrm.humanoid?.getRawBoneNode(humanoid);if(!bone)continue;
   bone.getWorldScale(scaleVector);const localScale=Math.max(.001,Math.abs(scaleVector.x));
   const collider=new VRMSpringBoneCollider(new MeasuredSphere({offset:new THREE.Vector3(...offset).multiplyScalar(this.height/localScale),radius:radius*this.height/localScale}));
   collider.name='Leva_R2_'+name;bone.add(collider);this.colliders.push(collider);
  }
  this.group={name:'Leva R2 body collision',colliders:this.colliders};
  for(const item of this.items){
   const p=SECONDARY_PRESETS[item.category];if(!p)continue;
   Object.assign(item.joint.settings,p,{hitRadius:p.hitRadius*this.height/1.6});
   item.joint.colliderGroups=[...item.groups,this.group];
   // addJoint is idempotent (Set); refreshes the public manager's dependency ordering.
   this.vrm.springBoneManager.addJoint(item.joint);
  }
  this.active=true;this.status='development_fixture_calibration';this.vrm.scene.updateMatrixWorld(true);this.vrm.springBoneManager?.reset();return true;
 }
 beginWindow(){this.calls=0;this.contacts=0;this.maxPenetration=0}
 summary(){const categories={};for(const item of this.items)categories[item.category]=(categories[item.category]||0)+1;
  return {status:this.status,active:this.active,allowed:this.allowed,categories,added_colliders:this.colliders.length,collision_tests:this.calls,contacts_before_projection:this.contacts,max_preprojection_penetration:this.maxPenetration,
   scope:'spring-tail sphere tests, not skinned-mesh clipping certification'};
 }
 restore(){
  if(!this.active)return;
  for(const item of this.items){Object.assign(item.joint.settings,item.settings);item.joint.colliderGroups=item.groups;this.vrm.springBoneManager?.addJoint(item.joint)}
  for(const collider of this.colliders)collider.removeFromParent();this.colliders=[];this.active=false;this.status='source';this.vrm.scene.updateMatrixWorld(true);this.vrm.springBoneManager?.reset();
 }
 dispose(){this.restore();this.items=[]}
}
