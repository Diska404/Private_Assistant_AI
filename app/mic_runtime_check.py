"""Explicit packaged-parent microphone check. No agent, recording, cloud or playback."""
import json
import os
import re
from pathlib import Path
import sys
import time
import ctypes
from paths import DATA

def check():
    from preferences import Preferences
    from pipeline_routing import route_spec
    from speech_resources import pipeline_gpu
    from local_mic_service import LocalMicService
    p=Preferences();spec=route_spec(p.get('provider'),p.get('dual_gpu'))
    request={k:p.get(k) for k in ('input_device_name','input_hostapi','asr_model','asr_language')};p.close()
    gpu=pipeline_gpu(spec,'asr');service=LocalMicService()
    proof={'frozen_parent':bool(getattr(sys,'frozen',False)),'parent_exe':sys.executable,'requested_gpu':gpu,
           'audio_persisted':False,'agent_executed':False,'speaker_opened':False,'meters':[],'status':None}
    hold_test='--check-asr-hold' in sys.argv;stage='initial';held_meters=0
    capture_handle=None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong];kernel.WaitForSingleObject.restype=ctypes.c_ulong
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    try:
        service.start(request['input_device_name'],request['input_hostapi'],request['asr_model'],gpu,request['asr_language'])
        until=time.monotonic()+55
        while time.monotonic()<until:
            for event in service.poll():
                if event['kind']=='local_status' and event.get('microphone_open'):
                    proof['status']={k:v for k,v in event.items() if k not in ('text',)}
                    if event.get('capture_pid') and capture_handle is None:capture_handle=kernel.OpenProcess(0x100000,False,event['capture_pid'])
                elif event['kind']=='local_meter':
                    proof['meters'].append({k:event.get(k) for k in ('rms','peak','threshold','phase')})
                    if stage=='held' and event.get('phase')=='buffering':held_meters+=1
                elif event['kind']=='local_asr_held':stage='held';proof['asr_hold_acknowledged']=True
                elif event['kind']=='local_asr_resumed':
                    proof['asr_resumed']=True;proof['capture_meters_while_asr_unloaded']=held_meters
                    proof['ok']=held_meters>=5;return proof
                elif event['kind']=='error':proof['error']=event;return proof
            if proof['status'] and len(proof['meters'])>=5 and stage=='initial':
                if not hold_test:proof['ok']=True;return proof
                service.request_asr_hold();stage='awaiting_hold'
            if stage=='held' and held_meters>=5:service.resume_asr();stage='resuming'
            time.sleep(.05)
        proof['error']={'code':'microphone_check_timeout'};return proof
    finally:
        service.stop();proof['worker_released']=not service.active
        proof['capture_worker_released']=bool(capture_handle and kernel.WaitForSingleObject(capture_handle,2000)==0)
        if capture_handle:kernel.CloseHandle(capture_handle)
        report=os.environ.get('LEVA_MIC_CHECK_REPORT','microphone-checks')
        if not re.fullmatch(r'[a-z0-9-]{1,64}',report):report='microphone-checks'
        folder=DATA/'verification'/report;folder.mkdir(parents=True,exist_ok=True)
        (folder/'frozen-microphone-check.json').write_text(json.dumps(proof,indent=2),encoding='utf8')
