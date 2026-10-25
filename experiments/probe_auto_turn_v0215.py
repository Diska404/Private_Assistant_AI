"""Synthetic recognizer/PCM; test automatic joining across a real three-second pause."""
import json,queue,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import numpy as np
import local_mic_worker
controls=queue.Queue();events=[];partial=threading.Event();errors=[]
texts=['Leva, buatkan web bumi 3d, boleh menggunakan','model AI apapun dari Hermes agent. Jangan generate dulu.']
class ASR:
    def __init__(self,*a):self.gpu={'name':'Synthetic'};self.devices=[];self.parameter_counts={};self.calls=0
    def transcribe(self,*a):
        value=texts[self.calls];self.calls+=1
        return {'text':value,'module_forward_cuda_ms':{}}
class Stream:
    def __init__(self,**kw):self.callback=kw['callback']
    def __enter__(self):
        def feed():
            try:
                tone=(np.sin(np.arange(320)*2*np.pi*300/16000)*3000).astype(np.int16).tobytes()
                for fragment in range(2):
                    for frame in [tone]*25+[bytes(640)]*55:self.callback(frame,320,None,None);time.sleep(.001)
                    if fragment==0:
                        assert partial.wait(3);time.sleep(3)
                        assert not any(e['kind']=='local_heard' for e in events),'unfinished first half was committed'
            except Exception as error:errors.append(str(error));controls.put({'kind':'stop'})
        self.thread=threading.Thread(target=feed,daemon=True);self.thread.start();return self
    def __exit__(self,*a):self.thread.join(timeout=1)
class Input:
    def __iter__(self):
        while True:
            item=controls.get(timeout=12);yield json.dumps(item)+'\n'
            if item['kind']=='stop':break
def emit(event):
    events.append(event)
    if event['kind']=='local_heard_partial':partial.set()
    if event['kind']=='local_heard':controls.put({'kind':'stop'})
sys.modules['sounddevice']=types.SimpleNamespace(RawInputStream=Stream,query_devices=lambda *a,**kw:{'name':'Synthetic'})
sys.modules['speech_asr']=types.SimpleNamespace(SpeechASR=ASR,normalized_transcript=lambda text:text)
sys.stdin=Input();local_mic_worker.run({'asr_model':'qwen_asr_06b','asr_gpu':'dual','asr_language':'id'},emit)
heard=[e for e in events if e['kind']=='local_heard'];commands=[e for e in events if e['kind']=='local_transcript']
assert not errors,errors
assert len(heard)==1 and len(commands)==1,(heard,commands)
assert heard[0]['text']==' '.join(texts) and heard[0]['accepted'],heard
assert 'Jangan generate dulu' in commands[0]['text']
proof={'synthetic':True,'real_microphone':False,'agent_executed':False,'pause_seconds':3,
       'first_fragment_not_dispatched':True,'full_command':commands[0]['text'],'commands':1,'negation_preserved':True}
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-session-v0215')
(out/'automatic-join.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
