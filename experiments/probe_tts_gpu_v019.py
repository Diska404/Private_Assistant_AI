"""Prove explicit TTS GPU selection using fresh files, with no audio playback."""
import hashlib
import json
from pathlib import Path
import sys
import time
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from audio_cpp_voice import AudioCppVoice

root=Path('D:/AI/AI Lokal Asisten/Leva/verification/speech-v019/tts');root.mkdir(parents=True,exist_ok=True)
proof={'microphone_opened':False,'playback':False,'engine':'omnivoice_leva','samples':[]}
for gpu in ('rtx4050','rtx5070'):
    folder=root/(gpu+'-'+str(time.time_ns()));folder.mkdir()
    engine=None
    try:
        start=time.monotonic();engine=AudioCppVoice('omnivoice_leva',folder,gpu)
        output=folder/'speech.wav'
        result=engine.synthesize('こんにちは。レヴァです。今日は何をしましょうか。',output,'ja','assistant')
        warm_output=folder/'speech-warm.wav'
        warm=engine.synthesize('こんにちは。レヴァです。今日は何をしましょうか。',warm_output,'ja','assistant')
        with wave.open(str(output),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
        proof['samples'].append({'requested_gpu':gpu,'output':str(output),'duration_seconds':round(duration,3),
            'total_seconds':round(time.monotonic()-start,3),'warm_request_seconds':warm['engine_request_seconds'],
            'warm_output':str(warm_output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),**result})
    except Exception as error:proof['samples'].append({'requested_gpu':gpu,'error':str(error)})
    finally:
        if engine:engine.close()
    (root.parent/'tts-gpu-proof-warm.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof['samples'][-1]),flush=True)
