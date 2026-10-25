"""Deterministic wake, segmentation and interruption policy, independent of devices."""
from collections import deque
import math
import re
import time
from difflib import SequenceMatcher

def self_transcript(text,spoken,age):
    clean=lambda value:' '.join(re.findall(r'\w+',value.casefold()))
    a,b=clean(text),clean(spoken)
    return bool(a and b and age<4 and (a in b or SequenceMatcher(None,a,b).ratio()>.72))

class WakePolicy:
    def __init__(self,word='leva',followup_seconds=45):self.word=word.casefold();self.until=0;self.followup_seconds=followup_seconds
    def accept(self,text,now=None):
        now=time.monotonic() if now is None else now
        match=re.search(r'(?<!\w)(?:'+re.escape(self.word)+r'|lefa|reva)(?!\w)[, .!?]*',text,re.I)
        # These aliases were observed in microphone transcripts. Require a greeting
        # at the start for ambiguous names; do not activate on arbitrary background
        # mentions of Lipa or on substrings such as "lewat".
        if not match and self.word=='leva':
            match=re.match(r'^\s*(?:hai|hey|hei|halo|hallo|hi|ay)[, .!]*\s+(?:alipa|lipa|aliva|liva)[, .!?]*',text,re.I)
        if match:
            self.until=now+self.followup_seconds
            return {'accepted':True,'wake':True,'command':(text[:match.start()]+text[match.end():]).strip(' ,.!?')}
        if now<self.until:
            self.until=now+self.followup_seconds
            return {'accepted':True,'wake':False,'command':text.strip()}
        return {'accepted':False,'wake':False,'command':''}
    def active(self,now=None):return (time.monotonic() if now is None else now)<self.until
    def arm(self,seconds=None,now=None):
        now=time.monotonic() if now is None else now
        self.until=now+(self.followup_seconds if seconds is None else seconds)

class Segmenter:
    def __init__(self,silence_frames=28,max_frames=600):
        self.pre=deque(maxlen=10);self.frames=[];self.silence=0;self.voiced=0;self.noise=.001;self.interruption=0
        self.silence_frames=silence_frames;self.max_frames=max_frames;self.last_boundary='';self.continuing=False
    @property
    def threshold(self):return max(.009,self.noise*3)
    def flush(self):
        pcm=b''.join(self.frames) if self.frames and (self.voiced or self.continuing) else b''
        self.frames=[];self.pre.clear();self.silence=self.voiced=0;self.continuing=False
        return pcm
    def push(self,pcm,rms,echo=False,speaking=False,awake=False):
        voiced=not echo and rms>self.threshold
        if not voiced and not speaking:self.noise=.995*self.noise+.005*min(rms,.01)
        self.interruption=self.interruption+1 if voiced and speaking and awake else 0
        interrupted=self.interruption==7
        self.pre.append(pcm)
        if voiced:
            if not self.frames:self.frames=list(self.pre)
            else:self.frames.append(pcm)
            self.voiced+=1;self.silence=0
        elif self.frames:
            self.frames.append(pcm);self.silence+=1
        complete=None;self.last_boundary=''
        if self.frames and (self.silence>=self.silence_frames or len(self.frames)>=self.max_frames):
            self.last_boundary='silence' if self.silence>=self.silence_frames else 'limit'
            if self.voiced>=10 or self.continuing:complete=b''.join(self.frames)
            self.continuing=self.last_boundary=='limit'
            self.frames=[];self.voiced=0
            if not self.continuing:self.silence=0
            self.pre.clear()
        # A length boundary can occur just as speech ends. Still close that turn
        # after silence, even if the next chunk contains no voiced frames.
        elif self.continuing and not self.frames and not voiced:
            self.silence+=1
            if self.silence>=self.silence_frames:
                self.last_boundary='silence';complete=b'';self.continuing=False;self.silence=0;self.pre.clear()
        return complete,interrupted,voiced

class EchoGuard:
    """WebRTC AEC3 with continuous render reference and a conservative echo gate.

    This object belongs to the capture/control thread; ASR reads snapshots only.
    Correlation fallback is explicitly identified when the native DSP is absent.
    """
    def __init__(self):
        self.reference=deque(maxlen=80);self.last_reference=0;self.tail=b'';self.render=bytearray();self.processor=None
        self.backend='correlation_fallback';self.last_metrics={};self.cleaned=None;self.discontinuities=0
        try:
            from pywebrtc_audio import AudioProcessor
            self.processor=AudioProcessor(sample_rate=16000,echo_cancellation=True,noise_suppression=False,auto_gain_control=False,stream_delay_ms=40)
            self.backend='webrtc_aec3'
        except (ImportError,OSError,RuntimeError):pass
    def reset(self):
        self.reference.clear();self.tail=b'';self.render.clear();self.last_reference=0;self.discontinuities+=1
        if self.processor:self.processor.reset()
    def offer(self,pcm,now=None):
        import numpy as np
        now=time.monotonic() if now is None else now
        if self.last_reference and now-self.last_reference>1:self.reset()
        if len(self.render)+len(pcm)>32000:self.reset()
        self.render.extend(pcm)
        # Retain the fractional 20-ms frame across the 36.75/40-ms playback packets.
        continuous=self.tail+pcm;end=len(continuous)//640*640;self.tail=continuous[end:]
        samples=np.frombuffer(continuous[:end],dtype=np.int16).astype(np.float32)/32768
        for offset in range(0,len(samples),320):self.reference.append(samples[offset:offset+320].copy())
        self.last_reference=time.monotonic() if now is None else now
    def classify(self,pcm,now=None):
        import numpy as np
        now=time.monotonic() if now is None else now
        mic=np.frombuffer(pcm,dtype=np.int16).astype(np.float32)/32768
        rms=float(np.sqrt(np.mean(mic*mic)))
        clean=mic;size=len(pcm);render=bytes(self.render[:size]);del self.render[:size]
        render+=b'\0'*(size-len(render))
        if self.processor:
            clean=self.processor.process(np.frombuffer(pcm,dtype=np.int16).copy(),np.frombuffer(render,dtype=np.int16).copy()).astype(np.float32)/32768
        self.cleaned=np.clip(clean*32768,-32768,32767).astype(np.int16).tobytes()
        self.last_metrics={'echo_backend':self.backend,'clean_rms':round(float(np.sqrt(np.mean(clean*clean))),6),'reference_buffer_ms':round(len(self.render)/32),'reference_resets':self.discontinuities}
        if not self.reference or now-self.last_reference>1:return float(np.sqrt(np.mean(clean*clean))),False
        # Downsampled correlation searches arbitrary acoustic delays rather than
        # assuming microphone/output callbacks have aligned frame boundaries.
        history=np.concatenate(tuple(self.reference))[::4];short=mic[::4];length=len(short)
        if len(history)<length:return rms,False
        dots=np.correlate(history,short,mode='valid')
        squared=np.concatenate(([0.],np.cumsum(history.astype(np.float64)**2)))
        energies=squared[length:]-squared[:-length]
        coefficients=np.abs(dots)/np.sqrt(np.maximum(1e-9,energies*float(np.dot(short,short))))
        index=int(np.argmax(coefficients));best=float(coefficients[index]);ref=history[index:index+length]
        gain=float(dots[index])/max(1e-8,float(energies[index]));diff=short-gain*ref
        residual=float(np.sqrt(np.mean(diff*diff)))
        pure_echo=best>.97 and residual<max(.002,rms*.18)
        if pure_echo:self.cleaned=bytes(len(pcm))
        elif not self.processor and best>.72:
            # Fallback subtracts only an observed aligned linear reference. It
            # preserves the independent near-end component instead of muting it.
            full=np.concatenate(tuple(self.reference));start=index*4
            ref_full=full[start:start+len(mic)]
            if len(ref_full)==len(mic):
                clean=mic-gain*ref_full;self.cleaned=np.clip(clean*32768,-32768,32767).astype(np.int16).tobytes()
        out_rms=0. if pure_echo else float(np.sqrt(np.mean(clean*clean)))
        self.last_metrics.update(echo_correlation=round(best,4),echo_rejected=pure_echo,clean_rms=round(out_rms,6))
        return out_rms,pure_echo
