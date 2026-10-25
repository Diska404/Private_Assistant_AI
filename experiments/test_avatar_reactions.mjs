import assert from'node:assert/strict';
import{ReactivePerformance,R2_FACE_PROFILES,REACTIONS}from'../app/leva_web/avatar_reactions.js';
import{VRMAvatarProvider}from'../app/leva_web/vrm_avatar.js';
const supported=['happy','sad','angry','relaxed','aa','ih','ou','blink','blinkLeft','blinkRight'];
const c=new ReactivePerformance({supported});c.configure('speaking','teasing');c.triggerReaction('playful');
let peak=0,wink=false;
for(let i=0;i<300;i++){const o=c.update(1/120,.5,{audioPlaying:true,features:{zeroCrossingRate:.04,available:true}});peak=Math.max(peak,Math.abs(o.headZ));wink||=o.weights.blinkLeft>.2;assert(o.weights.aa+o.weights.ih+o.weights.ou<=.8);assert(Object.values(o.weights).every(v=>Number.isFinite(v)&&v>=0&&v<=1))}
assert(peak<.09);assert(wink);assert(c.weights.ou>.01);assert.equal(c.output.reaction,'none');
c.configure('interrupted','neutral');for(let i=0;i<100;i++)c.update(1/120,1,{audioPlaying:true});assert.equal(c.weights.aa+c.weights.ih+c.weights.ou,0);
c.configure('idle','laugh');for(let i=0;i<120;i++)c.update(1/60,1,{audioPlaying:false});assert.equal(c.weights.aa+c.weights.ih+c.weights.ou,0);
const restricted=new ReactivePerformance({supported:['aa','blink']});restricted.configure('idle','surprised');restricted.triggerReaction('playful');for(let i=0;i<120;i++)restricted.update(1/60);assert(restricted.output.limited);assert.equal(restricted.weights.surprised,0);assert.equal(restricted.weights.blinkLeft,0);
function motion(fps){const v=new ReactivePerformance({supported});v.configure('idle','gentle');v.triggerReaction('greeting');for(let i=0;i<fps;i++)v.update(1/fps);return v.output}
const a=motion(60),b=motion(120);assert(Math.abs(a.headX-b.headX)<.002);assert(Math.abs(a.weights.happy-b.weights.happy)<.005);
let calls=0;const p=new VRMAvatarProvider({});p.performance.triggerReaction=()=>{calls++;return true};for(let i=0;i<20;i++)p.update({state:'idle',generation_id:1,reaction:'greeting',reaction_id:4});assert.equal(calls,1);p.update({state:'idle',generation_id:1,reaction:'playful',reaction_id:5,reaction_age_ms:9000});assert.equal(calls,1);
p.setPerformanceVersion('r1');assert.equal(p.performance.triggerReaction,undefined);p.setPerformanceVersion('r2');assert.equal(typeof p.performance.triggerReaction,'function');assert.throws(()=>p.triggerReaction('execute_shell'),/invalid/);
const sustained=new ReactivePerformance({supported});sustained.configure('idle','neutral');for(let i=0;i<7200;i++){if(i%300===0)sustained.triggerReaction('greeting');const o=sustained.update(1/120);assert(Math.abs(o.headX)<.1&&Math.abs(o.headZ)<.1)}
sustained.reset();assert.equal(sustained.baseOpenness,0);assert.equal(sustained.pendingReaction,null);
assert.equal(Object.keys(R2_FACE_PROFILES).length,24);assert.equal(Object.keys(REACTIONS).length,9);
console.log(JSON.stringify({passed:23,profiles:24,new_morphs:0,reaction_types:9,repeated_poll_deduplicated:true,silent_mouth_closed:true,sustained_pose_bounded:true,comparison_fps:[60,120]}));
