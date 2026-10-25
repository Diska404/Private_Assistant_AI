"""Reproduce the live app's environment/cwd; no command executor is connected."""
import contextlib,ctypes,json,os,queue,subprocess,sys,threading,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'program/0.21.2/Leva/_internal/assistant_runtime'
if '--child' in sys.argv:
    sys.path.insert(0,str(RUNTIME));protocol=sys.stdout;lock=threading.RLock()
    def emit(event):
        with lock:protocol.write(json.dumps(event,ensure_ascii=True)+'\n');protocol.flush()
    try:
        import local_mic_worker
        request=json.loads(sys.stdin.readline())
        with contextlib.redirect_stdout(sys.stderr):local_mic_worker.run(request,emit)
    except Exception as error:
        traceback.print_exc();emit({'kind':'error','code':type(error).__name__,'detail':str(error)})
    finally:emit({'kind':'stopped'})
    raise SystemExit()

sys.path.insert(0,str(ROOT/'app'))
from preferences import Preferences
from speech_asr import ASR_PYTHON
import psutil
parent=psutil.Process(57416);env=parent.environ();cwd=parent.cwd()
prefs=Preferences();request={k:prefs.get(k) for k in ('input_device_name','input_hostapi','asr_model','asr_language')};prefs.close()
request.update(asr_gpu='dual',wake_word='leva')
kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
kernel.SetDllDirectoryW(str(RUNTIME.parent))
out=Path('D:/AI/AI Lokal Asisten/Leva/verification/mic-recovery-v0213');out.mkdir(parents=True,exist_ok=True)
log=(out/'live-env.stderr.log').open('w',encoding='utf8');events=queue.Queue();rows=[]
try:
    process=subprocess.Popen([str(ASR_PYTHON),'-u','-B',str(Path(__file__).resolve()),'--child'],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=log,encoding='utf8',env={**env,'LEVA_MIC_DIAGNOSTICS':'0'},cwd=cwd,creationflags=0x08000000)
finally:kernel.SetDllDirectoryW(None)
def read():
    for line in process.stdout:
        try:events.put(json.loads(line))
        except ValueError:pass
threading.Thread(target=read,daemon=True).start()
try:
    process.stdin.write(json.dumps(request)+'\n');process.stdin.flush();meters=0;deadline=time.monotonic()+50
    while time.monotonic()<deadline:
        event=events.get(timeout=50)
        if event['kind']=='local_meter':meters+=1
        elif event['kind'] not in ('local_partial','local_transcript','local_heard'):rows.append(event)
        if event['kind']=='error' or meters>=5:break
    if process.poll() is None:
        process.stdin.write('{"kind":"stop"}\n');process.stdin.flush();process.wait(timeout=8)
    proof={'parent_pid':parent.pid,'parent_cwd':cwd,'events':rows,'meter_samples':meters,'agent_executed':False}
    (out/'live-env.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof))
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=5)
    log.close()
