"""Synthetic Live transport/audio probe. Never opens a microphone or speaker."""
import base64
import json
from pathlib import Path
import sys
import time
import wave

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/"experiments")]
from live_voice import connect_live
from voice_core import PlaybackBuffer, voice_setup
from paths import DATA


def main():
    proof={"microphone_opened":False,"speaker_opened":False,"setup_complete":False,
           "audio_received_before_interrupt":False,"interruption_received":False,
           "queued_audio_cleared":False,"final_audio_bytes":0,"output_transcript":""}
    playback=PlaybackBuffer()
    with connect_live() as ws:
        ws.send(json.dumps(voice_setup(manual_activity=True)))
        reply=json.loads(ws.recv(timeout=15))
        proof["setup_complete"]="setupComplete" in reply
        if not proof["setup_complete"]:
            raise RuntimeError("setup_failed")
        ws.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":"Dalam bahasa Indonesia, hitung dari satu hingga tiga puluh dengan perlahan."}]}],"turnComplete":True}}))
        deadline=time.monotonic()+25
        interrupted=False
        while time.monotonic()<deadline:
            message=json.loads(ws.recv(timeout=15)).get("serverContent",{})
            for part in message.get("modelTurn",{}).get("parts",[]):
                audio=part.get("inlineData",{})
                if audio.get("data"):
                    proof["audio_received_before_interrupt"]=True
                    playback.push(base64.b64decode(audio["data"]))
                    if not interrupted:
                        ws.send(json.dumps({"realtimeInput":{"activityStart":{}}}))
                        ws.send(json.dumps({"realtimeInput":{"audio":{"mimeType":"audio/pcm;rate=16000","data":base64.b64encode(bytes(3200)).decode("ascii")}}}))
                        interrupted=True
            if message.get("interrupted"):
                playback.clear()
                proof["interruption_received"]=True
                proof["queued_audio_cleared"]=len(playback)==0
                break
        ws.send(json.dumps({"realtimeInput":{"activityEnd":{}}}))
        ws.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":"Katakan singkat dalam bahasa Indonesia: Halo, aku Leva. Aku siap mendengarkan."}]}],"turnComplete":True}}))
        pcm=bytearray()
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            content=json.loads(ws.recv(timeout=15)).get("serverContent",{})
            for part in content.get("modelTurn",{}).get("parts",[]):
                audio=part.get("inlineData",{})
                if audio.get("data"):
                    pcm.extend(base64.b64decode(audio["data"]))
            proof["output_transcript"]+=content.get("outputTranscription",{}).get("text","")
            if content.get("turnComplete") and pcm:
                break
    target=DATA/"verification"
    target.mkdir(parents=True,exist_ok=True)
    path=target/"live-synthetic-voice.wav"
    with wave.open(str(path),"wb") as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(pcm)
    proof["final_audio_bytes"]=len(pcm)
    proof["audio_file"]=str(path)
    (target/"live-duplex-probe.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(proof,ensure_ascii=True))
    return 0 if proof["interruption_received"] and pcm else 1


if __name__=="__main__":
    raise SystemExit(main())
