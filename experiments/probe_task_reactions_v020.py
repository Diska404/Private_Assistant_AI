"""Generate the selected voice's reaction once, then prove CPU-only replay readiness.

No microphone or speaker opens. The PCM output stream is a sink for timing only.
"""
from pathlib import Path
import json
import sys
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from preferences import Preferences
from task_reactions import prepare_reaction,cached_reaction
from voice_pack_service import VoicePackService
from test_task_reactions import TaskReactionTests

OUT=DATA/'verification/responsive-v020';OUT.mkdir(parents=True,exist_ok=True)
proof={'microphone_opened':False,'speaker_opened':False,'real_agent_workload':False,
       'pcm_sink_not_hardware_latency':True,'reaction_samples':[],'pipeline_checks':[]}
prefs=Preferences();pack=prefs.get('target_voice_pack');gpu=prefs.get('tts_gpu');prefs.close()
for language in ('ja','id'):
    try:
        row=prepare_reaction(pack,language,gpu)
        proof['reaction_samples'].append({'language':language,**row})
        print(json.dumps({'language':language,'cached':row['cached'],'prepare_seconds':row.get('prepare_seconds'),'path':row['path']}),flush=True)
    except Exception as error:
        proof['reaction_samples'].append({'language':language,'error':str(error)})
        print(json.dumps({'language':language,'error':str(error)}),flush=True)
    (OUT/'reaction-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')

for language in ('ja','id'):
    path=cached_reaction(pack,language)
    if not path:continue
    samples=[]
    for _ in range(3):
        voice=VoicePackService(persistent=True);first=[];started=time.perf_counter();done=threading.Event()
        class Sink:
            def __init__(self,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):done.set()
            def write(self,pcm):
                if not first:first.append(round((time.perf_counter()-started)*1000,3))
            def abort(self):pass
        with patch('sounddevice.RawOutputStream',Sink):
            voice.use_cached(path,pack);ready_ms=round((time.perf_counter()-started)*1000,3)
            assert not voice.worker.active
            voice.play();assert done.wait(3)
            samples.append({'ready_ms':ready_ms,'first_pcm_sink_write_ms':first[0],'gpu_worker_started':voice.worker.active})
            voice.stop()
    proof.setdefault('cached_replay',{})[language]=samples

fixture=TaskReactionTests()
for language in ('id','ja'):
    m=fixture.window(language);gate=threading.Event();entered=threading.Event()
    m.desktop.handle.return_value={'kind':'chat'}
    def agent(*args,**kwargs):
        entered.set();gate.wait(5)
        return {'response':'Pengujian terisolasi selesai. Tidak ada aplikasi dibuka.',
                'speech_text':'隔離したテストが終わったよ。アプリは開いていないよ。' if language=='ja' else 'Pengujian terisolasi selesai. Tidak ada aplikasi dibuka.',
                'provider':'local'}
    m.chat.ask.side_effect=agent
    with patch('task_reactions.cached_reaction',return_value=None):
        start=time.perf_counter();m.send('Buat alur ComfyUI tanpa generate.')
        assert entered.wait(2)
        during={'language':language,'reaction_ms':m.last_reaction_ms,'agent_waiting':m.busy,
                'frontend_model_calls':m.frontend.ask.call_count,'original_goal':m.chat.ask.call_args.args[0]}
        time.sleep(1);gate.set()
        deadline=time.monotonic()+3;result=None
        while time.monotonic()<deadline:
            if m.events.empty():time.sleep(.01);continue
            event=m.events.get()
            if event[1].get('response') or event[1].get('error'):result=event;break
        assert result is not None
        during['final_text_ms']=result[1].get('text_ready_ms')
        during['reply']=result[1].get('response');proof['pipeline_checks'].append(during)

(OUT/'reaction-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cached_replay':proof.get('cached_replay'),'pipeline_checks':proof['pipeline_checks']}),flush=True)
