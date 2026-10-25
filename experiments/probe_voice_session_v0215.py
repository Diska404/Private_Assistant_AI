"""Synthetic PCM + recognizer: verify capture/segmentation/hold/dispatch protocol.
Not an ASR accuracy or real microphone test. Never executes an agent.
"""
import json,queue,sys,threading,time,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
import numpy as np
import local_mic_worker

def probe(hold=False):
    controls=queue.Queue();events=[];held=threading.Event();resumed=threading.Event()
    started=threading.Event();fed=threading.Event();release=threading.Event();loaded=[];calls=[];errors=[];recording=threading.Event()
    samples=(np.sin(np.arange(320)*2*np.pi*300/16000)*3000).astype(np.int16).tobytes();silence=bytes(640)
    texts=['Leva, ingatkan saya dua menit lagi.','Leva, buka','Chrome Diska untuk ChatGPT','lalu buka Edge EdLink.','jam berapa sekarang.']
    class ASR:
        def __init__(self,*args):
            self.gpu={'name':'SYNTHETIC (no GPU)'};self.devices=[];self.parameter_counts={};loaded.append(True)
        def transcribe(self,*args):
            calls.append(len(args[0]));started.set()
            if not hold and len(calls)==1:assert release.wait(5),'capture stalled while ASR busy'
            return {'text':texts[len(calls)-1],'module_forward_cuda_ms':{}}
    class Stream:
        def __init__(self,**kwargs):self.callback=kwargs['callback']
        def __enter__(self):
            def feed():
                try:
                    controls.put({'kind':'dictation_start'});assert recording.wait(5)
                    if hold:
                        controls.put({'kind':'hold_asr'});assert held.wait(5)
                    for frame in [samples]*500+[silence]*100:self.callback(frame,320,None,None);time.sleep(.0005)
                    if not hold:assert started.wait(5)
                    for frame in [samples]*1850+[silence]*55+[samples]*25+[silence]*55:
                        self.callback(frame,320,None,None);time.sleep(.0005)
                    fed.set();controls.put({'kind':'dictation_commit'})
                    if hold:
                        time.sleep(.25);assert not calls,'ASR ran while GPU was held'
                        controls.put({'kind':'resume_asr'});assert resumed.wait(5)
                    else:release.set()
                except Exception as error:errors.append(repr(error));controls.put({'kind':'stop'})
            self.thread=threading.Thread(target=feed,daemon=True);self.thread.start();return self
        def __exit__(self,*args):self.thread.join(timeout=1)
    class Input:
        def __iter__(self):
            while True:
                item=controls.get(timeout=12);yield json.dumps(item)+'\n'
                if item['kind']=='stop':break
    def emit(event):
        events.append(event)
        if event['kind']=='local_dictation' and event['recording']:recording.set()
        if event['kind']=='local_asr_held':held.set()
        if event['kind']=='local_asr_resumed':resumed.set()
        if sum(e['kind']=='local_heard' for e in events)==1:controls.put({'kind':'stop'})
    sys.modules['sounddevice']=types.SimpleNamespace(RawInputStream=Stream,query_devices=lambda *a,**kw:{'name':'Synthetic input'})
    sys.modules['speech_asr']=types.SimpleNamespace(SpeechASR=ASR,normalized_transcript=lambda value:value)
    sys.modules['torch']=types.SimpleNamespace(cuda=types.SimpleNamespace(device_count=lambda:0))
    sys.stdin=Input()
    local_mic_worker.run({'asr_model':'qwen_asr_06b','asr_gpu':'dual','asr_language':'id'},emit)
    if errors:raise AssertionError(errors)
    heard=[e for e in events if e['kind']=='local_heard'];commands=[e for e in events if e['kind']=='local_transcript']
    assert len(heard)==1 and len(commands)==1,(heard,commands)
    assert heard[0]['text']==' '.join(texts),heard
    assert len([e for e in events if e['kind']=='local_heard_partial'])==5
    assert heard[0]['accepted'] and fed.is_set() and len(loaded)==(2 if hold else 1)
    return {'hold_test':hold,'synthetic':True,'microphone_opened':False,'gpu_used':False,'agent_executed':False,
        'full_turn_count':len(heard),'command_count':len(commands),'asr_parts':len(calls),'full_turn':heard[0]['text'],
        'capture_continued_while_asr_waited':True,'model_load_count':len(loaded),'no_partial_execution':True,
        'manual_commit_joins_all_five_parts':True}

proof=[probe(),probe(hold=True)]
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-session-v0215');out.mkdir(parents=True,exist_ok=True)
(out/'worker-protocol.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
print(json.dumps(proof))
