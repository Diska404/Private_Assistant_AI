/* Headless geometry inspection using the separately installed private Cubism SDK. */
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
async function loadCore(corePath){
 const context={console,require,process,Buffer,WebAssembly,TextDecoder,TextEncoder,ArrayBuffer,Uint8Array,Float32Array,setTimeout,clearTimeout,__dirname:path.dirname(corePath),__filename:corePath,module:{exports:{}},exports:{}};
 try{vm.runInNewContext(fs.readFileSync(corePath,'utf8'),context,{filename:corePath})}catch(e){throw new Error('Core initialization: '+e.message)}
 for(let i=0;i<200;i++){try{context.Live2DCubismCore.Version.csmGetVersion();return context.Live2DCubismCore}catch{}await new Promise(r=>setTimeout(r,10))}
 throw new Error('core_initialization_timeout');
}
function openModel(C,mocPath){const bytes=fs.readFileSync(mocPath),moc=C.Moc.fromArrayBuffer(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));if(!moc)throw new Error('moc_load_failed');const model=C.Model.fromMoc(moc);if(!model)throw new Error('model_load_failed');model.update();return {moc,model,close(){model.release();moc._release()}}}
function snapshot(model){return {parameters:model.parameters.ids.map((id,i)=>({id,min:model.parameters.minimumValues[i],max:model.parameters.maximumValues[i],default:model.parameters.defaultValues[i]})),drawables:model.drawables.ids.map((id,i)=>{const v=model.drawables.vertexPositions[i],x=v.filter((_,n)=>n%2===0),y=v.filter((_,n)=>n%2===1);return {id,vertices:Array.from(v),opacity:model.drawables.opacities[i],bounds:{minX:Math.min(...x),maxX:Math.max(...x),minY:Math.min(...y),maxY:Math.max(...y)}}})}}
module.exports={loadCore,openModel,snapshot};
if(require.main===module)(async()=>{const [corePath,mocPath,outPath]=process.argv.slice(2);if(!corePath||!mocPath)throw new Error('Usage: node inspect_live2d_core.cjs <core.js> <model.moc3> [output.json]');const C=await loadCore(corePath),asset=openModel(C,mocPath),result=snapshot(asset.model);if(outPath)fs.writeFileSync(outPath,JSON.stringify(result));console.log(JSON.stringify({parameters:result.parameters.length,drawables:result.drawables.length}));asset.close()})().catch(e=>{console.error(e.message);process.exitCode=1});
