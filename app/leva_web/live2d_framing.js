// Fit the actual visible mesh, rather than assuming every model shares the sample's canvas origin.
export function nativeFraming(bounds,aspect,framing='portrait'){
 const {minX,maxX,minY,maxY}=bounds,width=maxX-minX,height=maxY-minY;
 if(![minX,maxX,minY,maxY,aspect].every(Number.isFinite)||width<=0||height<=0||aspect<=0)throw new Error('invalid_live2d_bounds');
 const fraction=framing==='face'?.3:framing==='portrait'?.65:1,viewHeight=height*fraction,cy=maxY-viewHeight/2,cx=(minX+maxX)/2;
 const zoom=Math.min(1.8/viewHeight,1.8*aspect/width),sx=zoom/aspect,sy=zoom;
 return new Float32Array([sx,0,0,0,0,sy,0,0,0,0,1,0,-cx*sx,-cy*sy,0,1]);
}
