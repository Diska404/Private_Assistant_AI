"""Verify capture launched by the actual new frozen executable, not a Python surrogate."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/mic-recovery-v0213');OUT.mkdir(parents=True,exist_ok=True)
status=Path('D:/AI/AI Lokal Asisten/Leva/status/local-microphone.json')
if status.is_file() and not (OUT/'original-status.json').exists():(OUT/'original-status.json').write_bytes(status.read_bytes())
exe=ROOT/'program/0.21.3/Leva/Leva.exe'
result=subprocess.run([str(exe),'--microphone-self-test'],capture_output=True,text=True,timeout=70,
    env={**os.environ,'LEVA_MIC_DIAGNOSTICS':'0'},creationflags=0x08000000,cwd=exe.parent)
(OUT/'frozen-parent.stderr.log').write_text(result.stderr,encoding='utf8')
proof=json.loads(result.stdout)
assert proof.get('ok'),proof
assert proof['frozen_parent'] and proof['worker_released']
assert len(proof['status']['gpu_devices'])==2
assert len(proof['meters'])>=5
print(json.dumps(proof))
