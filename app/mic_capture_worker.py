"""Microphone-only subprocess: no torch, model, network or audio files."""
import base64,json,queue,sys,threading,time

def main():
    import sounddevice as sd
    request=json.loads(sys.stdin.readline());audio=queue.Queue(maxsize=300);closed=threading.Event()
    health={'input_overflows':0,'queue_dropped_frames':0,'captured_frames':0,'callbacks':0}
    def emit(value):sys.stdout.write(json.dumps(value,ensure_ascii=True)+'\n');sys.stdout.flush()
    def callback(indata,frames,stamp,status):
        # Keep the PortAudio callback short. IPC encoding happens outside it.
        flags=[name for name in ('input_overflow','input_underflow','output_overflow','output_underflow','priming_output') if getattr(status,name,False)] if status else []
        health['callbacks']+=1;health['captured_frames']+=frames
        if 'input_overflow' in flags:health['input_overflows']+=1
        try:audio.put_nowait((bytes(indata),time.monotonic(),flags))
        except queue.Full:health['queue_dropped_frames']+=frames
    name=request.get('input_device_name');host=request.get('input_hostapi');device=None
    if name:
        matches=[i for i,row in enumerate(sd.query_devices()) if row['max_input_channels']>0 and row['name']==name and (not host or sd.query_hostapis(row['hostapi'])['name']==host)]
        if not matches:raise ValueError('microphone_not_found')
        device=matches[0]
    def read():
        for _ in sys.stdin:pass
        closed.set()
    threading.Thread(target=read,daemon=True).start()
    with sd.RawInputStream(samplerate=16000,blocksize=1600,latency='high',channels=1,dtype='int16',device=device,callback=callback):
        row=sd.query_devices(device,kind='input')
        emit({'kind':'capture_ready','device_name':row['name'],'hostapi':sd.query_hostapis(row['hostapi'])['name']})
        while not closed.is_set():
            try:pcm,stamp,flags=audio.get(timeout=.1)
            except queue.Empty:continue
            emit({'kind':'capture_audio','pcm':base64.b64encode(pcm).decode('ascii'),'stamp':stamp,'flags':flags,
                  'health':{**health,'queued_packets':audio.qsize()}})

if __name__=='__main__':
    try:main()
    except Exception as error:
        sys.stdout.write(json.dumps({'kind':'capture_error','code':str(error) if isinstance(error,ValueError) else type(error).__name__,'message':str(error)[:400]})+'\n');sys.stdout.flush()
