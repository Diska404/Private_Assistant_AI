"""Bounded real-model text probe; no mic/speaker and no claim of human dialogue quality."""
from pathlib import Path
import json
import queue
import sys
import time

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/"app"),str(Path(__file__).resolve().parent)]
from duplex_core import DuplexCoordinator,TranscriptDelta
from duplex_service import DuplexService
from paths import DATA


def main():
    service=DuplexService()
    core=DuplexCoordinator()
    rows=[]
    proof={"backend":"Qwen3.5-4B Q8_0 prompt-only","lora_loaded":False,"microphone_opened":False,
           "speaker_opened":False,"tick_interval_ms":600,"closed_loop":True,"manual_text_fragments":True}
    def event(timeout):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:return service.events.get_nowait()
            except queue.Empty:time.sleep(.01)
        raise TimeoutError("baseline_probe_timeout")
    try:
        service.start_lab()
        while True:
            item=event(100)
            if item["kind"]=="error":raise RuntimeError(item["code"])
            if item["kind"]=="ready":
                proof["ready"]=item
                break
        fragments=["Saya ingin menceritakan","sesuatu tentang laptop,","", "sebentar saya ingat",
                   "dulu... oh iya,","kenapa eGPU bisa","layarnya jadi hitam?",""]
        for fragment in fragments:
            if fragment:core.add(TranscriptDelta(fragment))
            while time.monotonic()<core.next_due:time.sleep(.01)
            tick=core.begin(time.monotonic())
            service.send({"kind":"tick","id":tick.id,"heard":tick.heard,"history":list(tick.history)})
            while True:
                item=event(12)
                if item["kind"]=="error":raise RuntimeError(item["code"])
                if item["kind"]=="result" and item["id"]==tick.id:break
            result=core.finish(tick,item["text"],time.monotonic())
            row={"tick":tick.id,"heard":tick.heard,"output":item["text"],"backend_ms":item["backend_ms"],
                 "timings":item.get("timings",{}),**result}
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!="timings"},ensure_ascii=True),flush=True)
        proof["completed"]=True
    except Exception as error:
        proof["completed"]=False
        proof["error"]=type(error).__name__
    finally:
        service.stop()
    proof["rows"]=rows
    proof["metrics"]=core.summary()
    target=DATA/"verification/duplex-baseline-qwen4b.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"completed":proof["completed"],"metrics":proof["metrics"],"proof":str(target)}),flush=True)


if __name__=="__main__":main()
