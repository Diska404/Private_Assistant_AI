import assert from 'node:assert/strict';
import {RemoteVoice} from '../app/leva_web/audio.js';
const epoch='a'.repeat(24),other='b'.repeat(24);
const clip=(seq,e=epoch)=>({seq,url:`/api/audio/${e}/${seq}.wav`,language:'ja',pack:'fixture'});
const manifest=(clips=[],e=epoch)=>({epoch:e,latest:clips.at(-1)?.seq||0,clips});
const settle=async()=>{for(let i=0;i<20;i++)await new Promise(resolve=>setImmediate(resolve))};
function fixture({fetcher,hold=false}={}){
 const button={setAttribute(){},textContent:''},status={dataset:{},textContent:''},test={};
 const played=[],fetched=[];
 const context={state:'running',resume:async()=>{},decodeAudioData:async()=>({duration:.2}),destination:{},createBufferSource(){return{connect(){},disconnect(){},start(){played.push(this);if(!hold)queueMicrotask(()=>this.onended?.())},stop(){queueMicrotask(()=>this.onended?.())}}}};
 const fetchAudio=fetcher||(async url=>{fetched.push(url);return{ok:true,headers:{get:()=> '100'},arrayBuffer:async()=>new ArrayBuffer(100)}});
 return{voice:new RemoteVoice({button,status,test,send(){},contextFactory:()=>context,fetchAudio}),status,played,fetched};
}
let passed=0;
{
 const f=fixture();f.voice.update(manifest([clip(1)]));await f.voice.toggle();await settle();
 assert.equal(f.played.length,0,'Connecting/enabling must not replay historical speech');
 f.voice.update(manifest([clip(1),clip(2)]));await settle();f.voice.update(manifest([clip(1),clip(2)]));await settle();
 assert.equal(f.played.length,1,'Repeated snapshots must not repeat audio');passed++;
}
{
 const f=fixture();f.voice.update(manifest());await f.voice.toggle();f.voice.update(manifest([clip(1,other)],other));await settle();
 assert.equal(f.played.length,1,'The first new clip after interruption must not be skipped');passed++;
}
{
 const f=fixture({hold:true});f.voice.update(manifest());await f.voice.toggle();f.voice.update(manifest([clip(1),clip(2)]));await settle();
 assert.equal(f.played.length,1);f.voice.stop();await settle();assert.equal(f.played.length,1,'Stop must discard queued speech');assert.equal(f.voice.queue.length,0);passed++;
}
{
 let resolveFetch;const f=fixture({fetcher:()=>new Promise(resolve=>{resolveFetch=resolve})});f.voice.update(manifest());await f.voice.toggle();f.voice.update(manifest([clip(1)]));
 f.voice.stop();resolveFetch({ok:true,headers:{get:()=> '100'},arrayBuffer:async()=>new ArrayBuffer(100)});await settle();assert.equal(f.played.length,0,'A cancelled download must not start playback');passed++;
}
{
 const f=fixture();f.voice.update(manifest());await f.voice.toggle();f.voice.update(manifest([{...clip(1),url:'https://third-party.invalid/audio.wav'}]));await settle();assert.equal(f.fetched.length,0,'Only authenticated same-origin audio paths are allowed');passed++;
}
{
 const f=fixture();f.voice.update(manifest());await f.voice.toggle();f.voice.disconnected();f.voice.update(manifest([clip(1)]));await settle();assert.equal(f.played.length,0,'Reconnect must not replay speech produced while disconnected');
 f.voice.update(manifest([clip(1),clip(2)]));await settle();assert.equal(f.played.length,1);passed++;
}
console.log(JSON.stringify({passed,scope:'RemoteVoice cancellation, deduplication, reconnect and path restrictions; fake audio context, no speaker'}));
