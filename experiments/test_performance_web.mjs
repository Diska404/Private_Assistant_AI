import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {NeuralGraph} from '../app/leva_web/graph.js';
import {initialize,step} from '../app/leva_web/physics.js';
import {mergeMessages} from '../app/leva_web/messages.js';
const baseline='D:/AI/AI Lokal Asisten/Leva/verification/performance-20261024/baseline-web/';
const {step:oldStep}=await import(pathToFileURL(baseline+'physics.js'));
const {NeuralGraph:OldGraph}=await import(pathToFileURL(baseline+'graph.js'));
let passed=0;
const history=[{id:1,text:'First'},{id:2,text:'Second'}];
assert.deepEqual(mergeMessages(history,{messages_mode:'append',messages_first_id:1,messages:[]}),history);passed++;
assert.deepEqual(mergeMessages(history,{messages_mode:'append',messages_first_id:2,messages:[{id:3,text:'New'}]}),[{id:2,text:'Second'},{id:3,text:'New'}]);passed++;
assert.deepEqual(mergeMessages(history,{messages_mode:'replace',messages:[]}),[]);passed++;
assert.deepEqual(mergeMessages(history,{messages:[{id:9,text:'Other room'}]}),[{id:9,text:'Other room'}]);passed++;
const seed=Array.from({length:140},(_,i)=>initialize({id:'n'+i,category:'document',label:'Node '+i},i));
seed[0].x=seed[1].x;seed[0].y=seed[1].y;seed[0].z=seed[1].z;
const edges=seed.slice(1).map((n,i)=>({source:seed[i].id,target:n.id}));
const current=structuredClone(seed),old=structuredClone(seed);
for(let i=0;i<25;i++){step(current,edges,.3);oldStep(old,edges,.3)}
assert.deepEqual(current,old,'Force equations and layout must remain numerically identical');passed++;
function fixture(Type){const calls=[];const noop=(...args)=>calls.push(args);const ctx=new Proxy({createRadialGradient:(...args)=>{calls.push(['gradient',...args]);return{addColorStop:noop}}},{get:(o,k)=>o[k]||((...args)=>calls.push([k,...args])),set:(o,k,v)=>{calls.push([k,v]);o[k]=v;return true}});
 const graph=Object.assign(Object.create(Type.prototype),{ctx,mode:'knowledge',quality:'high',w:800,h:500,camera:{yaw:.7,pitch:.3},zoom:1,pan:{x:0,y:0},nodes:current,edges,hover:'n20',selected:'n4',labels:true});return{graph,calls}}
const a=fixture(NeuralGraph),b=fixture(OldGraph);a.graph.draw(140,false);b.graph.draw(140,false);
// Gradient methods are fixture functions with different identities; compare values.
assert.equal(JSON.stringify(a.calls),JSON.stringify(b.calls),'Canvas drawing commands must preserve stars, positions, colors and labels');passed++;
a.calls.length=b.calls.length=0;a.graph.draw(160,false);b.graph.draw(160,false);assert.equal(JSON.stringify(a.calls),JSON.stringify(b.calls));passed++;
for(let x=0;x<800;x+=35)for(let y=0;y<500;y+=35)assert.equal(a.graph.hit(x,y)?.id,b.graph.hit(x,y)?.id);passed++;
const g=Object.assign(Object.create(NeuralGraph.prototype),{phase:'idle',input:0,output:0,mode:'knowledge',schedule(){this.scheduled=(this.scheduled||0)+1}});
g.setSignal('idle',.2,.3);assert.equal(g.scheduled,undefined);g.setSignal('thinking',.2,.3);assert.equal(g.scheduled,1);g.mode='neural';g.setSignal('thinking',.4,.3);assert.equal(g.scheduled,2);passed++;
// Test scheduling with a settled graph, rather than inspecting source strings.
globalThis.document={hidden:false};
for(const [mode,phase,quality,expected] of [['knowledge','idle','high',0],['knowledge','thinking','high',1],['knowledge','thinking','low',0],['neural','idle','high',1]]){
 const v=Object.assign(Object.create(NeuralGraph.prototype),{mode,phase,quality,motion:true,reduced:false,alpha:0,nodes:[],edges:[],w:800,h:500,intensity:.5,pointer:{x:0,y:0},frameTimes:[],fps:[],lastReport:1000,draw(){},schedule(){this.scheduled=(this.scheduled||0)+1}});
 v.frame(1100);assert.equal(v.scheduled||0,expected,mode+' '+phase);passed++;
}
console.log(JSON.stringify({passed,visual_commands_identical:true,physics_identical:true}));
