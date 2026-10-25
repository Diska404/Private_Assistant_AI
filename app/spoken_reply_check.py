"""Explicit executable integration test: real local chat → candidate A → playback."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from chat_service import ChatService
from paths import DATA
from reply_voice import ReplyVoice

def check():
    out=DATA/'verification/spoken-chat-v08'
    out.mkdir(parents=True,exist_ok=True)
    chat=ChatService();voice=ReplyVoice()
    proof={'status':'starting','frozen':bool(getattr(sys,'frozen',False)),
        'microphone_opened':False,'network_used':False,'states':[],'audio':[]}
    if proof['frozen']:
        with Path(sys.executable).open('rb') as f:proof['exe_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    started=time.monotonic()
    try:
        result=chat.ask('Jawab hanya satu kalimat singkat dalam bahasa Indonesia: sapa aku dan sebut namamu.','local',keep_warm=False)
        proof['chat']=result
        proof['chat_seconds']=round(time.monotonic()-started,3)
        voice_start=time.monotonic()
        proof['resolution']=voice.speak(result['response'],'leva_gfl2')
        deadline=time.monotonic()+180
        seen=set()
        while time.monotonic()<deadline:
            notices=voice.poll()
            if notices:raise RuntimeError(notices[0])
            if not proof['states'] or voice.state!=proof['states'][-1]['state']:
                proof['states'].append({'state':voice.state,'seconds_since_tts_start':round(time.monotonic()-voice_start,3)})
            path=voice.service.generated
            if path and path.is_file() and str(path) not in seen:
                seen.add(str(path));dest=out/f'actual-reply-{len(seen)}.wav'
                shutil.copyfile(path,dest);proof['audio'].append(str(dest))
            if not voice.active:
                if not any(row['state']=='speaking' for row in proof['states']):raise RuntimeError('playback_not_observed')
                proof['status']='local_chat_synthesis_playback_completed';break
            time.sleep(.03)
        else:raise TimeoutError('spoken_chat_timeout')
    except Exception as error:proof.update(status='failed',error=str(error))
    finally:
        chat.cancel();voice.stop()
        proof['workers_released']=not voice.active and chat.process is None
        (out/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    return proof
