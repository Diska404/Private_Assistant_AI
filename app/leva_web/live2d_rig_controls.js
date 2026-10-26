// Numeric controls for derived Leva rigs. Head XY is shallow parallax, not yaw.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number.isFinite(v)?v:0));
export function rigControls(p,{time=0,qaElapsed=null,freeze=false,leftEye=false,sleeping=false}={}){
 const w=p.weights||{},qa=qaElapsed!==null,q=qaElapsed/12000*Math.PI*4;
 const pose={ParamAngleX:qa?Math.sin(q)*30:p.headY*57.3*4,ParamAngleY:qa?Math.cos(q)*24:-p.headX*57.3*4,ParamAngleZ:qa?Math.sin(q)*30:p.headZ*57.3*6,ParamBodyAngleX:qa?Math.sin(q*.5)*8:p.spineY*57.3*3,ParamBodyAngleZ:qa?Math.cos(q*.5)*8:p.chestX*57.3*2,ParamBreath:.5-.5*Math.cos(time*(sleeping?.0012:.0019))};
 for(const id of ['ParamAngleX','ParamAngleY','ParamAngleZ'])pose[id]=freeze?0:clamp(pose[id],-30,30);
 for(const id of ['ParamBodyAngleX','ParamBodyAngleZ'])pose[id]=freeze?0:clamp(pose[id],-10,10);
 if(freeze)pose.ParamBreath=0;
 pose.ParamEyeLOpen=leftEye&&!sleeping?1-clamp(Math.max(w.blink||0,w.blinkLeft||0),0,1):0;
 pose.ParamLeftEyeMood=clamp((w.happy||0)-(w.angry||0),-1,1);
 return pose;
}
