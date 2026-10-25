class LevaRecorder extends AudioWorkletProcessor {
  constructor(){super();this.enabled=false;this.port.onmessage=e=>{this.enabled=e.data==='start'};}
  process(inputs,outputs){
    const channels=inputs[0];
    if(this.enabled&&channels&&channels.length){
      const mono=new Float32Array(channels[0].length);
      for(const channel of channels)for(let i=0;i<mono.length;i++)mono[i]+=channel[i]/channels.length;
      this.port.postMessage(mono,[mono.buffer]);
    }
    // Output is always silence: microphone monitoring is never played to speakers.
    return true;
  }
}
registerProcessor('leva-recorder',LevaRecorder);
