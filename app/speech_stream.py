"""Bounded SSE PCM receiver for the installed audio.cpp speech contract."""
import base64
import json
from pathlib import Path
import time
import wave

def receive_pcm(response,output,emit,first_chunk_ms=640):
    if 'text/event-stream' not in response.headers.get('Content-Type',''):raise ValueError('invalid_voice_stream_type')
    started=time.monotonic();output=Path(output);pending=bytearray();total=0;sequence=0;done=False;first=None
    # Native rate for the installed Higgs v3 codec, mono signed PCM16LE.
    rate=24000;chunk_bytes=rate*2*64//100;minimum=rate*2//10
    if type(first_chunk_ms) is not int or not 100<=first_chunk_ms<=640:raise ValueError('invalid_voice_prebuffer')
    first_bytes=rate*2*first_chunk_ms//1000
    def publish(raw):
        nonlocal sequence
        sequence+=1
        if sequence>128:raise ValueError('voice_stream_chunk_limit')
        path=output.parent/('stream-'+str(sequence).zfill(4)+'.wav')
        with wave.open(str(path),'wb') as clip:clip.setnchannels(1);clip.setsampwidth(2);clip.setframerate(rate);clip.writeframes(raw)
        emit({'kind':'audio_delta','path':str(path),'sequence':sequence,'sample_rate':rate})
    with wave.open(str(output),'wb') as target:
        target.setnchannels(1);target.setsampwidth(2);target.setframerate(rate)
        while True:
            line=response.readline(2*1024*1024+1)
            if not line:break
            if len(line)>2*1024*1024:raise ValueError('invalid_voice_stream_event')
            if not line.startswith(b'data:'):continue
            data=line[5:].strip()
            if data==b'[DONE]':break
            row=json.loads(data)
            if row.get('type')=='speech.audio.delta':
                if done:raise ValueError('invalid_voice_stream_order')
                raw=base64.b64decode(row.get('audio',''),validate=True)
                if len(raw)%2:raise ValueError('invalid_voice_stream_pcm')
                total+=len(raw)
                if total>12*1024*1024:raise ValueError('voice_stream_size_limit')
                if raw and first is None:first=time.monotonic()-started
                target.writeframes(raw);pending.extend(raw)
                # Leave a tail so that the final clip is never shorter than the
                # preview validator's 100 ms; no synthetic padding or lost PCM.
                while len(pending)>=(first_bytes if sequence==0 else chunk_bytes)+minimum:
                    size=first_bytes if sequence==0 else chunk_bytes
                    publish(bytes(pending[:size]));del pending[:size]
            elif row.get('type')=='speech.audio.done':done=True
            elif row.get('type') in ('error','speech.audio.error'):raise ValueError('voice_stream_engine_error')
        if not done or not total:raise ValueError('voice_stream_incomplete')
        if len(pending)<minimum:raise ValueError('voice_stream_too_short')
        publish(bytes(pending))
    return {'stream_chunks':sequence,'pcm_bytes':total,'first_delta_seconds':first,'stream_completed':True}
