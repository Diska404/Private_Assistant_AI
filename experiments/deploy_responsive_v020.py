"""Back up launch state and install the verified local package; no preference reset."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import winreg

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from preferences import Preferences
from task_reactions import cached_reaction
OUT=DATA/'verification/responsive-v020'
exe=ROOT/'program/0.20.0/Leva/Leva.exe'
check=json.loads((OUT/'packaged-check.json').read_text('utf-8'))
if hashlib.sha256(exe.read_bytes()).hexdigest()!=check['sha256']:raise RuntimeError('package_changed_after_verification')
backup=DATA/'backups'/('before-responsive-v020-'+str(time.time_ns()))
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
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        try:old_startup=winreg.QueryValueEx(key,'LevaAssistant')[0]
        except FileNotFoundError:old_startup=None
except FileNotFoundError:old_startup=None
(backup/'launch-metadata.json').write_text(json.dumps({'previous_startup':old_startup,'new_executable':str(exe)},indent=2),encoding='utf-8')
prefs=Preferences()
preserved={key:prefs.get(key) for key in ('target_voice_pack','speech_language','speech_style','provider','dual_gpu','agent_gpu','agent_local_model','always_listen')}
if old_startup is not None and prefs.get('autostart'):
    from autonomy_services import startup
    startup(True,exe)
prefs.close()
# Fixed paths are passed as literal arguments to PowerShell's COM API.
script="""$taskShell=New-Object -ComObject WScript.Shell
$taskLink=$taskShell.CreateShortcut($args[0])
$taskLink.TargetPath=$args[1]
$taskLink.WorkingDirectory=$args[2]
$taskLink.Description='Leva — Asisten Desktop 0.20.0'
$taskLink.Save()
"""
# Use a saved script plus -File arguments; no shell interpolation of path values.
script_path=backup/'update-shortcut.ps1'
script_path.write_text(script,encoding='utf-8-sig')
subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script_path),str(link),str(exe),str(ROOT)],check=True,creationflags=0x08000000)
proof={'version':'0.20.0','backup':str(backup),'backup_integrity':integrity,'preserved':preserved,
       'reaction_cache':{language:bool(cached_reaction(preserved['target_voice_pack'],language)) for language in ('id','ja')},
       'previous_executable_retained':(ROOT/'program/0.19.0/Leva/Leva.exe').is_file(),
       'main_window_opened':False,'no_uv_or_driver_changes':True}
(OUT/'deployment-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof))
