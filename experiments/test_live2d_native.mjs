import assert from 'node:assert/strict';
import{localResource,NativeLive2DAvatarProvider}from'../app/leva_web/live2d_avatar.js';
assert.equal(localResource('Hiyori.2048/texture_00.png'),'/api/live2d/model/Hiyori.2048/texture_00.png');
for(const name of ['../secret','/absolute','https://remote/a','x?query','x\\y',null])assert.throws(()=>localResource(name));
assert.equal(typeof NativeLive2DAvatarProvider.prototype.dispose,'function');
console.log('Live2D native: resource URL guards and lifecycle contract passed; rendering covered by browser evidence.');
