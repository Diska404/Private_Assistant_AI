"""Exercise the application's real local voice adapter with new text (no microphone)."""
import argparse
import json
from pathlib import Path
import queue
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
from voice_pack_service import VoicePackService
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\spoken-replies-v08')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--play',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    service=VoicePackService(); proof={'status':'starting','microphone_opened':False,'events':[],'playback_requested':args.play}
    try:
        proof['resolution']=service.generate('leva_gfl2','Halo, aku Leva. Sekarang jawabanku juga bisa kamu dengarkan.')
        deadline=time.monotonic()+180; generated=False; playing=False
        while time.monotonic()<deadline:
            try:event=service.events.get_nowait()
            except queue.Empty:time.sleep(.05);event=None
            if event:
                proof['events'].append(event)
                if event['kind']=='error':raise RuntimeError(event['code'])
                if event['kind']=='generated':
                    service.accept_generated(event)
                    output=OUT/'candidate-A-new-reply.wav'
                    shutil.copyfile(service.generated,output)
                    proof['audio']=str(output);generated=True
                if event['kind']=='playback_finished':proof['status']='synthesis_and_playback_completed';break
            if generated and not service.worker.active:
                if not args.play:proof['status']='synthesis_completed';break
                if not playing:playing=service.play()
        else:raise TimeoutError('voice_probe_timeout')
    except Exception as error:proof.update(status='failed',error=str(error))
    finally:
        service.stop();proof['worker_released']=not service.active
        (OUT/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=True),flush=True)
