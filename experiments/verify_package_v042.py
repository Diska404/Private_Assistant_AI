"""Frozen checks and web parity; no model inference or live microphone."""
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
EXE=Path(r'D:\AI\AI Lokal Asisten\Leva\program\0.42.0\Leva\Leva.exe')
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-live2d-r01-20261026/performance')
def main():
 (EXE.parent/'project-root.txt').write_text(str(ROOT),encoding='utf8')
 result=subprocess.run([str(EXE),'--packaged-self-test'],capture_output=True,text=True,timeout=180,creationflags=0x08000000)
 if result.returncode:raise RuntimeError((result.stderr or result.stdout or 'package_selftest_failed')[-2000:])
 checks=json.loads(result.stdout);assets={}
 if not all(value is True for value in checks.values()):raise RuntimeError(json.dumps({k:v for k,v in checks.items() if v is not True}))
 for path in (ROOT/'app/leva_web').rglob('*'):
  if path.is_file():
   rel=path.relative_to(ROOT/'app/leva_web');target=EXE.parent/'_internal/leva_web'/rel
   digest=hashlib.sha256(path.read_bytes()).hexdigest()
   if not target.is_file() or digest!=hashlib.sha256(target.read_bytes()).hexdigest():raise RuntimeError('web_asset_mismatch: '+str(rel))
   assets[str(rel)]=digest
 proof={'version':'0.42.0','checks':checks,'passed':len(checks),'sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),'assets':assets,
   'normal_app_started':False,'production_preferences_changed':False,'real_audio_inference':False}
 (OUT/'packaged-check.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
 print(json.dumps({'passed':len(checks),'sha256':proof['sha256']}))
if __name__=='__main__':main()
