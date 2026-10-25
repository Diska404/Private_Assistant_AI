"""One bounded real-model/real-voice probe. No microphone or physical output device.

Uses the user's current UV profile without changing settings. The PCM sink is a
fixture, explicitly distinct from audible headset/phone playback.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
os.environ['LEVA_AUDIO_DIAGNOSTICS']='0'
from chat_service import make_local
from live_speech_pipeline import LiveSpeechPipeline
from speech_resources import gpu_rows
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\realtime-voice-avatar-20261025')

def main():
    proof={'status':'running','profile':'user confirmed UV/clock restriction active',
           'model':'hauhau_qwen35_4b','voice':'higgs_leva','language':'ja',
           'microphone_opened':False,'physical_speaker_opened':False,'output_sink':'fixture',
           'events':[],'pcm_files':[],'text':''}
    def save():(OUT/'real-pipeline-smoke.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    engine=pipeline=None;started=time.monotonic();sink_bytes=[0]
    class Sink:
        def start(self):pass
        def write(self,raw):sink_bytes[0]+=len(raw)
        def stop(self):pass
        def abort(self):pass
        def close(self):pass
    def audio(path,metadata):
        destination=OUT/('pipeline-phrase-'+str(len(proof['pcm_files'])+1)+'.wav')
        shutil.copyfile(path,destination)
        proof['pcm_files'].append({'file':str(destination),'at_ms':round((time.monotonic()-started)*1000,2),'bytes':destination.stat().st_size})
    def event(value):proof['events'].append({**value,'at_ms':round((time.monotonic()-started)*1000,2)})
    def delta(value):
        if 'first_text_ms' not in proof:proof['first_text_ms']=round((time.monotonic()-started)*1000,2)
        proof['text']+=value;pipeline.feed(value)
    try:
        row=next(r for r in gpu_rows() if 'RTX 5070' in r['name'])
        if row['free_mib']<9500:raise ValueError('smoke_headroom_unavailable')
        proof['gpu_before']=subprocess.check_output(['nvidia-smi','--query-gpu=name,clocks.sm,memory.used','--format=csv,noheader'],text=True,creationflags=0x08000000).splitlines()
        engine=make_local({'local_model':proof['model'],'local_mode':'gpu5070','purpose':'room_companion_avatar'})
        engine.data_dir=OUT/'real-pipeline-llm';engine.max_output_tokens=48
        engine.start();proof['model_buffers_mib']=engine.model_gpu_buffers_mib
        pipeline=LiveSpeechPipeline('higgs_leva','ja','assistant','rtx5070',audio_callback=audio,
                                    output_factory=lambda rate:Sink(),native_stream=False)
        reply=engine.generate_stream([{'role':'user','content':'Jawab persis teks Jepang ini saja tanpa tambahan: レヴァだよ。準備できたよ。'}],delta,event)
        pipeline.feed('',final=True);proof['final_response']=reply;save()
        deadline=time.monotonic()+180
        while pipeline.active and time.monotonic()<deadline:
            pipeline.poll();save();time.sleep(.05)
        pipeline.poll()
        if pipeline.active:raise TimeoutError('pipeline_smoke_deadline')
        proof['pipeline_metrics']=json.loads(json.dumps(pipeline.metrics));proof['sink_bytes']=sink_bytes[0]
        if pipeline.metrics['failed'] or not proof['pcm_files']:raise RuntimeError('pipeline_no_complete_audio')
        proof['status']='completed'
    except Exception as error:proof['status']='failed';proof['error']=str(error)[:300]
    finally:
        if pipeline and pipeline.active:pipeline.cancel()
        if engine:engine.close()
        if pipeline:
            deadline=time.monotonic()+8
            while not pipeline.cleanup_done and time.monotonic()<deadline:time.sleep(.05)
            proof['speech_cleanup_done']=pipeline.cleanup_done
        proof['total_ms']=round((time.monotonic()-started)*1000,2);proof['llm_owned_process_released']=not engine or engine.process is None or engine.process.poll() is not None;save()
    print(json.dumps({k:proof[k] for k in ('status','total_ms')},ensure_ascii=False))
    return 0 if proof['status']=='completed' else 1

if __name__=='__main__':raise SystemExit(main())
