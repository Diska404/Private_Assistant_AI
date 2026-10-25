"""Synthetic audio + deliberately slow ASR: test live meter during recognition."""
import json,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import numpy as np
import local_mic_worker
done=threading.Event();events=[];lock=threading.Lock()

class ASR:
    def __init__(self,*args):
        self.calls=0;self.gpu={'name':'SYNTHETIC TEST (no GPU)'};self.devices=[];self.parameter_counts={}
    def transcribe(self,*args):
        time.sleep(.8);self.calls+=1
        return {'text':'Ay, lipa.' if self.calls==1 else 'Leva, buka Chrome Diska.','module_forward_cuda_ms':{}}

class Stream:
    def __init__(self,**kw):self.callback=kw['callback'];self.stop=threading.Event()
    def __enter__(self):
        def audio():
            voice=(np.sin(np.arange(320)*2*np.pi*300/16000)*2000).astype(np.int16).tobytes()
            silence=bytes(640)
            for frame in [voice]*25+[silence]*38+[voice]*25+[silence]*100:
                if self.stop.wait(.02):break
                self.callback(frame,320,None,None)
        self.thread=threading.Thread(target=audio,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join(timeout=1)

class Input:
    def __iter__(self):
        done.wait(8);yield '{"kind":"stop"}\n'

def emit(event):
    with lock:events.append(event)
    if sum(e['kind']=='local_heard' for e in events)==2:done.set()

sys.modules['sounddevice']=types.SimpleNamespace(RawInputStream=Stream,query_devices=lambda *args,**kw:{'name':'Synthetic input'})
sys.modules['speech_asr']=types.SimpleNamespace(SpeechASR=ASR,normalized_transcript=lambda value:value)
sys.stdin=Input()
local_mic_worker.run({'asr_model':'qwen_asr_06b','asr_gpu':'dual','input_device_name':'','asr_language':'id'},emit)
meters=[e for e in events if e['kind']=='local_meter']
busy=[e for e in meters if e['phase']=='transcribing']
heard=[e for e in events if e['kind']=='local_heard']
commands=[e for e in events if e['kind']=='local_transcript']
assert len(busy)>=4,events
assert [e['reason'] for e in heard]==['awaiting_wake','wake'],heard
assert len(commands)==1 and commands[0]['text']=='buka Chrome Diska',commands
assert any(e['rms']>.02 for e in busy)
proof={'real_microphone_opened':False,'gpu_model_loaded':False,'agent_executed':False,'synthetic_meter_frames':len(meters),
       'meter_frames_during_slow_asr':len(busy),'heard':heard,'accepted_command_count':len(commands),
       'asr_delay_simulated_ms':800,'meter_uses_pcm_measurements':True}
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/mic-indicator-v0211');out.mkdir(parents=True,exist_ok=True)
(out/'worker-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
print(json.dumps(proof))
