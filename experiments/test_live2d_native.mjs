import assert from 'node:assert/strict';
import{localResource,NativeLive2DAvatarProvider}from'../app/leva_web/live2d_avatar.js';
assert.equal(localResource('Hiyori.2048/texture_00.png'),'/api/live2d/model/Hiyori.2048/texture_00.png');
for(const name of ['../secret','/absolute','https://remote/a','x?query','x\\y',null])assert.throws(()=>localResource(name));
assert.equal(typeof NativeLive2DAvatarProvider.prototype.dispose,'function');
assert.equal(localResource('model.json','leva_rig_r02'),'/api/live2d/models/leva_rig_r02/model.json');
assert.throws(()=>localResource('model.json','../leva_rig_r02'));
console.log('Live2D native: resource URL guards and lifecycle contract passed; rendering covered by browser evidence.');

const {nativeFraming}=await import('../app/leva_web/live2d_framing.js');
const bounds={minX:-.5,maxX:.5,minY:-2,maxY:3};const matrix=nativeFraming(bounds,1.5,'full');for(const x of [-.5,.5])for(const y of [-2,3]){assert(Math.abs(x*matrix[0]+matrix[12])<=1);assert(Math.abs(y*matrix[5]+matrix[13])<=1)}assert.throws(()=>nativeFraming({...bounds,maxY:-2},1));

const {decodeLive2DTexture}=await import('../app/leva_web/live2d_avatar.js');
let bitmapOptions;globalThis.createImageBitmap=async(blob,options)=>{assert.equal(blob.type,'image/png');bitmapOptions=options;return {width:1,height:1}};await decodeLive2DTexture(new Uint8Array([1]));assert.equal(bitmapOptions.premultiplyAlpha,'premultiply');delete globalThis.createImageBitmap;
