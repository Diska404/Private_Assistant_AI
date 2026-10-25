"""Deterministic offline acoustic simulation. Never opens microphone or speaker."""
import sys,time,json,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import numpy as np
from local_audio_core import EchoGuard,Segmenter
from paths import DATA

out=DATA/'verification/visual-voice-v027';out.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(271);sr=16000;seconds=14;count=sr*seconds
samples=DATA/'verification/higgs-naturalness-20261020/rtx4050-final'
def load(name):
    with wave.open(str(samples/name)) as stream:
        audio=np.frombuffer(stream.readframes(stream.getnframes()),np.int16).astype(np.float32)/32768;rate=stream.getframerate()
    return np.interp(np.arange(int(len(audio)*sr/rate))*rate/sr,np.arange(len(audio)),audio).astype(np.float32)
far=load('ja_long_leva_A.wav')[:count]*.5
delay=1280;echo=np.zeros(count,np.float32);echo[delay:]=far[:-delay]*.65;echo[delay+160:]+=far[:-delay-160]*.18
near=np.zeros(count,np.float32);start=sr*9;end=sr*12;near[start:end]=load('id_long_native.wav')[sr*2:sr*5]*.7
mic=echo+near;guard=EchoGuard();clean=[];timings=[];gate=Segmenter();interrupts=[]
pcm=lambda x:np.clip(x*32768,-32768,32767).astype(np.int16).tobytes()
# Render packets deliberately do not align with 320-sample capture frames.
sent=0;received=0
for i in range(0,count,320):
    while sent<min(count,i+640):
        limit=min(count,sent+588);guard.offer(pcm(far[sent:limit]),now=10+i/sr);sent=limit
    before=time.perf_counter();rms,rejected=guard.classify(pcm(mic[i:i+320]),now=10+i/sr);timings.append((time.perf_counter()-before)*1000)
    clean.append(np.frombuffer(guard.cleaned,np.int16).astype(np.float32)/32768)
    if gate.push(guard.cleaned,rms,rejected,True,True)[1]:interrupts.append(i/sr)
clean=np.concatenate(clean)
measure=slice(sr*5,sr*8);power=lambda x:float(np.mean(x*x))
erle=10*np.log10(max(1e-12,power(mic[measure]))/max(1e-12,power(clean[measure])))
region=slice(start+sr,end);gain=float(np.sqrt(power(clean[region])/power(near[region])))
correlation,lag=max((float(np.corrcoef(clean[start+sr+lag:end],near[start+sr:end-lag] if lag else near[start+sr:end])[0,1]),lag) for lag in range(0,321))
print('simulation',erle,correlation,gain,interrupts,lag,flush=True)
assert guard.backend=='webrtc_aec3',guard.backend
assert erle>12,erle
assert correlation>.65,correlation
assert .4<gain<1.6,gain
assert any(9<=t<9.6 for t in interrupts),interrupts
# Verify no packet-tail loss independent of the ring's 80-frame eviction.
carry=EchoGuard();signal=np.arange(588*3,dtype=np.int16)
for block in np.split(signal,3):carry.offer(block.tobytes(),now=1)
reconstructed=np.concatenate(tuple(carry.reference))*32768
assert np.array_equal(reconstructed.astype(np.int16),signal[:len(reconstructed)])
assert len(reconstructed)*2+len(carry.tail)==signal.nbytes
report={'backend':guard.backend,'package':'pywebrtc-audio==0.2.0','simulation_seconds':seconds,'echo_delay_ms':delay/sr*1000,'erle_db':float(erle),'near_end_correlation':correlation,'near_end_rms_ratio':gain,'dsp_ms_p50':float(np.median(timings)),'dsp_ms_p95':float(np.percentile(timings,95)),'barge_in_seconds':interrupts,'reference_packet_samples':588,'capture_frame_samples':320,'reference_tail_loss':0,'microphone_opened':False,'speaker_opened':False,'physical_acoustic_tested':False}
(out/'echo-proof.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
