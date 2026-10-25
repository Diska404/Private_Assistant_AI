import{NaturalPerformance,FACE_PROFILES}from'./avatar_performance.js';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const follow=(a,b,dt,speed=5)=>a+(b-a)*(1-Math.exp(-Math.min(.1,dt)*speed));
export const R2_FACE_PROFILES=Object.freeze({...FACE_PROFILES,
 soft_smile:{happy:.18},happy:{happy:.44,relaxed:.035},laugh:{happy:.57,relaxed:.05},
 gentle:{happy:.13,relaxed:.07},concerned:{sad:.16,happy:.035},relieved:{happy:.23,relaxed:.10},
 proud:{happy:.30,angry:.025},apologetic:{sad:.17,relaxed:.035},teasing:{happy:.32,angry:.025},
 disappointed:{sad:.28},grateful:{happy:.27,relaxed:.05}
});
export const REACTIONS=Object.freeze({
 greeting:{seconds:1.6,nod:.055,tilt:.035,smile:.14},nod:{seconds:1.1,nod:.045},
 ponder:{seconds:1.8,tilt:.035,yaw:.025},comfort:{seconds:1.8,nod:.025,tilt:.025,smile:.08},
 celebrate:{seconds:1.6,nod:.04,tilt:.025,shoulder:.018,smile:.23},
 playful:{seconds:1.6,tilt:.04,yaw:.02,wink:.6,smile:.18},
 apology:{seconds:1.5,nod:.055},surprise:{seconds:1.0,nod:-.04},interrupted:{seconds:.7,nod:-.015}
});
export const R2_FACE_CHANNELS=Object.freeze(['happy','sad','angry','relaxed','surprised','blink','blinkLeft','blinkRight','aa','ih','ou']);
const ALIASES={gentle:'soft_smile',concerned:'sad',relieved:'soft_smile',proud:'happy',apologetic:'sad',teasing:'playful',disappointed:'sad',grateful:'happy'};
export class ReactivePerformance extends NaturalPerformance{
 constructor(options={}){super(options);Object.assign(this.weights,{blinkLeft:0,blinkRight:0,ih:0,ou:0});this.r2Profile='neutral';this.r2Age=1;this.previousEmotion={};this.reaction=null;this.pendingReaction=null;this.reactionCooldown=1;this.reactionSequence=0;this.saccadeAt=1.8;this.gazeTargetX=0;this.gazeTargetY=0}
 configure(state='idle',expression='neutral'){
  if(state==='sleeping'){this.reaction=null;this.pendingReaction=null}
  if(this.state!==state){const event={listening:'nod',thinking:'ponder',interrupted:'interrupted'}[state];if(event)this.triggerReaction(event,{force:state==='interrupted'})}
  this.r2Requested=Object.hasOwn(R2_FACE_PROFILES,expression)?expression:expression==='smile'?'soft_smile':'neutral';
  super.configure(state,ALIASES[this.r2Requested]||this.r2Requested);
 }
 triggerReaction(name,{force=false}={}){
  if(!Object.hasOwn(REACTIONS,name))return false;
  if(!force&&(this.reaction||this.reactionCooldown<.6)){this.pendingReaction=name;return false}
  this.reaction={name,age:0};this.reactionCooldown=0;this.reactionSequence++;this.pendingReaction=null;return true;
 }
 reset(){super.reset();this.baseOpenness=0;this.basePose=null;this.reaction=null;this.pendingReaction=null;this.reactionCooldown=1;for(const name of ['ih','ou','blinkLeft','blinkRight'])this.weights[name]=0}
 update(dt,level=0,options={}){
  dt=Number.isFinite(dt)?clamp(dt,0,.1):0;
  if(this.basePose)Object.assign(this.output,this.basePose);
  if(this.baseOpenness!==undefined)this.weights.aa=this.baseOpenness;
  for(const key of ['happy','sad','angry','relaxed','surprised'])this.previousEmotion[key]=this.weights[key];
  const o=super.update(dt,level,options),active=!!options.audioPlaying&&!['interrupted','sleeping'].includes(this.state),step=dt*clamp(options.speed??1,.1,1);
  this.baseOpenness=this.weights.aa;this.basePose??={};for(const key of ['headX','headY','headZ','chestX','gazeX','gazeY'])this.basePose[key]=o[key];
  this.r2Age+=step;this.reactionCooldown+=step;
  let desired=this.r2Requested||'neutral';if(desired==='neutral')desired=this.state==='listening'?'attentive':this.state==='thinking'?'thinking':this.state==='sleeping'?'sleepy':'neutral';
  if(desired!==this.r2Profile&&this.r2Age>=.35){this.r2Profile=desired;this.r2Age=0}
  if(this.reaction){this.reaction.age+=step;if(this.reaction.age>=REACTIONS[this.reaction.name].seconds)this.reaction=null}
  if(!this.reaction&&this.pendingReaction&&this.reactionCooldown>=.6){const event=this.pendingReaction;this.pendingReaction=null;this.triggerReaction(event)}
  const reaction=this.reaction,config=reaction&&REACTIONS[reaction.name],phase=reaction?clamp(reaction.age/config.seconds):0;
  const envelope=reaction?Math.sin(Math.PI*phase)**2:0,gesture=envelope*clamp(options.motion??1),profile=R2_FACE_PROFILES[this.r2Profile]||{};
  let limited=false;
  for(const key of ['happy','sad','angry','relaxed','surprised']){
   let target=(profile[key]||0)+(key==='happy'?(config?.smile||0)*envelope:0);target=clamp(target,0,.68);
   if(active&&['happy','sad','angry'].includes(key))target*=.6;
   if(this.supported&&!this.supported.has(key)){if(target)limited=true;target=0}
   this.weights[key]=follow(this.previousEmotion[key],target,dt,target>this.previousEmotion[key]?4.5:5.5);
  }
  // Existing left/right blink channels only. Suppress wink during a full blink or sleep.
  const wink=config?.wink&&this.weights.blink<.15?config.wink*envelope:0;
  this.weights.blinkLeft=this.supported&&!this.supported.has('blinkLeft')?0:wink;this.weights.blinkRight=0;
  const openness=this.weights.aa,features=options.features||{},z=Number.isFinite(features.zeroCrossingRate)?clamp(features.zeroCrossingRate):null;
  // A measured spectral heuristic adds shape variation; it is not phoneme recognition.
  const round=active&&z!==null&&features.available!==false?clamp((.16-z)/.16)*.25:0,wide=active&&z!==null&&features.available!==false?clamp((z-.07)/.25)*.22:0;
  const ih=this.supported&&!this.supported.has('ih')?0:wide,ou=this.supported&&!this.supported.has('ou')?0:round;
  this.weights.ih=follow(this.weights.ih,openness*ih,dt,16);this.weights.ou=follow(this.weights.ou,openness*ou,dt,16);
  this.weights.aa=Math.max(0,openness-this.weights.ih-this.weights.ou);
  if(!active&&openness<.005){this.weights.aa=0;this.weights.ih=0;this.weights.ou=0}
  o.headX+=(config?.nod||0)*Math.sin(phase*Math.PI*2)*gesture;o.headY+=(config?.yaw||0)*gesture;o.headZ+=(config?.tilt||0)*gesture;o.chestX+=(config?.shoulder||0)*gesture;
  if(this.time>=this.saccadeAt){this.saccadeAt=this.time+2.2+this.random()*2;this.gazeTargetX=(this.random()-.5)*.014;this.gazeTargetY=(this.random()-.5)*.006}
  o.gazeX+=this.gazeTargetX*.3;o.gazeY+=this.gazeTargetY*.3;
  o.profile=this.r2Profile;o.transitioning=this.r2Age<.6;o.limited=limited;o.reaction=reaction?.name||'none';o.reaction_sequence=this.reactionSequence;
  return o;
 }
}
