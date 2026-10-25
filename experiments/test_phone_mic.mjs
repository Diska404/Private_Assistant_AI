import test from 'node:test';
import assert from 'node:assert/strict';
import {PhoneMic,pcmWav} from '../app/leva_web/mic.js';
globalThis.document={addEventListener(){},hidden:false};
const sleep=()=>new Promise(r=>setImmediate(r));
function setup(options={}){
 let calls=0,stopped=0;const attrs={};const button={setAttribute:(k,v)=>attrs[k]=v},status={},meter={},cancel={};
 const stream={getTracks:()=>[{stop(){stopped++}}]};
 const media={async getUserMedia(){calls++;return stream}};
 const context={sampleRate:16000,async resume(){},async close(){},audioWorklet:{async addModule(){}},createMediaStreamSource:()=>({connect(){},disconnect(){}}),createGain:()=>({gain:{},connect(){},disconnect(){}})};
 const node={connect(){},disconnect(){},port:{postMessage(value){if(value==='flush')queueMicrotask(()=>this.onmessage({data:'flushed'}))}}};
 const requests=[],drafts=[];const api=async(path,opts)=>{requests.push([path,opts]);return path.includes('?id=')?{status:'completed',text:'Baca dokumen, jangan ubah file.'}:{status:'queued'}};
 const mic=new PhoneMic({button,status,meter,cancel,api,onDraft:v=>drafts.push(v),media,contextFactory:()=>context,nodeFactory:()=>node,...options});
 return {mic,button,status,node,cancel,drafts,requests,stream,get calls(){return calls},get stopped(){return stopped}};
}
test('page construction and enabling never open microphone',()=>{const s=setup();s.mic.enable(true);assert.equal(s.calls,0);assert.equal(s.requests.length,0)});
test('release stops all tracks, whole phrase is a draft only',async()=>{const s=setup();s.mic.enable(true);await s.mic.begin();s.node.port.onmessage({data:new Float32Array(6000).fill(.1)});const end=s.mic.end();assert.ok(s.stopped>0);await end;assert.deepEqual(s.drafts,['Baca dokumen, jangan ubah file.']);assert.ok(s.requests.every(r=>!r[0].includes('/commands')));assert.equal(s.button.disabled,false)});
test('permission granted after release does not leave a live stream',async()=>{let grant;const s=setup({media:{getUserMedia:()=>new Promise(r=>grant=r)}});s.mic.enable(true);const pending=s.mic.begin();await sleep();await s.mic.end();grant(s.stream);await pending;assert.ok(s.stopped>0);assert.equal(s.mic.stream,null);assert.equal(s.requests.length,0)});
test('cancel discards captured audio and never uploads',async()=>{const s=setup();s.mic.enable(true);await s.mic.begin();s.node.port.onmessage({data:new Float32Array(6000)});await s.mic.end(true);assert.equal(s.requests.length,0);assert.ok(s.stopped>0);assert.equal(s.mic.chunks.length,0)});
test('disabled state cannot capture',async()=>{const s=setup();await s.mic.begin();assert.equal(s.calls,0)});
test('WAV preserves full duration, sample rate and PCM format',async()=>{const b=pcmWav([new Float32Array(24000),new Float32Array(24000)],48000);const v=new DataView(await b.arrayBuffer());assert.equal(v.getUint32(24,true),16000);assert.equal(v.getUint16(22,true),1);assert.equal(v.getUint32(40,true),32000);assert.equal(b.size,32044)});
