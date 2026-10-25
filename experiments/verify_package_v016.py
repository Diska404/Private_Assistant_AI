"""Isolated final package checks; no GUI, credentials, network or model loading."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r'D:\AI\AI Lokal Asisten\Leva\verification\agent-foundation-v016')
EXE = ROOT / 'program/0.16.0/Leva/Leva.exe'


def main():
    result = subprocess.run([str(EXE), '--packaged-self-test'], capture_output=True,
                            text=True, timeout=60, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError('packaged_self_test_exit_' + str(result.returncode))
    checks = json.loads(result.stdout)
    if not checks or not all(value is True for value in checks.values()):
        raise RuntimeError('packaged_self_test_failed:' + json.dumps(checks))
    sys.path.insert(0, r'D:\AI\AI Lokal Asisten\build-tools')
    from PyInstaller.archive.readers import CArchiveReader
    modules = CArchiveReader(str(EXE)).open_embedded_archive('PYZ.pyz').toc
    names = ('terminal_service', 'project_workspace', 'local_connectors',
             'task_journal', 'agent_runtime', 'assistant_tools', 'receipt_state')
    present = {name: name in modules for name in names}
    resources = {}
    for name in ('feature_worker.py', 'browser_runtime.py', 'system_controls.py'):
        source = (ROOT / 'app' / name).read_bytes()
        packed = (EXE.parent / '_internal/assistant_runtime' / name).read_bytes()
        resources[name] = hashlib.sha256(source).hexdigest() == hashlib.sha256(packed).hexdigest()
    proof = dict(version='0.16.0', regression_tests=305,
                 executable=str(EXE), sha256=hashlib.sha256(EXE.read_bytes()).hexdigest(),
                 self_test=checks, modules=present, resource_hashes_match=resources,
                 gui_exercised=False)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'packaged-check.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps(proof), flush=True)
    if not all(present.values()) or not all(resources.values()):
        raise RuntimeError('package_content_mismatch')


if __name__ == '__main__':
    main()
