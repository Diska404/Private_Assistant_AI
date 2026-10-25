// Reversible runtime controls, independent of persona text and host permissions.
export const QUALITY=Object.freeze({
 ultra:{fps:120,dpr:1.75,physicsHz:60,motion:1},
 premium:{fps:60,dpr:2,physicsHz:60,motion:1},
 balanced:{fps:30,dpr:1.5,physicsHz:30,motion:.7},
 gaming:{fps:30,dpr:1,physicsHz:15,motion:.35},
 eco:{fps:15,dpr:1,physicsHz:10,motion:.15},
});
export const LIGHTING=Object.freeze({
 default:{ambient:1.6,key:1.5,rim:.7,color:0xfff1e7},warm:{ambient:1.45,key:1.6,rim:.6,color:0xffdab7},
 cool:{ambient:1.5,key:1.45,rim:.9,color:0xd4e9ff},night:{ambient:.9,key:1.1,rim:.55,color:0xc8d4ff},
 streaming:{ambient:1.7,key:1.7,rim:.85,color:0xffedf5},performance:{ambient:1.8,key:1.2,rim:0,color:0xffffff},
 premium_studio:{ambient:1.05,key:1.5,rim:.45,fill:.35,color:0xfff2e8},
 soft_anime:{ambient:1.35,key:1.15,rim:.28,fill:.28,color:0xfff5f1},
 dark_environment:{ambient:.18,key:.45,rim:.24,fill:.08,color:0xb3c9f5},
});
export function quality(value){return QUALITY[value==='performance'?'premium':value]||QUALITY.balanced}
export function damp(current,target,delta,speed=10){return current+(target-current)*(1-Math.exp(-Math.max(0,Math.min(delta,.1))*speed))}
export function expressionTargets(state,expression){
 const map={smile:'happy',laugh:'happy',playful:'happy',shy:'relaxed',embarrassed:'relaxed',sleepy:'relaxed',confused:'surprised',curious:'surprised'};
 const selected=map[expression]||expression;
 const weight=['laugh','happy'].includes(expression)?.65:['confused','curious'].includes(expression)?.2:.4;
 return Object.fromEntries(['happy','sad','angry','relaxed','surprised'].map(k=>[k,k===selected?weight:state==='listening'&&k==='relaxed'?.12:0]));
}
export class FixedPhysics{
 constructor(){this.accumulator=0;this.steps=0;this.discardedSeconds=0;this.cappedFrames=0}
 update(delta,hz,callback){
  if(!Number.isFinite(delta)||!Number.isFinite(hz)||hz<=0)return 0;
  this.discardedSeconds+=Math.max(0,delta-.1);this.accumulator+=Math.max(0,Math.min(delta,.1));const step=1/hz;let count=0;
  while(this.accumulator+1e-9>=step&&count<4){callback(step);this.accumulator=Math.max(0,this.accumulator-step);count++;this.steps++}
  if(this.accumulator+1e-9>=step){const dropped=Math.floor((this.accumulator+1e-9)/step)*step;this.discardedSeconds+=dropped;this.accumulator=Math.max(0,this.accumulator-dropped);this.cappedFrames++}
  return count;
 }
 reset(){this.accumulator=0}
}
export class MaterialLayer{
 constructor(materials=[],{maxAnisotropy=4}={}){this.maxAnisotropy=maxAnisotropy;this.textures=new Map();this.items=materials.filter(m=>m.isMToonMaterial).map(m=>{for(const value of Object.values(m))if(value?.isTexture&&!this.textures.has(value))this.textures.set(value,{anisotropy:value.anisotropy});return {m,original:{shadingToonyFactor:m.shadingToonyFactor,shadingShiftFactor:m.shadingShiftFactor,giEqualizationFactor:m.giEqualizationFactor,...(typeof m.outlineWidthFactor==='number'?{outlineWidthFactor:m.outlineWidthFactor}:{})}}})}
 apply(name='source'){
  if(!['source','soft_anime','premium_r2'].includes(name))throw new Error('invalid_material_preset');
  for(const [texture,original]of this.textures){texture.anisotropy=name==='premium_r2'?Math.min(4,this.maxAnisotropy):original.anisotropy;texture.needsUpdate=true}
  for(const {m,original} of this.items){Object.assign(m,original);if(name!=='source'){m.shadingToonyFactor=name==='premium_r2'?.78:.82;m.giEqualizationFactor=name==='premium_r2'?.82:.85;if(/skin/i.test(m.name))m.shadingShiftFactor=name==='premium_r2'?-.07:-.08;if(name==='premium_r2'&&typeof original.outlineWidthFactor==='number'&&original.outlineWidthFactor>0)m.outlineWidthFactor=Math.min(original.outlineWidthFactor,/face|skin/i.test(m.name)?.00045:.0012)}}
 }
 restore(){this.apply('source')}
}
