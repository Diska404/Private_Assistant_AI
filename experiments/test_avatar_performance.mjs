import assert from 'node:assert/strict';
import{NaturalPerformance,FACE_PROFILES}from'../app/leva_web/avatar_performance.js';
const supported=['happy','sad','angry','relaxed','aa','blink'];
const c=new NaturalPerformance({supported});c.configure('speaking','happy');
for(let i=0;i<60;i++)c.update(1/60,.7,{audioPlaying:false});assert.equal(c.weights.aa,0,'silent backend speaking label must not animate speech');
c.configure('speaking','soft_smile');for(let i=0;i<120;i++)c.update(1/60,.45,{audioPlaying:true});assert(c.weights.aa>.3&&c.weights.aa<.8);
c.configure('interrupted','neutral');for(let i=0;i<60;i++)c.update(1/60,.8,{audioPlaying:true});assert.equal(c.weights.aa,0);
const blending=new NaturalPerformance({supported});blending.configure('idle','happy');blending.update(1/60);assert(blending.weights.happy>0&&blending.weights.happy<.1);
for(let i=0;i<120;i++)blending.update(1/60);assert(blending.weights.happy>.5&&blending.weights.happy<=.52);
blending.configure('idle','surprised');for(let i=0;i<60;i++)blending.update(1/60);assert(blending.output.limited);assert.equal(blending.weights.surprised,0);
function run(fps){const v=new NaturalPerformance({supported,seed:404});v.configure('listening','curious');for(let i=0;i<fps*10;i++)v.update(1/fps);return v.output}
const a=run(30),b=run(60);assert(Math.abs(a.headY-b.headY)<.002);assert(Math.abs(a.headZ-b.headZ)<.002);
const blinking=new NaturalPerformance();let closures=0,was=false;
for(let i=0;i<30*60;i++){const o=blinking.update(1/60);const now=o.weights.blink>.85;if(now&&!was)closures++;was=now;for(const v of Object.values(o.weights))assert(Number.isFinite(v)&&v>=0&&v<=1)}
assert(closures>=4&&closures<=9);assert.notDeepEqual(FACE_PROFILES.curious,FACE_PROFILES.confused);assert.notDeepEqual(FACE_PROFILES.shy,FACE_PROFILES.thinking);
blinking.update(NaN,Infinity);assert(Object.values(blinking.weights).every(Number.isFinite));
console.log(JSON.stringify({passed:15,audio_gated:true,frame_rate_comparison:[30,60],blink_closures_in_30s:closures,unsupported_morphs_not_fabricated:true}));
