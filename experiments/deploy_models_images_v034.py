import sys,json,hashlib,sqlite3,shutil,subprocess,time,winreg,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from paths import DATA
from preferences import Preferences
EXE=DATA/'program/0.34.0/Leva/Leva.exe';OUT=DATA/'verification/model-expansion-v034'
check=json.loads((OUT/'packaged-check.json').read_text('utf8'))
assert check['passed']==88 and hashlib.sha256(EXE.read_bytes()).hexdigest()==check['sha256']
for name,digest in check['assets'].items():assert hashlib.sha256((EXE.parent/'_internal/leva_web'/name).read_bytes()).hexdigest()==digest
backup=DATA/'backups'/('before-models-and-images-v034-'+str(time.time_ns()));backup.mkdir(parents=True)
integrity={}
for source in list(DATA.glob('*.sqlite3'))+[DATA/'terminal/processes.sqlite3']:
 if not source.exists():continue
 dest=backup/source.relative_to(DATA);dest.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(dest) as dst:
  src.backup(dst);integrity[str(source.relative_to(DATA))]=dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert all(integrity.values())
import psutil
old_exe=DATA/'program/0.33.0/Leva/Leva.exe'
stopped=[]
for prior in psutil.process_iter(['pid','name','exe']):
 try:
  if prior.info['exe'] and Path(prior.info['exe']).resolve()==old_exe.resolve():
   prior.terminate();prior.wait(timeout=15);stopped.append(prior.pid)
 except (psutil.NoSuchProcess,psutil.AccessDenied):pass
if stopped:time.sleep(1)

link=ROOT/'Leva.lnk'
if link.exists():shutil.copy2(link,backup/link.name)
with sqlite3.connect(DATA/'web-control.sqlite3') as db:
 before_devices=db.execute('SELECT id,token_hash,expires,revoked FROM devices ORDER BY id').fetchall()
try:
 with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
  try:old_startup=winreg.QueryValueEx(key,'LevaAssistant')[0]
  except FileNotFoundError:old_startup=None
except FileNotFoundError:old_startup=None
prefs=Preferences();settings={k:prefs.get(k) for k in ('target_voice_pack','speech_language','speech_style','provider','dual_gpu','agent_provider','agent_gpu','agent_local_model','asr_model','asr_gpu','tts_gpu','always_listen','web_port','web_remote_enabled','web_remote_origin','companion_idle','companion_playful','companion_idle_delay','chat_model','chat_gpu','secret_model','secret_gpu','show_japanese')}
if old_startup is not None and prefs.get('autostart'):
 from autonomy_services import startup
 startup(True,EXE)
prefs.close()
(backup/'launch-metadata.json').write_text(json.dumps({'previous_startup':old_startup,'new_executable':str(EXE)},indent=2),encoding='utf8')
script=backup/'update-shortcut.ps1';script.write_text("""$taskShell=New-Object -ComObject WScript.Shell
$taskLink=$taskShell.CreateShortcut($args[0])
$taskLink.TargetPath=$args[1]
$taskLink.WorkingDirectory=$args[2]
$taskLink.Description='Leva — Asisten Desktop 0.34.0'
$taskLink.Save()
""",encoding='utf-8-sig')
subprocess.run(['powershell','-NoProfile','-File',str(script),str(link),str(EXE),str(ROOT)],check=True,creationflags=0x08000000)
proc=subprocess.Popen([str(EXE),'--quiet-start','--background'],cwd=str(ROOT),creationflags=0x08000000)
health=None
for _ in range(40):
 if proc.poll() is not None:raise RuntimeError('application_exited_'+str(proc.returncode))
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(settings['web_port'])+'/health',timeout=2) as response:health=json.load(response)
  break
 except Exception:time.sleep(.5)
with sqlite3.connect(DATA/'web-control.sqlite3') as db:after_devices=db.execute('SELECT id,token_hash,expires,revoked FROM devices ORDER BY id').fetchall()
prefs=Preferences();after={k:prefs.get(k) for k in settings};prefs.close()
assert settings==after and before_devices==after_devices
proof={'version':'0.34.0','backup':str(backup),'backup_integrity':integrity,'preferences_preserved':settings==after,'paired_devices_preserved':before_devices==after_devices,'paired_device_records':len(after_devices),'pid':proc.pid,'health':health,'previous_executable_retained':(DATA/'program/0.33.0/Leva/Leva.exe').is_file(),'shortcut_updated':True,'startup_updated_only_if_previously_enabled':True,'no_uv_or_driver_changes':True}
(OUT/'deployment-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof,ensure_ascii=True))
