"""Verify capture launched by the actual new frozen executable, not a Python surrogate."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/voice-session-v0215');OUT.mkdir(parents=True,exist_ok=True)
status=Path('D:/AI/AI Lokal Asisten/Leva/status/local-microphone.json')
if status.is_file() and not (OUT/'original-status.json').exists():(OUT/'original-status.json').write_bytes(status.read_bytes())
exe=ROOT/'program/0.21.5/Leva/Leva.exe'
result=subprocess.run([str(exe),'--microphone-self-test','--check-asr-hold'],capture_output=True,text=True,timeout=70,
    env={**os.environ,'LEVA_MIC_DIAGNOSTICS':'0','LEVA_MIC_CHECK_REPORT':'voice-session-v0215'},creationflags=0x08000000,cwd=exe.parent)
(OUT/'frozen-parent.stderr.log').write_text(result.stderr,encoding='utf8')
proof=json.loads(result.stdout)
assert proof.get('ok'),proof
assert proof['frozen_parent'] and proof['worker_released']
assert len(proof['status']['gpu_devices'])==2
assert proof['asr_hold_acknowledged'] and proof['asr_resumed']
assert proof['capture_meters_while_asr_unloaded']>=5
(OUT/'frozen-microphone-check.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in proof.items() if k!='meters'}))
