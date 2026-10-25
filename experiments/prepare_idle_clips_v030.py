import sys,json,time,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from preferences import Preferences
from voice_pack_service import VoicePackService
from task_reactions import prepare_reaction
from leva_persona import PersonaDelivery
from speech_resources import pipeline_gpu
from pipeline_routing import route_spec
from paths import DATA
prefs=Preferences();pack=prefs.get('target_voice_pack');lang=prefs.get('speech_language');gpu=pipeline_gpu(route_spec(prefs.get('provider'),prefs.get('dual_gpu')),'tts',prefs.get('tts_gpu'));prefs.close()
d=PersonaDelivery(random.Random(8));candidates={}
for room,apps in [('assistant',{}),('chat',{}),('secret',{}),('assistant',{'discord':True}),('assistant',{'chrome':True})]:
 for _ in range(450):
  row=d.standby(room,apps);spoken=row['speech_text'] if lang=='ja' else row['text'];candidates[spoken]=row
ordered=sorted(candidates.items(),key=lambda pair:({'secret':0,'chat':1,'assistant':2}[pair[1]['room']],pair[0]))
service=VoicePackService(persistent=True);rows=[];failures=[];retried=0;began=time.perf_counter();OUT=DATA/'verification/companion-presence-v030'
try:
 for spoken,row in ordered:
  try:result=prepare_reaction(pack,lang,gpu,service=service,speech=spoken,stop_service=False)
  except RuntimeError as error:
   service.stop();retried+=1
   try:result=prepare_reaction(pack,lang,gpu,service=service,speech=spoken,stop_service=False)
   except RuntimeError as again:
    failures.append({'room':row['room'],'code':str(again)});service.stop()
    if len(failures)>=4:break
    continue
  rows.append({'text':row['text'],'speech_text':spoken,'path':result['path'],'cached':result['cached'],'room':row['room']})
  if len(rows)%10==0:print('Cached',len(rows),'/',len(candidates),flush=True)
 report={'pack':pack,'language':lang,'gpu':gpu,'clips':rows,'wall_s':time.perf_counter()-began,'speaker_opened':False,'microphone_opened':False,'all_candidates':len(candidates),'retried_failed_parts':retried,'failures':failures}
 (OUT/'idle-clips.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in report.items() if k!='clips'},ensure_ascii=True),flush=True)
finally:service.stop()
