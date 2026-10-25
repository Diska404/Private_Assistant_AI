"""Validate the final executable without opening microphone/models/main UI."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/web-v023')
EXE=ROOT/'program/0.23.0/Leva/Leva.exe'
result=subprocess.run([str(EXE),'--packaged-self-test'],capture_output=True,text=True,timeout=60,creationflags=0x08000000)
if result.returncode:raise RuntimeError('packaged_self_test_failed')
checks=json.loads(result.stdout)
if not checks or not all(v is True for v in checks.values()):raise RuntimeError('packaged_checks_failed:'+json.dumps(checks))
sys.path.insert(0,'D:/AI/AI Lokal Asisten/build-tools')
from PyInstaller.archive.readers import CArchiveReader
modules=CArchiveReader(str(EXE)).open_embedded_archive('PYZ.pyz').toc
names=('gui','chat_service','preferences','pipeline_routing','conversation_frontend','speech_pipeline_window',
       'speech_asr','speech_resources','mic_indicator','mic_recovery','mic_runtime_check','speech_turns','speech_log_window','local_mic_service','voice_core','provider_chain','agent_runtime','agent_contract','second_brain','second_brain_window','web_bridge','web_data','web_host','comfy_service','fooocus_service',
       'task_reactions','reply_voice','voice_pack_service','saluki_backend')
present={n:n in modules for n in names}
resources={}
for folder,names in [('assistant_runtime',('local_mic_worker.py','mic_capture.py','mic_capture_worker.py','local_audio_core.py','speech_turns.py','mic_indicator.py','mic_recovery.py','speech_asr.py','speech_resources.py','feature_worker.py')),
                     ('local_voice_runtime',('audio_cpp_voice.py','voice_pack_worker.py','voice_packs.py'))]:
    for name in names:resources[name]=hashlib.sha256((ROOT/'app'/name).read_bytes()).digest()==hashlib.sha256((EXE.parent/'_internal'/folder/name).read_bytes()).digest()
for name in ('index.html','app.js','graph.js','physics.js','style.css'):
    resources['leva_web/'+name]=hashlib.sha256((ROOT/'app/leva_web'/name).read_bytes()).digest()==hashlib.sha256((EXE.parent/'_internal/leva_web'/name).read_bytes()).digest()
proof={'version':'0.23.0','regression_tests':472,'executable':str(EXE),'sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),
       'self_test':checks,'modules':present,'resources_match':resources,'native_main_ui_exercised':False,
       'ui_route_widgets_exercised':False,'hidden_frozen_tk_web_button_exercised':checks.get('web_packaged_tk_button',False),'second_brain_widgets_exercised':True,'microphone_opened':False}
OUT.mkdir(parents=True,exist_ok=True);(OUT/'packaged-check.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
if not all(present.values()) or not all(resources.values()):raise RuntimeError('packaged_content_mismatch')
print(json.dumps({'self_tests':len(checks),'modules':present,'resources_match':resources,'sha256':proof['sha256']}))
