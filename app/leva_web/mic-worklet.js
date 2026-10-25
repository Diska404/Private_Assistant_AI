// Dedicated capture node. No recording starts until the UI creates this processor.
class LevaCapture extends AudioWorkletProcessor{
 constructor(){super();this.buffer=new Float32Array(1600);this.index=0;this.port.onmessage=e=>{if(e.data==='flush'){if(this.index)this.port.postMessage(this.buffer.slice(0,this.index));this.index=0;this.port.postMessage('flushed')}}}
 process(inputs){const input=inputs[0]?.[0];if(input)for(const sample of input){this.buffer[this.index++]=sample;if(this.index===this.buffer.length){this.port.postMessage(this.buffer.slice());this.index=0}}return true}
}
registerProcessor('leva-capture',LevaCapture);
