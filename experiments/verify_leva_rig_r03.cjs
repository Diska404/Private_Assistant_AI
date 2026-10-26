/* Numerical acceptance checks against the real private Cubism Core, not mocks. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {loadCore,openModel,snapshot}=require('./inspect_live2d_core.cjs');
(async()=>{
 const [core,baseline,candidate,out]=process.argv.slice(2),C=await loadCore(core),a=openModel(C,baseline),b=openModel(C,candidate),m=b.model;
 function pose(model,values={}){model.parameters.values.set(model.parameters.defaultValues);for(const [id,v]of Object.entries(values)){const i=model.parameters.ids.indexOf(id);assert(i>=0,id);model.parameters.values[i]=v}model.update();return snapshot(model)}
 function difference(x,y,count=x.drawables.length){let max=0;for(let i=0;i<count;i++){assert.equal(x.drawables[i].vertices.length,y.drawables[i].vertices.length);for(let k=0;k<x.drawables[i].vertices.length;k++)max=Math.max(max,Math.abs(x.drawables[i].vertices[k]-y.drawables[i].vertices[k]))}return max}
 const base=pose(a.model),neutral=pose(m),delta=difference(base,neutral,35);assert(delta<.00001,'neutral geometry changed '+delta);
 const checks=[];let poses=0;
 for(const id of ['ParamAngleX','ParamAngleY','ParamBodyAngleX','ParamBodyAngleZ','ParamBreath','ParamHairFront','ParamHairBack','ParamHairSide','ParamJacketSway']){
  const i=m.parameters.ids.indexOf(id);assert(i>=0);let movement=0;for(const v of [m.parameters.minimumValues[i],m.parameters.maximumValues[i]]){const p=pose(m,{[id]:v});movement=Math.max(movement,difference(neutral,p,35));for(const d of p.drawables)assert(d.vertices.every(Number.isFinite));poses++}assert(movement>1e-5,id+' has no movement');checks.push({id,max_vertex_displacement:movement})
 }
 for(const x of [-30,0,30])for(const y of [-30,0,30])for(const z of [-30,30])for(const body of [-10,10]){const p=pose(m,{ParamAngleX:x,ParamAngleY:y,ParamAngleZ:z,ParamBodyAngleX:body,ParamBodyAngleZ:body,ParamBreath:1,ParamEyeLOpen:1});for(const d of p.drawables)assert(d.vertices.every(v=>Number.isFinite(v)&&Math.abs(v)<5));poses++}
 const open=pose(m,{ParamEyeLOpen:1});assert(open.drawables.slice(35).some(d=>d.opacity>.1));assert(neutral.drawables.slice(35).every(d=>d.opacity<.001));
 for(const z of [-30,30])assert(difference(pose(a.model,{ParamAngleZ:z}),pose(m,{ParamAngleZ:z}),35)<1e-5);
 const result={status:'passed',parameters:neutral.parameters.length,drawables:neutral.drawables.length,neutral_max_delta:delta,poses_checked:poses,active_controls:checks,left_eye_opt_in:true,head_motion:'limited_2_5d_parallax',full_perspective_yaw:false};fs.writeFileSync(out,JSON.stringify(result,null,2));console.log(JSON.stringify(result));a.close();b.close();
})().catch(e=>{console.error(e.message);process.exitCode=1});
