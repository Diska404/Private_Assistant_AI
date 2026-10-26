import assert from'node:assert/strict';
import{rigControls}from'../app/leva_web/live2d_rig_controls.js';
const p={headX:1,headY:-1,headZ:1,spineY:1,chestX:-1,weights:{blink:0,happy:.7,angry:.1}};
const a=rigControls(p,{time:1200});assert.equal(a.ParamAngleX,-30);assert.equal(a.ParamAngleY,-30);assert.equal(a.ParamEyeLOpen,0);assert.equal(a.ParamLeftEyeMood,.6);
assert.equal(rigControls(p,{leftEye:true}).ParamEyeLOpen,1);
assert.equal(rigControls({...p,weights:{blink:1}},{leftEye:true}).ParamEyeLOpen,0);
assert.equal(rigControls(p,{leftEye:true,sleeping:true}).ParamEyeLOpen,0);
const f=rigControls(p,{freeze:true,time:5000});for(const id of ['ParamAngleX','ParamAngleY','ParamAngleZ','ParamBodyAngleX','ParamBodyAngleZ','ParamBreath'])assert.equal(f[id],0);
for(let t=0;t<12000;t+=100){const q=rigControls(p,{qaElapsed:t,time:t,leftEye:true});assert(Object.values(q).every(Number.isFinite));assert(q.ParamBreath>=0&&q.ParamBreath<=1)}
console.log('Live2D R03 controls: clamping, opt-in eye, sleep, freeze and QA passed');
