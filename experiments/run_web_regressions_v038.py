"""Run the existing JS fixture scripts and preserve each exit code/output."""
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\pending-stage1-20261025')
rows=[]
for path in sorted((ROOT/'experiments').glob('test_*.mjs')):
 result=subprocess.run(['node',str(path)],capture_output=True,text=True,encoding='utf8',timeout=30,cwd=ROOT)
 rows.append({'file':path.name,'exit_code':result.returncode,'output':result.stdout+result.stderr})
(OUT/'javascript-tests.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'scripts':len(rows),'passed':sum(r['exit_code']==0 for r in rows)}))
if any(r['exit_code']!=0 for r in rows):raise SystemExit(1)
