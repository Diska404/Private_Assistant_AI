// Procedural calibration of existing avatar channels. No model training or asset edits.
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const ease=(v)=>{v=clamp(v);return v*v*(3-2*v)};
const follow=(current,target,dt,speed)=>current+(target-current)*(1-Math.exp(-Math.min(.1,Math.max(0,dt))*speed));
export const FACE_CHANNELS=Object.freeze(['happy','sad','angry','relaxed','surprised','blink','aa']);
const EMOTION_CHANNELS=FACE_CHANNELS.slice(0,5);
export const FACE_PROFILES=Object.freeze({
 neutral:{},soft_smile:{happy:.22},happy:{happy:.52,relaxed:.06},laugh:{happy:.68,relaxed:.12},
 curious:{happy:.08,sad:.025},confused:{angry:.11,sad:.10},thinking:{relaxed:.10,angry:.025},
 surprised:{surprised:.5},shy:{happy:.14,relaxed:.27},embarrassed:{happy:.12,relaxed:.22},
 playful:{happy:.37,angry:.02},angry:{angry:.38},sad:{sad:.42},sleepy:{relaxed:.32},
 attentive:{happy:.05,relaxed:.08},excited:{happy:.60,relaxed:.075}
});
export const PERFORMANCE_STATES=Object.freeze(['idle','listening','thinking','speaking','reacting','transitioning','sleeping','interrupted','error']);
export class NaturalPerformance{
 constructor({seed=404,supported=null}={}){
  this.seed=seed;this.supported=supported?new Set(supported):null;this.time=0;this.nextBlink=3.1;this.blinkStart=-1;this.blinkDuration=.23;
  this.state='idle';this.requested='neutral';this.profile='neutral';this.profileAge=1;this.speech=0;
  this.weights={happy:0,sad:0,angry:0,relaxed:0,surprised:0,blink:0,aa:0};
  this.output={weights:this.weights,headX:0,headY:0,headZ:0,chestX:0,spineY:0,gazeX:0,gazeY:0,posture:0,state:'idle',profile:'neutral',transitioning:false,limited:false};
 }
 random(){this.seed=(Math.imul(1664525,this.seed)+1013904223)>>>0;return this.seed/4294967296}
 configure(state='idle',expression='neutral'){
  this.state=PERFORMANCE_STATES.includes(state)?state:'idle';
  this.requested=Object.hasOwn(FACE_PROFILES,expression)?expression:expression==='smile'?'soft_smile':'neutral';
 }
 reset(){this.speech=0;this.blinkStart=-1;this.nextBlink=this.time+2.8;for(const k of Object.keys(this.weights))this.weights[k]=0}
 update(dt,level=0,{speed=1,motion=1,audioPlaying=false}={}){
  dt=Number.isFinite(dt)?clamp(dt,0,.1):0;level=Number.isFinite(level)?level:0;this.time+=dt*clamp(speed,.1,1);this.profileAge+=dt;
  const state=this.state,desired=this.requested==='neutral'?(state==='listening'?'attentive':state==='thinking'?'thinking':state==='sleeping'?'sleepy':'neutral'):this.requested;
  // Short cooldown prevents rapid label chatter; weights still blend continuously.
  if(desired!==this.profile&&this.profileAge>=.35){this.profile=desired;this.profileAge=0}
  const profile=FACE_PROFILES[this.profile]||FACE_PROFILES.neutral;
  const active=audioPlaying&&!['interrupted','sleeping'].includes(state);
  let limited=false;
  for(const key of EMOTION_CHANNELS){
   let target=profile[key]||0;
   if(active&&(key==='happy'||key==='sad'||key==='angry'))target*=.72;
   if(this.supported&&!this.supported.has(key)){if(target)limited=true;target=0}
   this.weights[key]=follow(this.weights[key],target,dt,target>this.weights[key]?5.2:4.2);
  }
  if(this.time>=this.nextBlink&&this.blinkStart<0){this.blinkStart=this.time;this.nextBlink=this.time+3.5+this.random()*2.6}
  let blink=0;
  if(this.blinkStart>=0){const t=this.time-this.blinkStart;if(t<.065)blink=ease(t/.065);else if(t<.095)blink=1;else if(t<this.blinkDuration)blink=1-ease((t-.095)/(this.blinkDuration-.095));else this.blinkStart=-1}
  const sleepy=state==='sleeping'?.72:this.profile==='sleepy'?.28:0;
  this.sleepClosure=follow(this.sleepClosure||0,sleepy,dt,5);
  this.weights.blink=Math.max(blink,this.sleepClosure);
  // Only current playback drives the mouth. No timer-created syllables/viseme claim.
  const raw=active&&level>.018?Math.pow(clamp((level-.018)/.65),.8)*.78:0;
  this.weights.aa=follow(this.weights.aa,raw,dt,raw>this.weights.aa?25:13);
  if(!active&&this.weights.aa<.005)this.weights.aa=0;
  this.speech=follow(this.speech,active?clamp(level):0,dt,6);
  const t=this.time,o=this.output,scale=clamp(motion)* (state==='sleeping'?.35:1);
  const listening=state==='listening'?1:0,thinking=state==='thinking'?1:0,shy=['shy','embarrassed'].includes(this.profile)?1:0;
  o.headX=follow(o.headX,(Math.sin(t*1.23)*.008+this.speech*Math.sin(t*2.7)*.028+shy*.035)*scale,dt,5);
  o.headY=follow(o.headY,(Math.sin(t*.41)*.018+thinking*.07)*scale,dt,3.8);
  o.headZ=follow(o.headZ,(Math.sin(t*.67)*.009+listening*.025+(['curious','confused'].includes(this.profile)?.035:0))*scale,dt,4.3);
  o.chestX=follow(o.chestX,Math.sin(t*1.45)*.0055*scale,dt,5);
  o.spineY=follow(o.spineY,Math.sin(t*.27)*.009*scale,dt,3);
  o.gazeX=follow(o.gazeX,thinking?.065:Math.sin(t*.32)*.012,dt,4);
  o.gazeY=follow(o.gazeY,shy?-.025:thinking?.018:Math.sin(t*.47)*.006,dt,4);
  o.posture=follow(o.posture,listening*.018-thinking*.012,dt,4);
  o.state=state;o.profile=this.profile;o.transitioning=this.profileAge<.6;o.limited=limited;
  return o;
 }
}
