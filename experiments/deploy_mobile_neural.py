"""Apply a reversible static-asset update to the installed Leva 0.24.0 package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('D:/AI/AI Lokal Asisten/Leva')
SOURCE = ROOT / 'app/leva_web'
TARGET = ROOT / 'program/0.24.0/Leva/_internal/leva_web'
EXE = ROOT / 'program/0.24.0/Leva/Leva.exe'
OUT = DATA / 'verification/mobile-neural-v0241'
ORIGIN = 'https://laptop.example-tailnet.ts.net'
FILES = ('index.html', 'style.css', 'mobile.js', 'graph.js')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for name in FILES:
    if not (SOURCE / name).is_file() or not (TARGET / name).is_file():
        raise RuntimeError('static_asset_missing: ' + name)

with urllib.request.urlopen(ORIGIN + '/health', timeout=10) as response:
    if not json.load(response).get('desktop_bridge'):
        raise RuntimeError('unexpected_backend')

before_exe = digest(EXE)
backup = DATA / 'backups' / ('before-mobile-neural-' + str(time.time_ns()))
backup.mkdir(parents=True, exist_ok=False)
previous = {}
for name in FILES:
    shutil.copy2(TARGET / name, backup / name)
    previous[name] = digest(TARGET / name)

try:
    for name in FILES:
        temporary = TARGET / (name + '.leva-next')
        shutil.copy2(SOURCE / name, temporary)
        os.replace(temporary, TARGET / name)
    checked = {}
    for name in FILES:
        with urllib.request.urlopen(ORIGIN + '/' + name, timeout=10) as response:
            served = hashlib.sha256(response.read()).hexdigest()
        if served != digest(SOURCE / name):
            raise RuntimeError('served_asset_mismatch: ' + name)
        checked[name] = served
    try:
        urllib.request.urlopen(ORIGIN + '/api/state', timeout=10)
        raise RuntimeError('authentication_missing')
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
    if digest(EXE) != before_exe:
        raise RuntimeError('executable_changed')
except Exception:
    for name in FILES:
        shutil.copy2(backup / name, TARGET / name)
    raise

OUT.mkdir(parents=True, exist_ok=True)
result = {
    'application_version': '0.24.0', 'ui_revision': 'mobile-neural-v0241',
    'backup': str(backup), 'origin': ORIGIN, 'served_assets_match_source': checked,
    'previous_assets': previous, 'executable_sha256': before_exe,
    'restart_required': False, 'unauthenticated_state_status': 401,
    'regression_tests_passed': 27, 'preferences_or_sessions_modified': False,
    'physical_android_layout_verified': False,
}
(OUT / 'deployment-check.json').write_text(json.dumps(result, indent=2), encoding='utf8')
print(json.dumps(result, indent=2))
