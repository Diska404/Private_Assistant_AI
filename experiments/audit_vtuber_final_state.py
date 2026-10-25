"""Read-only process/Git/source audit; never records command-line credentials."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
import psutil
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\vtuber-model-trial-20261024')
before={}
with zipfile.ZipFile(OUT/'source-before.zip') as archive:
 for name in archive.namelist():
  if not name.endswith('/'):before[name.replace('\\','/')]=hashlib.sha256(archive.read(name)).hexdigest()
paths=[p for folder in ('app','experiments','docs') for p in (ROOT/folder).rglob('*') if p.is_file() and not any(v in p.parts for v in ('__pycache__','graphify-out')) and p.suffix in ('.py','.mjs','.js','.css','.html','.json','.md','.ps1')]
paths += [ROOT/n for n in ('LEVA_PROJECT.json','APP_README.md','PLANNED_UPDATES.md')]
after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
diff={'changed':[{'path':name,'before':before[name],'after':digest} for name,digest in after.items() if name in before and before[name]!=digest],
 'not_in_checkpoint':[{'path':name,'sha256':digest} for name,digest in after.items() if name not in before],
 'removed':[name for name in before if name not in after and not (ROOT/name).exists()],
 'baseline_scope':'selected app/experiments code/assets and LEVA_PROJECT; markdown/other omitted files are not necessarily newly created. graphify-out excluded from both comparisons'}
(OUT/'source-diff.json').write_text(json.dumps(diff,indent=2),encoding='utf8')
def git(*args):
 result=subprocess.run(['git','-C',str(ROOT/'github-export'),*args],capture_output=True,text=True,timeout=10)
 return result.stdout.strip()
processes=[]
for p in psutil.process_iter(['pid','name']):
 if p.info['name'].casefold() in ('remoting_host.exe','tailscaled.exe','tailscale-ipn.exe','leva.exe','llama-server.exe'):processes.append(p.info)
gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,temperature.gpu,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=10)
proof={'at':datetime.now().astimezone().isoformat(),'source_has_git':(ROOT/'.git').exists(),'source_version':json.loads((ROOT/'LEVA_PROJECT.json').read_text('utf8'))['version'],
 'export':{'branch':git('rev-parse','--abbrev-ref','HEAD'),'commit':git('rev-parse','HEAD'),'working_tree_porcelain':git('status','--porcelain')},
 'selected_processes':processes,'gpu':gpu.stdout.strip().splitlines(),'normal_gui_started_by_this_task':False,'remote_configuration_changed':False,
 'memory_available_gib':round(psutil.virtual_memory().available/1024**3,2),'disk_free_gib':{drive:round(psutil.disk_usage(drive+':/').free/1024**3,2) for drive in ('C','D','Y')}}
(OUT/'system-final.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
print(json.dumps({'source_changed':len(diff['changed']),'not_in_checkpoint':len(diff['not_in_checkpoint']),'source_removed':len(diff['removed']),'processes':processes,'export_clean':not proof['export']['working_tree_porcelain']}))
