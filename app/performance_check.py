"""Explicit cold/warm benchmark with the same model, prompt and voice quality settings."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from chat_service import ChatService
from paths import DATA
from reply_voice import ReplyVoice
from voice_pack_service import VoicePackService

def gpu_snapshot():
    try:return subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,utilization.gpu','--format=csv,noheader'],
        text=True,creationflags=0x08000000,timeout=10)
    except (OSError,subprocess.SubprocessError):return 'unavailable'

def check():
    out=DATA/'verification/efficiency-v09';out.mkdir(parents=True,exist_ok=True)
    chat=ChatService();voice=ReplyVoice(VoicePackService(persistent=True))
    proof={'status':'running','frozen':bool(getattr(sys,'frozen',False)),'microphone_opened':False,'network_used':False,
        'quality_settings':{'llm':'Saluki IQ2-mix MTP unchanged','thinking':False,'temperature':0,'context':4096,
            'voice':'candidate A','diffusion_steps':30,'cfg':0.7,'reference':'A'},'rounds':[],'gpu_before':gpu_snapshot(),
        'method':'Same short prompt, history cleared only in this benchmark for controlled comparison; production retains bounded history.'}
    if proof['frozen']:
        with Path(sys.executable).open('rb') as f:proof['exe_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    def save():(out/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    save()
    try:
        for phase in ('cold_first','warm_second','warm_third','warm_new_prompt','cold_after_release'):
            if phase=='cold_after_release':chat.cancel();voice.stop()
            chat.history=[]
            started=time.monotonic()
            prompt=('Jelaskan singkat dalam satu kalimat mengapa eGPU bisa lebih lambat daripada GPU desktop yang sama.' if phase=='warm_new_prompt'
                else 'Jawab persis satu kalimat ini tanpa tambahan: Halo, aku Leva. Aku siap membantu.')
            response=chat.ask(prompt,'local',local_model='saluki',acceleration='mtp',keep_warm=True)
            row={'phase':phase,'chat_ms':round((time.monotonic()-started)*1000,2),'response':response,
                'chat_worker_pid':chat.process.pid,'states':[]}
            proof['rounds'].append(row);save()
            voice_start=time.monotonic();voice.speak(response['response'],'leva_gfl2')
            row['voice_worker_pid']=voice.service.worker.process.pid
            deadline=time.monotonic()+180;copied=False
            while time.monotonic()<deadline:
                notices=voice.poll()
                if notices:raise RuntimeError(notices[0])
                if not row['states'] or voice.state!=row['states'][-1]['state']:
                    row['states'].append({'state':voice.state,'ms_since_voice_start':round((time.monotonic()-voice_start)*1000,2)})
                    if voice.state=='speaking':row['first_audio_ms']=round((time.monotonic()-started)*1000,2)
                if voice.service.generated and not copied:
                    destination=out/(phase+'.wav');shutil.copyfile(voice.service.generated,destination)
                    row['audio']=str(destination);row['voice_result']=voice.service.last_result;copied=True
                if not voice.active:break
                time.sleep(.02)
            else:raise TimeoutError('performance_voice_timeout')
            if 'first_audio_ms' not in row:raise RuntimeError('playback_not_observed')
            row['total_ms']=round((time.monotonic()-started)*1000,2)
            row['gpu_resident']=gpu_snapshot();save()
            print(json.dumps({'phase':phase,'chat_ms':row['chat_ms'],'first_audio_ms':row['first_audio_ms'],
                'voice_synthesis_seconds':row['voice_result']['total_seconds'],'seed_reused':row['voice_result']['seed_model_reused']}),flush=True)
        proof['same_answer_across_repeated_prompt']=len({r['response']['response'] for r in proof['rounds'] if r['phase']!='warm_new_prompt'})==1
        proof['status']='cold_warm_comparison_completed'
    except Exception as error:proof.update(status='failed',error=str(error))
    finally:
        chat.cancel();voice.stop()
        proof['workers_released']=chat.process is None and not voice.service.loaded
        proof['gpu_after_release']=gpu_snapshot();save()
    return proof
