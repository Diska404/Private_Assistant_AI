"""Actual selected ASR worker on cached synthetic speech, no live mic or cloud."""
from pathlib import Path
import audioop,io,json,sys,time,wave
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from preferences import Preferences
from speech_configuration import configuration_snapshot
from pipeline_routing import route_spec
from remote_speech import RemoteSpeech
from task_reactions import cached_reaction
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/independent-devices-v0272');OUT.mkdir(parents=True,exist_ok=True)
prefs=Preferences(OUT/'isolated-preferences.sqlite3')
try:config=configuration_snapshot(prefs,route_spec('RTX 4050'))
finally:prefs.close()
path=cached_reaction('higgs_leva','id')
if path is None:raise RuntimeError('cached_synthetic_audio_missing')
with wave.open(str(path),'rb') as f:pcm=f.readframes(f.getnframes());rate=f.getframerate();channels=f.getnchannels();width=f.getsampwidth()
if width!=2:raise RuntimeError('pcm16_required')
if channels==2:pcm=audioop.tomono(pcm,2,.5,.5)
pcm,_=audioop.ratecv(pcm,2,1,rate,16000,None);buffer=io.BytesIO()
with wave.open(buffer,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
speech=RemoteSpeech();started=time.monotonic()
try:
    speech.submit('independent-asr-proof','fixture',buffer.getvalue())
    speech.pump({'model':config['values']['asr_model'],'gpu':config['effective']['asr_gpu'],'language':'id'},lambda _:True,lambda:None)
    while speech.pending() and time.monotonic()-started<135:time.sleep(.2)
    result=speech.get('independent-asr-proof','fixture')
    result.update(wall_seconds=round(time.monotonic()-started,3),audio_seconds=round(len(pcm)/32000,3),configuration=config,microphone_opened=False,speaker_opened=False,agent_called=False,cloud_called=False,fixture='cached synthetic Indonesian assistant speech')
    (OUT/'real-asr-proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    if result['status']!='completed':raise SystemExit(1)
    assert result['metrics']['requested_gpu']=='rtx5070'
    assert len(result['metrics']['executed_gpu_names'])==1 and '5070' in result['metrics']['executed_gpu_names'][0]
    assert set(result['metrics']['parameter_counts'])=={'cuda:0'}
    assert all(ms>0 for ms in result['metrics']['module_forward_cuda_ms'].values())
finally:speech.stop()
