"""Whole utterance ASR on the laptop. Never opens any microphone or speaker."""
import base64
import contextlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))


def main():
    emit=lambda data:print(json.dumps(data,ensure_ascii=True),flush=True)
    try:
        request=json.loads(sys.stdin.readline())
        with contextlib.redirect_stdout(sys.stderr):
            import numpy as np
            from speech_asr import SpeechASR,normalized_transcript
            pcm=base64.b64decode(request['pcm'],validate=True)
            if not 6400<=len(pcm)<=1_920_000 or len(pcm)%2:raise ValueError('invalid_pcm')
            samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
            engine=SpeechASR(request.get('model','qwen_asr_06b'),request.get('gpu','rtx5070'),max_tokens=1024)
            result=engine.transcribe(samples,request.get('language','id'),'Leva, Chrome, Diska, ChatGPT, Arduino, Smarthome IoT, Matematika Diskrit, ComfyUI, EdLink.')
        emit({'kind':'draft','text':normalized_transcript(result['text']),'metrics':{k:result[k] for k in ('model','gpu_name','requested_gpu','asr_ms','module_forward_cuda_ms','parameter_counts','executed_gpu_names','gpu_devices')}|{'load_ms':engine.load_ms}})
    except Exception as error:emit({'kind':'error','code':str(error)[:120] if isinstance(error,ValueError) else type(error).__name__})
    finally:emit({'kind':'stopped','microphone_open':False})


if __name__=='__main__':main()
