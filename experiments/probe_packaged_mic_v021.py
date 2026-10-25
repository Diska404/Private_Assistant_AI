"""Open configured input briefly with the new external worker; never run a command."""
import json,os,queue,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from preferences import Preferences
from speech_asr import ASR_PYTHON
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021')
prefs=Preferences();request={key:prefs.get(key) for key in ('input_device_name','input_hostapi','asr_model','asr_language')};prefs.close()
request.update(asr_gpu='dual',wake_word='leva')
script=ROOT/'program/0.21.0/Leva/_internal/assistant_runtime/local_mic_worker.py'
events=queue.Queue();log=(out/'packaged-mic.stderr.log').open('w',encoding='utf8')
process=subprocess.Popen([str(ASR_PYTHON),'-B','-u',str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,
                         env={**os.environ,'LEVA_MIC_DIAGNOSTICS':'0'},creationflags=0x08000000)
def read():
    for line in process.stdout:
        try:events.put(json.loads(line))
        except ValueError:pass
threading.Thread(target=read,daemon=True).start()
try:
    process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
    deadline=time.monotonic()+40;status=None
    while time.monotonic()<deadline:
        event=events.get(timeout=40)
        if event.get('kind')=='error':raise RuntimeError(event['code'])
        if event.get('kind')=='local_status' and event.get('microphone_open'):
            status=event;break
    if not status:raise RuntimeError('no_microphone_ready')
    assert len(status['gpu_devices'])==2 and set(status['parameter_counts'])=={'cuda:0','cuda:1'}
    process.stdin.write('{"kind":"stop"}\n');process.stdin.flush();process.wait(timeout=8)
    proof={'packaged_worker':str(script),'status':status,'exit_code':process.returncode,
           'microphone_opened':True,'audio_persisted':False,'agent_actions_executed':False,'speaker_opened':False}
    (out/'packaged-mic.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
    print(json.dumps(proof))
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=8)
    log.close()
