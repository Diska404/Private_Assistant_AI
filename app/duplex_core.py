"""Transport-neutral micro-turn experiment. No microphone, model, TTS or action tools."""
from collections import deque
from dataclasses import dataclass
import math

LISTEN, NO_VOICE = "<listen>", "<no voice>"


@dataclass(frozen=True)
class TranscriptDelta:
    text: str = ""
    corrected: bool = False
    ignored: bool = False


class StableTranscript:
    """Emit only an agreeing prefix or final hypothesis, once per segment revision."""
    def __init__(self, capacity=32):
        self.capacity = capacity
        self.segments = {}
        self.retired = deque(maxlen=128)
        self.duplicate_revisions = 0
        self.corrections = 0

    def update(self, segment_id, revision, text, final=False):
        if not isinstance(segment_id,str) or not segment_id or not isinstance(revision,int) or revision<0:
            raise ValueError("invalid_transcript_identity")
        if not isinstance(text,str) or len(text)>3000:
            raise ValueError("invalid_transcript_text")
        old=self.segments.get(segment_id)
        if segment_id in self.retired:
            self.duplicate_revisions+=1
            return TranscriptDelta(ignored=True)
        if old and (revision<=old["revision"] or old["final"]):
            self.duplicate_revisions+=1
            return TranscriptDelta(ignored=True)
        if old is None and len(self.segments)>=self.capacity:
            closed=next((k for k,v in self.segments.items() if v["final"]),None)
            if closed is None:
                raise BufferError("too_many_open_transcript_segments")
            del self.segments[closed]
            self.retired.append(closed)
        words=text.split()
        previous=old["words"] if old else []
        emitted=old["emitted"] if old else []
        common=0
        for a,b in zip(previous,words):
            if a!=b:break
            common+=1
        corrected=words[:len(emitted)]!=emitted
        if corrected:
            self.corrections+=1
            emitted=[]
        stable=words if final else words[:common]
        delta=stable[len(emitted):]
        self.segments[segment_id]={"revision":revision,"words":words,"emitted":stable,"final":bool(final)}
        return TranscriptDelta(" ".join(delta),corrected)


@dataclass(frozen=True)
class Tick:
    id: int
    epoch: int
    heard: str
    started: float
    deadline: float
    history: tuple


def parse_decision(value):
    """Baseline grammar; never invents native LoRA tokens or silently truncates output."""
    if not isinstance(value,str):raise ValueError("invalid_policy_output")
    text=value.strip()
    if text==LISTEN:return "listen",LISTEN
    if not text or len(text.split())>3 or any(x in text for x in ("<",">","\n","\r")):
        raise ValueError("invalid_policy_output")
    return "speak",text


class DuplexCoordinator:
    def __init__(self, interval=0.6, max_pending=16, max_history=64, enforce_deadline=True):
        if not 0.1<=interval<=3:raise ValueError("invalid_tick_interval")
        self.interval=interval
        self.enforce_deadline=enforce_deadline
        self.max_pending=max_pending
        self.max_history=max_history
        self.epoch=0
        self.counter=0
        self.pending=deque()
        self.history=[]
        self.inflight=None
        self.next_due=0.0
        self.paused=False
        self.metrics={"deadline_misses":0,"stale_response_discards":0,"invalid_outputs":0,
                      "context_resets":0,"transcript_corrections":0,"backpressure":0}
        self.processing_ms=deque(maxlen=512)

    def add(self, delta):
        if delta.ignored:return
        if delta.corrected:
            # Already emitted text must not be edited inside a cached history.
            # Invalidate pending output and start a fresh, explicitly recorded context.
            self.epoch+=1
            self.history=[]
            self.pending.clear()
            self.inflight=None
            self.metrics["context_resets"]+=1
            self.metrics["transcript_corrections"]+=1
        if delta.text:
            if len(self.pending)>=self.max_pending or sum(len(v)+1 for v in self.pending)+len(delta.text)>600:
                self.metrics["backpressure"]+=1
                self.pause()
                raise BufferError("transcript_backpressure_session_paused")
            self.pending.append(delta.text)

    def begin(self, now):
        if self.paused or self.inflight is not None or now<self.next_due:return None
        if len(self.history)>=self.max_history or sum(len(a)+len(b) for a,b in self.history)>6000:
            self.history=[]
            self.epoch+=1
            self.metrics["context_resets"]+=1
        self.counter+=1
        heard=" ".join(self.pending) if self.pending else NO_VOICE
        self.pending.clear()
        tick=Tick(self.counter,self.epoch,heard,now,now+self.interval,tuple(self.history))
        self.inflight=tick
        self.next_due=now+self.interval
        return tick

    def finish(self,tick,value,now):
        if tick!=self.inflight or tick.epoch!=self.epoch or self.paused:
            self.metrics["stale_response_discards"]+=1
            return {"accepted":False,"reason":"stale_response"}
        self.inflight=None
        elapsed=max(0,(now-tick.started)*1000)
        self.processing_ms.append(elapsed)
        late=now>tick.deadline
        if late:
            self.metrics["deadline_misses"]+=1
        if late and self.enforce_deadline:
            if tick.heard!=NO_VOICE:self.pending.appendleft(tick.heard)
            return {"accepted":False,"reason":"deadline_missed","processing_ms":elapsed}
        try:kind,text=parse_decision(value)
        except ValueError:
            self.metrics["invalid_outputs"]+=1
            if tick.heard!=NO_VOICE:self.pending.appendleft(tick.heard)
            return {"accepted":False,"reason":"invalid_policy_output","processing_ms":elapsed}
        self.history.append((tick.heard,text))
        return {"accepted":True,"kind":kind,"text":text,"processing_ms":elapsed,"late":late,
                "manual_replay":not self.enforce_deadline}

    def pause(self):
        self.epoch+=1
        self.paused=True
        self.inflight=None
        self.pending.clear()

    def resume(self):
        self.paused=False
        self.next_due=0.0

    def summary(self):
        times=sorted(self.processing_ms)
        def percentile(p):return round(times[max(0,math.ceil(len(times)*p)-1)],2) if times else None
        return {**self.metrics,"tick_interval_ms":self.interval*1000,"tick_processing_p50_ms":percentile(.5),
                "tick_processing_p95_ms":percentile(.95),"measured_ticks":len(times)}


class SpeechGate:
    """Tickets prevent audio arriving after cancellation from entering playback."""
    def __init__(self,max_chunks=8):
        self.epoch=0
        self.queue=deque()
        self.max_chunks=max_chunks
        self.cancel_count=0
        self.stale_audio_discards=0

    def enqueue(self,text):
        if len(self.queue)>=self.max_chunks:raise BufferError("speech_backpressure")
        self.queue.append((self.epoch,text))
        return self.epoch

    def coalesce(self,max_words=12):
        chunks=[]
        while self.queue:
            epoch,text=self.queue[0]
            if chunks and len((" ".join(chunks)+" "+text).split())>max_words:break
            self.queue.popleft()
            if epoch==self.epoch:chunks.append(text)
        return (self.epoch," ".join(chunks)) if chunks else None

    def cancel(self):
        self.epoch+=1
        self.queue.clear()
        self.cancel_count+=1

    def accept_audio(self,ticket):
        valid=ticket==self.epoch
        if not valid:self.stale_audio_discards+=1
        return valid


def replay_scenarios():
    """Explicit synthetic policy outputs, not results generated by an AI."""
    ledger=StableTranscript()
    core=DuplexCoordinator()
    gate=SpeechGate()
    rows=[]
    fixtures=[("Saya sedang",False,LISTEN),("Saya sedang mencari",False,LISTEN),
              ("Saya sedang mencari referensi",True,LISTEN),(None,False,LISTEN),
              ("tentang eGPU laptop",True,"Baik, kita bahas."),(None,False,"Mulai dari koneksi.")]
    for i,(text,final,said) in enumerate(fixtures):
        if text:
            segment="a" if i<3 else "b"
            core.add(ledger.update(segment,i,text,final))
        tick=core.begin(i*.6)
        result=core.finish(tick,said,i*.6+.05)
        if result.get("kind")=="speak":gate.enqueue(result["text"])
        rows.append({"tick":i+1,"heard":tick.heard,"policy_output":said,**result})
    old_ticket=gate.epoch
    gate.cancel()
    stale_audio_accepted=gate.accept_audio(old_ticket)
    return {"synthetic":True,"microphone_opened":False,"model_loaded":False,"speaker_opened":False,
            "rows":rows,"metrics":core.summary(),"barge_in_flush":not gate.queue,
            "stale_audio_accepted":stale_audio_accepted,"latency_source":"virtual clock, not hardware benchmark"}
