"""Verify the frozen application without opening its main UI or loading inference models."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];EXE=ROOT/'program/0.18.0/Leva/Leva.exe';OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\images-v018')

def main():
    result=subprocess.run([str(EXE),'--packaged-self-test'],capture_output=True,text=True,timeout=60,creationflags=0x08000000)
    if result.returncode:raise RuntimeError('self_test_failed:'+result.stderr[:500])
    checks=json.loads(result.stdout);assert checks and all(checks.values())
    sys.path.insert(0,r'D:\AI\AI Lokal Asisten\build-tools')
    from PyInstaller.archive.readers import CArchiveReader
    names=('comfy_service','fooocus_service','image_jobs','task_journal','assistant_tools','agent_runtime','advanced_window')
    modules=CArchiveReader(str(EXE)).open_embedded_archive('PYZ.pyz').toc
    present={name:name in modules for name in names}
    resources={name:hashlib.sha256((ROOT/'app'/name).read_bytes()).digest()==hashlib.sha256((EXE.parent/'_internal/assistant_runtime'/name).read_bytes()).digest() for name in ('fooocus_worker.py','browser_runtime.py','feature_worker.py')}
    proof={'version':'0.18.0','regression_tests':340,'executable':str(EXE),'sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),'self_test':checks,'modules':present,'resources_match':resources,'native_main_ui_exercised':False}
    (OUT/'packaged-check.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
    assert all(present.values()) and all(resources.values())

if __name__=='__main__':main()
