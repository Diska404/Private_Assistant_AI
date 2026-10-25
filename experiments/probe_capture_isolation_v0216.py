"""Real headset capture while the ASR parent deliberately holds the GIL for 2.2s."""
import ctypes,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from mic_capture import CaptureProcess
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-agent-v0216');out.mkdir(parents=True,exist_ok=True)
count=[0]
def receive(pcm,*args):count[0]+=len(pcm)
request={'input_device_name':'Microphone (DAXA SL1 )','input_hostapi':'MME'}
with CaptureProcess(request,receive) as capture:
    time.sleep(.6);before=dict(capture.health);before_bytes=count[0]
    # PyDLL keeps the GIL held, unlike WinDLL; only the owned capture child can
    # continue servicing Python callbacks during this controlled parent stall.
    sleep=ctypes.PyDLL('kernel32').Sleep;sleep.argtypes=[ctypes.c_uint32];sleep(2200)
    time.sleep(.8);capture.check();health=dict(capture.health)
    proof={'real_microphone':True,'model_loaded':False,'audio_saved':False,'parent_gil_stall_ms':2200,
           'capture_pid':capture.process.pid,'device':capture.info,'health_before':before,'health_after':health,
           'bytes_delivered_after_stall':count[0]-before_bytes,'pcm_total_bytes':count[0]}
    assert health['queue_dropped_frames']==0 and health['input_overflows']==0,proof
    assert proof['bytes_delivered_after_stall']>=64000,proof
proof['capture_child_released']=capture.process.poll() is not None
(out/'capture-isolation.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
