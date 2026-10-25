import test from 'node:test';import assert from 'node:assert/strict';
import {rotatePoint,orbit,chatHeight}from'../app/leva_web/camera.js';
test('orbit rotates sphere and preserves spatial distance without translation',()=>{const camera={yaw:0,pitch:0},point={x:3,y:4,z:5};orbit(camera,100,40);const p=rotatePoint(point.x,point.y,point.z,camera.yaw,camera.pitch);assert.notEqual(p.x,point.x);assert.ok(Math.abs(Math.hypot(p.x,p.y,p.z)-Math.sqrt(50))<1e-8);assert.deepEqual(point,{x:3,y:4,z:5});});
test('pitch and resizable height are bounded',()=>{const camera={yaw:0,pitch:0};orbit(camera,20,99999);assert.equal(camera.pitch,1.45);assert.equal(chatHeight(-1),560);assert.equal(chatHeight(5000),2400);assert.equal(chatHeight(1000),1000);});
