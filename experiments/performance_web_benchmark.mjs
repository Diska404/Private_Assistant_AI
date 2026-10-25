import {performance} from 'node:perf_hooks';
import {writeFileSync,mkdirSync} from 'node:fs';
import {initialize,step} from '../app/leva_web/physics.js';
import {NeuralGraph} from '../app/leva_web/graph.js';
const phase=process.argv[2]||'baseline',out='D:/AI/AI Lokal Asisten/Leva/verification/performance-20261024';
const stats=rows=>{rows.sort((a,b)=>a-b);return{n:rows.length,median_ms:rows[Math.floor(rows.length*.5)],p95_ms:rows[Math.floor(rows.length*.95)],min_ms:rows[0],max_ms:rows.at(-1)}};
const results={};
for(const count of [120,300,600]){
 const nodes=Array.from({length:count},(_,i)=>initialize({id:'fixture-'+i,category:'document',label:'Fixture '+i},i));
 const edges=nodes.slice(1).map((n,i)=>({source:nodes[i].id,target:n.id}));
 const samples=[];for(let f=0;f<55;f++){const t=performance.now();step(nodes,edges,.3);if(f>=10)samples.push(performance.now()-t)}
 results['physics_'+count]=stats(samples);
 if(count!==300)continue;
 const noop=()=>{};const ctx=new Proxy({createRadialGradient:()=>({addColorStop:noop})},{get:(o,k)=>o[k]||noop});
 const graph=Object.assign(Object.create(NeuralGraph.prototype),{ctx,mode:'knowledge',quality:'high',w:800,h:500,
   camera:{yaw:.3,pitch:.2},zoom:1,pan:{x:0,y:0},nodes,edges,hover:null,selected:null,labels:false});
 const draw=[],hits=[];let projections=0;const project=graph.project.bind(graph);graph.project=n=>{projections++;return project(n)};
 for(let i=0;i<70;i++){let t=performance.now();graph.draw(i*20,false);if(i>=10)draw.push(performance.now()-t);
   t=performance.now();graph.hit(400,250);if(i>=10)hits.push(performance.now()-t)}
 projections=0;graph.draw(0,false);results.draw_300={...stats(draw),projection_calls:projections};
 projections=0;graph.hit(400,250);results.hit_300={...stats(hits),projection_calls:projections};
}
mkdirSync(out,{recursive:true});writeFileSync(`${out}/web-${phase}.json`,JSON.stringify({phase,method:'Node.js CPU fixture; Canvas calls are no-op, excludes browser paint/GPU and is NOT FPS.',results},null,2));
console.log(JSON.stringify(results,null,2));
