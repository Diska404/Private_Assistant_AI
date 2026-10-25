import assert from'node:assert/strict';
import{FramePacer,AvatarFrameMetrics,FrameLoadGovernor}from'../app/leva_web/avatar_timing.js';
import{FixedPhysics,quality}from'../app/leva_web/avatar_dynamics.js';
for(const [refresh,target]of [[60,30],[144,120],[120,120],[60,120]]){
 const p=new FramePacer();let frames=0;for(let i=0;i<refresh*10;i++)if(p.accept(i*1000/refresh,target))frames++;
 assert(Math.abs(frames-Math.min(target,refresh)*10)<2,`${refresh}/${target}: ${frames}`);
}
const p=new FramePacer();p.accept(0,120);assert(p.accept(500,120).stalled);
const solver=new FixedPhysics();let steps=0;for(let i=0;i<600;i++)solver.update(1/60,120,()=>steps++);assert.equal(steps,1200);
assert(solver.update(1,120,()=>{})<=4);assert(solver.discardedSeconds>.9);assert(solver.accumulator<1/120);assert.equal(solver.update(NaN,120,()=>{}),0);
const stats=new AvatarFrameMetrics(30);for(let i=0;i<300;i++)stats.push(1000/60,2,.3,2);const m=stats.snapshot(120);assert.equal(m.samples,30);assert(Math.abs(m.observed_fps-60)<.01);assert.equal(m.over_budget_frames,30);assert.equal(quality('ultra').fps,120);assert.equal(quality('ultra').physicsHz,60);
console.log(JSON.stringify({passed:16,target_120_real_logic:true,refresh_limited_test:true,solver_120Hz_steps:steps,bounded_storage:true}));

const governor=new FrameLoadGovernor();for(let i=0;i<4;i++)governor.observe({samples:240,observed_fps:75,frame_p95_ms:19},120,true);assert(governor.fallback);assert.equal(governor.observe({samples:240,observed_fps:60,frame_p95_ms:17},120,true),60);assert.equal(governor.observe({},120,false),120);
