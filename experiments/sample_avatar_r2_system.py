"""Global device telemetry during the interactive QA window, not per-avatar attribution."""
from pathlib import Path
import collections,json,subprocess,time,psutil
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-premium-avatar-r2\performance')
rows=[]
for i in range(30):
 start=time.monotonic();groups=collections.defaultdict(lambda:{'processes':0,'rss_mib':0})
 for p in psutil.process_iter(['name','memory_info']):
  name=(p.info['name'] or '').lower()
  if any(k in name for k in ('chrome','msedge','codex')):
   groups[name]['processes']+=1;groups[name]['rss_mib']+=round(p.info['memory_info'].rss/1024**2,2)
 try:
  result=subprocess.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total,clocks.gr,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,creationflags=0x08000000)
  gpu=[dict(zip(('name','utilization_percent','used_mib','total_mib','clock_mhz','temperature_c'),[v.strip() for v in line.split(',')])) for line in result.stdout.splitlines()]
 except Exception as e:gpu=[{'error':type(e).__name__}]
 rows.append({'sample':i,'monotonic':start,'cpu_percent_global':psutil.cpu_percent(),'ram_used_gib':round(psutil.virtual_memory().used/1024**3,3),'browser_process_groups':dict(groups),'gpus':gpu})
 (OUT/'system-telemetry.json').write_text(json.dumps({'scope':'Global laptop/device and entire browser process families; other apps/tabs active; not exclusive avatar consumption. No settings changed.','samples':rows},indent=2),encoding='utf8')
 time.sleep(max(0,3-(time.monotonic()-start)))
print(json.dumps({'samples':len(rows),'report':'system-telemetry.json'}))
