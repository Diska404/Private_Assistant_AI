// Orbit the camera, never mutate graph topology or node positions on drag.
export function rotatePoint(x,y,z,yaw,pitch){
 const c=Math.cos(yaw),s=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
 const a=x*c+z*s,b=z*c-x*s;
 return {x:a,y:y*cp-b*sp,z:y*sp+b*cp};
}
export function orbit(camera,dx,dy){camera.yaw+=dx*.008;camera.pitch=Math.max(-1.45,Math.min(1.45,camera.pitch+dy*.008));}
export function chatHeight(value){return Math.max(560,Math.min(2400,Number(value)||740));}
