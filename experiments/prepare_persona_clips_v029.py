import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from preferences import Preferences
from voice_pack_service import VoicePackService
from task_reactions import prepare_reaction
from leva_persona import ACKS,acknowledgement_speech
from speech_resources import pipeline_gpu
from pipeline_routing import route_spec
from paths import DATA
prefs=Preferences();pack=prefs.get('target_voice_pack');lang=prefs.get('speech_language');gpu=pipeline_gpu(route_spec(prefs.get('provider'),prefs.get('dual_gpu')),'tts',prefs.get('tts_gpu'));prefs.close()
service=VoicePackService(persistent=True);rows=[];began=time.perf_counter()
try:
 for phrases in ACKS.values():
  for phrase in phrases:
   result=prepare_reaction(pack,lang,gpu,service=service,speech=acknowledgement_speech(phrase,lang),stop_service=False)
   rows.append({'text':phrase,'path':result['path'],'cached':result['cached']})
 report={'pack':pack,'language':lang,'gpu':gpu,'clips':rows,'wall_s':time.perf_counter()-began,'speaker_opened':False,'microphone_opened':False}
 (DATA/'verification/conversation-reliability-v029/persona-clips.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in report.items() if k!='clips'},ensure_ascii=True),flush=True)
finally:service.stop()
