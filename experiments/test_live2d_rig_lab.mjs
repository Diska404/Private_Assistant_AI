import assert from'node:assert/strict';
import{RigOverrides}from'../app/leva_web/live2d_rig_lab.js';
const qa=new RigOverrides([{id:'ParamAngleX',min:-30,max:30},{id:'ParamMouthOpenY',min:0,max:1},{id:'ParamHairBack',min:-1,max:1}]);
assert.throws(()=>qa.set('ParamMissingArm',2));assert.throws(()=>qa.set('ParamAngleX',NaN));qa.set('ParamAngleX',999);qa.set('ParamMouthOpenY',.7);qa.set('ParamHairBack',-9);
let values={};const write=(k,v)=>values[k]=v;qa.apply(write);assert.deepEqual(values,{});qa.enabled=true;qa.apply(write,{audioPlaying:true});assert.deepEqual(values,{ParamAngleX:30});qa.apply(write,{physics:true,audioPlaying:true});assert.equal(values.ParamHairBack,-1);assert(!('ParamMouthOpenY'in values));
qa.apply(write);assert.equal(values.ParamMouthOpenY,.7);qa.clear();values={};qa.apply(write);assert.deepEqual(values,{});console.log('Rig QA: unsupported controls rejected, bounds, ownership, live audio priority and reset passed');
