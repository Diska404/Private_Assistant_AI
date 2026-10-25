"""Reproduce an external worker's DLL environment without controlling the app UI."""
import ctypes,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/mic-recovery-v0213');OUT.mkdir(parents=True,exist_ok=True)
RUNTIME=ROOT/'program/0.21.2/Leva/_internal/assistant_runtime'
if '--child' in sys.argv:
    sys.path.insert(0,str(RUNTIME))
    try:
        import numpy as np
        from speech_asr import SpeechASR
        t=time.monotonic();engine=SpeechASR(gpu='dual')
        print(json.dumps({'ok':True,'gpu':engine.gpu['name'],'load_seconds':time.monotonic()-t}),flush=True)
    except Exception as error:
        traceback.print_exc()
        print(json.dumps({'ok':False,'type':type(error).__name__,'error':str(error)}),flush=True)
    raise SystemExit()

sys.path.insert(0,str(ROOT/'app'))
from speech_asr import ASR_PYTHON
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p];kernel.SetDllDirectoryW.restype=ctypes.c_bool
proof=[]
for label,folder in [('inherited_packaged_dll',str(RUNTIME.parent)),('clean_dll',None)]:
    if not kernel.SetDllDirectoryW(folder):raise ctypes.WinError(ctypes.get_last_error())
    try:
        result=subprocess.run([str(ASR_PYTHON),'-u','-B',str(Path(__file__).resolve()),'--child'],capture_output=True,text=True,
                              timeout=60,creationflags=0x08000000,env={**os.environ,'LEVA_MIC_DIAGNOSTICS':'0'})
    finally:kernel.SetDllDirectoryW(None)
    (OUT/(label+'.stderr.log')).write_text(result.stderr,encoding='utf8')
    row={'case':label,'exit_code':result.returncode,'stdout':result.stdout,'stderr_tail':result.stderr[-1800:]}
    proof.append(row);print(json.dumps(row),flush=True)
(OUT/'dll-reproduction.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
