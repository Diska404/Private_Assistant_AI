// rAF pacing cannot exceed the display/browser refresh rate. No synthetic FPS counts.
export class FramePacer{
 constructor(){this.reset()}
 reset(){this.due=null;this.previous=null}
 accept(t,fps){
  const interval=1000/fps;if(!Number.isFinite(t)||!Number.isFinite(interval)||interval<=0)return null;
  if(this.due!==null&&t+.25<this.due)return null;
  const elapsed=this.previous===null?null:t-this.previous;this.previous=t;
  this.due=this.due===null||elapsed>250?t+interval:this.due+interval;
  if(this.due<t)this.due+=(Math.floor((t-this.due)/interval)+1)*interval;
  return {elapsed,delta:Math.min(.1,(elapsed??interval)/1000),stalled:elapsed>250};
 }
}
export class FrameLoadGovernor{
 constructor(){this.reset()}
 reset(){this.slowWindows=0;this.fallback=false}
 observe(metrics,requested,enabled=true){
  if(!enabled||requested!==120){this.reset();return requested}
  if(metrics.samples>=90){this.slowWindows=metrics.observed_fps<requested*.85&&metrics.frame_p95_ms>1000/requested*1.5?this.slowWindows+1:0;if(this.slowWindows>=4)this.fallback=true}
  return this.fallback?60:requested;
 }
}
const quantile=(values,p)=>values[Math.floor((values.length-1)*p)]||0;
export class AvatarFrameMetrics{
 constructor(size=240){this.size=size;this.intervals=new Float32Array(size);this.costs=new Float32Array(size);this.physics=new Float32Array(size);this.render=new Float32Array(size);this.reset()}
 reset(){this.count=0;this.cursor=0;this.physicsSteps=0;this.resets=0}
 push(elapsed,cost,physics,steps,render=0){if(elapsed===null)return;const i=this.cursor;this.intervals[i]=elapsed;this.costs[i]=cost;this.physics[i]=physics;this.render[i]=render;this.cursor=(i+1)%this.size;this.count=Math.min(this.size,this.count+1);this.physicsSteps+=steps}
 snapshot(target){
  const a=Array.from(this.intervals.subarray(0,this.count)).sort((x,y)=>x-y),c=Array.from(this.costs.subarray(0,this.count)).sort((x,y)=>x-y),p=Array.from(this.physics.subarray(0,this.count)).sort((x,y)=>x-y),r=Array.from(this.render.subarray(0,this.count)).sort((x,y)=>x-y);
  const mean=a.reduce((s,x)=>s+x,0)/Math.max(1,a.length),budget=1000/target;
  return {samples:a.length,target_fps:target,observed_fps:mean?1000/mean:0,frame_p50_ms:quantile(a,.5),frame_p95_ms:quantile(a,.95),frame_p99_ms:quantile(a,.99),
   draw_ms:c.reduce((s,x)=>s+x,0)/Math.max(1,c.length),draw_p95_ms:quantile(c,.95),render_cpu_p95_ms:quantile(r,.95),physics_ms:p.reduce((s,x)=>s+x,0)/Math.max(1,p.length),physics_p95_ms:quantile(p,.95),
   jitter_ms:Math.sqrt(a.reduce((s,x)=>s+(x-mean)**2,0)/Math.max(1,a.length)),frame_budget_ms:budget,long_frame_threshold_ms:budget*1.5,long_frame_count:a.filter(x=>x>budget*1.5).length,over_budget_frames:a.filter(x=>x>budget*1.5).length,
   estimated_missed_target_slots:a.reduce((s,x)=>s+Math.max(0,Math.round(x/budget)-1),0),simulation_steps:this.physicsSteps,simulation_resets:this.resets};
 }
}
