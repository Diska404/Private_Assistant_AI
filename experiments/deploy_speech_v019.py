"""Back up preferences/launch metadata and install the already-verified local package."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import winreg

ROOT=Path(__file__).resolve().parents[1]
DATA=Path('D:/AI/AI Lokal Asisten/Leva')
OUT=DATA/'verification/speech-v019'
exe=ROOT/'program/0.19.0/Leva/Leva.exe'
check=json.loads((OUT/'packaged-check.json').read_text('utf-8'))
if hashlib.sha256(exe.read_bytes()).hexdigest()!=check['sha256']:raise RuntimeError('package_changed_after_verification')
backup=DATA/'backups/20261021-before-speech-v019'
backup.mkdir(parents=True,exist_ok=False)
integrity={}
for name in ('preferences.sqlite3','tasks.sqlite3','scheduled-tasks.sqlite3','image-jobs.sqlite3'):
    source=DATA/name
    if not source.is_file():continue
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(backup/name) as dst:
        src.backup(dst);integrity[name]=dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
if not all(integrity.values()):raise RuntimeError('backup_integrity_failed')
link=ROOT/'Leva.lnk'
if link.is_file():shutil.copy2(link,backup/link.name)
with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
    try:old_startup=winreg.QueryValueEx(key,'LevaAssistant')[0]
    except FileNotFoundError:old_startup=None
(backup/'launch-metadata.json').write_text(json.dumps({'startup':old_startup,'new_executable':str(exe)},indent=2),encoding='utf-8')
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from preferences import Preferences
from pipeline_routing import visible_route,route_spec
prefs=Preferences()
voice={k:prefs.get(k) for k in ('target_voice_pack','speech_language','speech_style')}
current=route_spec(prefs.get('provider'))
single=current['gpu'] if current['gpu'] in ('rtx4050','rtx5070') else prefs.get('route_single_gpu')
prefs.set_many({'provider':visible_route(prefs.get('provider'),prefs.get('dual_gpu'),single),
    'route_single_gpu':single,'asr_model':'qwen_asr_06b','asr_gpu':'auto','asr_language':'id',
    'separate_agent':True,'always_listen':False})
if old_startup is not None and prefs.get('autostart'):
    from autonomy_services import startup
    startup(True,exe)
proof={'version':'0.19.0','backup':str(backup),'backup_integrity':integrity,
       'voice_preserved':voice,'provider':prefs.get('provider'),'dual_gpu':prefs.get('dual_gpu'),
       'asr_model':prefs.get('asr_model'),'always_listen':prefs.get('always_listen'),
       'agent_local_model':prefs.get('agent_local_model'),'previous_executable_retained':(ROOT/'program/0.18.0/Leva/Leva.exe').is_file(),
       'main_window_opened':False}
prefs.close()
(OUT/'deployment-check.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof))
