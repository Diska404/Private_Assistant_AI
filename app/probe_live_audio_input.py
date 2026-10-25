"""Real Live VAD/barge-in test using synthesized PCM, never real microphone/speaker."""
import audioop
import base64
import json
from pathlib import Path
import sys
import threading
import time
import wave

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/"experiments")]
from live_voice import connect_live
from voice_core import PlaybackBuffer, voice_setup
from paths import DATA


def main():
    proof={"microphone_opened":False,"speaker_opened":False,"automatic_vad":True,
           "interruption_received":False,"input_transcript":"","response_audio_bytes":0}
    target=DATA/"verification"
    with wave.open(str(target/"synthetic-user-interrupt.wav"),"rb") as wav:
        pcm=wav.readframes(wav.getnframes())
        rate=wav.getframerate()
    audio,_=audioop.ratecv(pcm,2,1,rate,16000,None)
    playback=PlaybackBuffer()
    audio_response=bytearray()
    sent=False
    sender=None
    with connect_live() as ws:
        ws.send(json.dumps(voice_setup()))
        setup=json.loads(ws.recv(timeout=15))
        proof["setup_complete"]="setupComplete" in setup
        ws.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":"Jelaskan panjang lebar, dalam bahasa Indonesia, sejarah perkembangan komputer dari awal sampai sekarang."}]}],"turnComplete":True}}))
        def feed():
            for start in range(0,len(audio),1280):
                ws.send(json.dumps({"realtimeInput":{"audio":{"mimeType":"audio/pcm;rate=16000","data":base64.b64encode(audio[start:start+1280]).decode("ascii")}}}))
                time.sleep(0.04)
            for _ in range(12):
                ws.send(json.dumps({"realtimeInput":{"audio":{"mimeType":"audio/pcm;rate=16000","data":base64.b64encode(bytes(1280)).decode("ascii")}}}))
                time.sleep(0.04)
            ws.send(json.dumps({"realtimeInput":{"audioStreamEnd":True}}))
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            try:
                raw=json.loads(ws.recv(timeout=3))
            except TimeoutError:
                continue
            content=raw.get("serverContent",{})
            proof["last_message_fields"]=list(content)
            if content.get("interrupted"):
                proof["interruption_received"]=True
                playback.clear()
                proof["queue_empty_after_interrupt"]=len(playback)==0
            proof["input_transcript"]+=content.get("inputTranscription",{}).get("text","")
            for part in content.get("modelTurn",{}).get("parts",[]):
                data=part.get("inlineData",{}).get("data")
                if data:
                    decoded=base64.b64decode(data)
                    if proof["interruption_received"]:
                        audio_response.extend(decoded)
                    else:
                        playback.push(decoded)
                    if not sent:
                        sent=True
                        sender=threading.Thread(target=feed)
                        sender.start()
            if content.get("turnComplete") and proof["interruption_received"] and audio_response and proof["input_transcript"]:
                break
        if sender:
            sender.join(timeout=8)
    proof["response_audio_bytes"]=len(audio_response)
    proof["synthetic_audio_sent"]=sent
    (target/"live-audio-input-probe.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(proof,ensure_ascii=True))
    return 0 if proof["interruption_received"] and proof["input_transcript"] and audio_response else 1


if __name__=="__main__":
    raise SystemExit(main())
