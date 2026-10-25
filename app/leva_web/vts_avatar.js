import{ReactivePerformance}from'./avatar_reactions.js';
import{FramePacer}from'./avatar_timing.js';
// This is an external renderer backend. The web card never pretends to render a Live2D character.
export class VTubeStudioAvatarProvider{
 constructor(canvas,options){Object.assign(this,options);this.canvas=canvas;this.dead=false;this.performance=new ReactivePerformance();this.pacer=new FramePacer();this.state='idle';this.expression='neutral';this.generation=null;this.lastPoll=0;this.sending=false;
  canvas.hidden=true;this.card=document.createElement('div');this.card.className='vts-backend-card';this.card.setAttribute('role','status');canvas.after(this.card);this.tick=t=>this.frame(t);
 }
 async load(){this.status=await this.api('/api/vts/status');this.paint();this.schedule();return {provider:'VTube Studio external',native_web_renderer:false}}
 async connect(authorize=false){this.status=await this.api('/api/vts/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({authorize})});this.paint()}
 paint(){this.card.replaceChildren();const title=document.createElement('h3');title.textContent='2D · VTube Studio';const state=document.createElement('p');state.textContent='Status: '+(this.status?.state||'off')+(this.status?.model_name?' · Model: '+this.status.model_name:'')+(this.status?.error?' · '+this.status.error:'');const note=document.createElement('p');note.textContent='Karakter Live2D dirender di jendela VTube Studio pada laptop. Halaman ini mengirim gerak, ekspresi dan level audio; belum menampilkan video avatar 2D di web/HP. Model contoh tidak dinamai Leva.';this.card.append(title,state,note)}
 update(value={}){if(this.generation!==value.generation_id)this.performance.reset();this.generation=value.generation_id;this.state=value.state||'idle';this.expression=value.expression||'neutral';const key=String(this.generation)+'|'+value.reaction_id;if(this.reactionKey!==key){this.reactionKey=key;if(value.reaction&&value.reaction!=='none'&&(value.reaction_age_ms==null||value.reaction_age_ms<2500))this.performance.triggerReaction(value.reaction)}}
 setExpression(value){this.expression=value}setExpressionOverride(value){this.override=value}triggerReaction(value){return this.performance.triggerReaction(value)}setQuality(){}setPhysicsEnabled(){}setPhysicsRate(){}setAdaptive(){}setRenderScale(){}setPerformanceVersion(){}setSecondaryEnabled(){}setEnhanced(){}setFreezePose(){}setAnimationSpeed(){}setLighting(){}setFraming(){}setView(){}setDebug(){}setMaterial(){}resetSimulation(){}
 schedule(){if(!this.dead&&!this.raf)this.raf=requestAnimationFrame(this.tick)}
 frame(t){this.raf=0;if(this.dead)return;const frame=this.pacer.accept(t,30);if(!frame){this.schedule();return}
  if(t-this.lastPoll>1000){this.lastPoll=t;this.api('/api/vts/status').then(v=>{this.status=v;this.paint()}).catch(()=>{});}
  if(this.status?.state==='connected'&&!document.hidden&&!this.sending){this.performance.configure(this.state,this.override||this.expression);const p=this.performance.update(frame.delta,this.level(),{audioPlaying:this.audioPlaying(),features:this.features?.()});
   const w=p.weights,payload={headX:p.headX,headY:p.headY,headZ:p.headZ,gazeX:p.gazeX,gazeY:p.gazeY,mouth:w.aa+w.ih+w.ou,happy:w.happy,sad:w.sad,angry:w.angry,blink:w.blink,blinkLeft:w.blinkLeft,blinkRight:w.blinkRight};
   this.sending=true;this.api('/api/vts/frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).catch(()=>{}).finally(()=>{this.sending=false})
  }this.schedule();
 }
 dispose(){this.dead=true;cancelAnimationFrame(this.raf);this.card.remove();this.canvas.hidden=false;this.api('/api/vts/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{})}
}
