/* Optional left eye from existing right-eye artwork/keyforms; no image generation. */
const fs=require('node:fs'),{loadCore,openModel}=require('./inspect_live2d_core.cjs');
(async()=>{
 const [core,moc,expressions,out]=process.argv.slice(2);if(!out)throw new Error('Usage: node bake_leva_left_eye_r03.cjs <core.js> <baseline.moc3> <expressions dir> <new output.json>');if(fs.existsSync(out))throw new Error('Refusing to overwrite bake.');
 const C=await loadCore(core),asset=openModel(C,moc),m=asset.model,ids=new Map(m.parameters.ids.map((id,i)=>[id,i]));
 const selected=[5,6,7,8,9,10,11,20,30,31,14],meshes=selected.map(index=>({sourceIndex:index,id:m.drawables.ids[index],mirrored:index!==14,samples:[]}));
 const recipe=name=>JSON.parse(fs.readFileSync(require('node:path').join(expressions,`EMO_Levva_${name}_01.exp3.json`),'utf8')).Parameters;
 const recipes={[-1]:recipe('Angry'),0:[],1:recipe('Happy')};
 const set=(id,value)=>{const i=ids.get(id);if(i!==undefined)m.parameters.values[i]=Math.max(m.parameters.minimumValues[i],Math.min(m.parameters.maximumValues[i],value))};
 for(const mood of [-1,0,1])for(const y of [-1,0,1])for(const x of [-1,0,1])for(const open of [0,1]){
  m.parameters.values.set(m.parameters.defaultValues);
  for(const p of recipes[mood]){const i=ids.get(p.Id);if(i===undefined)continue;set(p.Id,p.Blend==='Overwrite'?p.Value:p.Blend==='Multiply'?m.parameters.values[i]*p.Value:m.parameters.values[i]+p.Value)}
  set('ParamEyeROpen',open);set('ParamEyeBallX',-x);set('ParamEyeBallY',y);m.update();
  for(const target of meshes){const index=target.sourceIndex;target.samples.push({vertices:Array.from(m.drawables.vertexPositions[index]),opacity:m.drawables.opacities[index]*open})}
 }
 const result={source_moc:moc.split(/[\\/]/).pop(),kind:'optional_left_eye_mirrored_from_source_right_eye',generated_artwork:false,axes:[{id:'ParamEyeLOpen',keys:[0,1]},{id:'ParamEyeBallX',keys:[-1,0,1]},{id:'ParamEyeBallY',keys:[-1,0,1]},{id:'ParamLeftEyeMood',keys:[-1,0,1]}],meshes};
 fs.writeFileSync(out,JSON.stringify(result));asset.close();console.log(JSON.stringify({meshes:meshes.length,samples_per_mesh:54,generated_artwork:false}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
