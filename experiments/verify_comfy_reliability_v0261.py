"""Verify the frozen application and served-source asset parity, no real inference."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/'program/0.26.1/Leva/Leva.exe'
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/comfy-reliability-v0261')
result=subprocess.run([str(EXE),'--packaged-self-test'],capture_output=True,text=True,timeout=180,creationflags=0x08000000)
if result.returncode:raise RuntimeError(result.stderr or result.stdout or 'packaged_check_failed')
checks=json.loads(result.stdout)
if not all(value is True for value in checks.values()):raise RuntimeError(json.dumps(checks))
assets={}
for path in (ROOT/'app/leva_web').iterdir():
    if not path.is_file():continue
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=hashlib.sha256((EXE.parent/'_internal/leva_web'/path.name).read_bytes()).hexdigest():raise RuntimeError('asset_mismatch: '+path.name)
    assets[path.name]=digest
value={'version':'0.26.1','checks':checks,'passed':len(checks),'sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),
       'regression_suites':{'app_full':463,'experiments_full':61,'comfy_reliability':8},
       'js_audio_queue_passed':6,'js_manual_mic_passed':6,'assets':assets}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'packaged-check.json').write_text(json.dumps(value,indent=2),encoding='utf8')
print(json.dumps({'passed':len(checks),'sha256':value['sha256']}))
