/* Acceptance for the real R04-A export; no SDK code or assets embedded. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const{loadCore,openModel,snapshot}=require('./inspect_live2d_core.cjs');
(async()=>{
 const[core,baseline,candidate,out]=process.argv.slice(2),C=await loadCore(core),a=openModel(C,baseline),b=openModel(C,candidate),m=b.model;
 function pose(model,values){model.parameters.values.set(model.parameters.defaultValues);for(const[id,v]of Object.entries(values))model.parameters.values[model.parameters.ids.indexOf(id)]=v;model.update();return snapshot(model)}
 const na=pose(a.model,{}),nb=pose(m,{});assert.equal(nb.drawables.length,57);assert.deepEqual(na.parameters,nb.parameters);let delta=0;
 for(let i=0;i<46;i++){if(i===33)continue;for(let k=0;k<na.drawables[i].vertices.length;k++)delta=Math.max(delta,Math.abs(na.drawables[i].vertices[k]-nb.drawables[i].vertices[k]))}assert(delta<1e-6);
 let tested=0;for(const x of[-30,0,30])for(const y of[-30,0,30])for(const z of[-30,0,30])for(const eye of[0,1]){const s=pose(m,{ParamAngleX:x,ParamAngleY:y,ParamAngleZ:z,ParamEyeLOpen:eye,ParamBreath:1,ParamBodyAngleX:8});for(const d of s.drawables)assert(d.vertices.every(v=>Number.isFinite(v)&&Math.abs(v)<5));tested++}
 const names=nb.drawables.map(d=>d.id);assert.equal(names.filter(id=>id.startsWith('Leva_R04A_')).length,12);
 const result={status:'passed',parameters:44,drawables:57,separated_base_parts:12,combined_poses:tested,untouched_face_max_vertex_delta:delta,independent_arm_controls:false,full_body:false};fs.writeFileSync(out,JSON.stringify(result,null,2));console.log(JSON.stringify(result));a.close();b.close();
})().catch(e=>{console.error(e.message);process.exitCode=1});
