export function hash(text){let h=2166136261;for(const c of text)h=Math.imul(h^c.charCodeAt(0),16777619);return(h>>>0)/4294967295}
// Uniform volume sampling and equal units on all three axes.
export function initialize(node,i){const a=hash(node.id+'angle')*Math.PI*2,u=hash(node.id+'elevation')*2-1,r=70+Math.cbrt(hash(node.id+'radius'))*170,s=Math.sqrt(1-u*u);return{...node,x:Math.cos(a)*s*r,y:u*r,z:Math.sin(a)*s*r,vx:0,vy:0,vz:0,r:node.category==='document'?5.5:node.category==='task'?6:4}}
export function step(nodes,edges,alpha=1,fixed=null){
 const map=new Map(nodes.map(n=>[n.id,n]));
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y,dz=(b.z||0)-(a.z||0),d2=dx*dx+dy*dy+dz*dz;if(d2<.1){dx=.1;dy=.1;dz=.1;d2=.03}const d=Math.sqrt(d2),f=Math.min(2.5,1200/d2)*alpha+(d<24?(24-d)*.025:0);
 // Preserve the force equations/order without allocating arrays for every pair.
 a.vx=(a.vx||0)-dx/d*f;b.vx=(b.vx||0)+dx/d*f;
 a.vy=(a.vy||0)-dy/d*f;b.vy=(b.vy||0)+dy/d*f;
 a.vz=(a.vz||0)-dz/d*f;b.vz=(b.vz||0)+dz/d*f}
 for(const e of edges){const a=map.get(e.source),b=map.get(e.target);if(!a||!b)continue;const dx=b.x-a.x,dy=b.y-a.y,dz=(b.z||0)-(a.z||0),d=Math.max(1,Math.hypot(dx,dy,dz)),f=(d-115)*.0025*alpha;for(const [key,delta]of[['vx',dx],['vy',dy],['vz',dz]]){a[key]=(a[key]||0)+delta/d*f;b[key]=(b[key]||0)-delta/d*f}}
 let energy=0;for(const n of nodes){if(n.id===fixed){n.vx=n.vy=n.vz=0;continue}for(const [pos,vel]of[['x','vx'],['y','vy'],['z','vz']]){n[vel]=((n[vel]||0)-(n[pos]||0)*.00065*alpha)*.84;n[pos]=(n[pos]||0)+Math.max(-7,Math.min(7,n[vel]));energy+=n[vel]*n[vel]}}return energy/Math.max(1,nodes.length)
}
