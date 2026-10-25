import base64,io,json,queue,struct,tempfile,time,wave
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from speech_stream import receive_pcm
from stream_playback import StreamPlayback
from mic_indicator import OutputTelemetry

class Response(io.BytesIO):headers={'Content-Type':'text/event-stream'}
def event(kind,**fields):return b'data: '+json.dumps({'type':kind,**fields}).encode()+b'\n\n'
class Sink:
    def __init__(self,rate):self.rate=rate;self.data=bytearray();self.closed=False
    def start(self):pass
    def write(self,raw):self.data.extend(raw)
    def stop(self):pass
    def abort(self):pass
    def close(self):self.closed=True

class SpeechStreamTests(unittest.TestCase):
    def test_sse_preserves_pcm_and_requires_done_with_bounded_clips(self):
        raw=struct.pack('<h',1500)*50000
        sse=b''.join(event('speech.audio.delta',audio=base64.b64encode(raw[i:i+16000]).decode()) for i in range(0,len(raw),16000))+event('speech.audio.done')+b'data: [DONE]\n\n'
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'speech.wav';rows=[];result=receive_pcm(Response(sse),target,rows.append)
            with wave.open(str(target),'rb') as audio:self.assertEqual(audio.readframes(audio.getnframes()),raw)
            pieces=[]
            for row in rows:
                with wave.open(row['path'],'rb') as audio:
                    self.assertGreaterEqual(audio.getnframes()/audio.getframerate(),.1);pieces.append(audio.readframes(audio.getnframes()))
            self.assertEqual(b''.join(pieces),raw);self.assertTrue(result['stream_completed']);self.assertGreater(len(rows),1)
            with self.assertRaisesRegex(ValueError,'incomplete'):receive_pcm(Response(event('speech.audio.delta',audio=base64.b64encode(raw).decode())),target,lambda e:None)
            with self.assertRaises(ValueError):receive_pcm(Response(event('speech.audio.delta',audio='!bad')),target,lambda e:None)

    def test_one_output_stream_orders_packets_and_publishes_before_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            paths=[];expected=b''
            for i in range(3):
                path=Path(folder)/(str(i)+'.wav');raw=struct.pack('<h',500+i)*4000;expected+=raw
                with wave.open(str(path),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000);out.writeframes(raw)
                paths.append(path)
            owner=Mock();owner.output_telemetry=OutputTelemetry();owner.events=queue.Queue();published=[];owner.audio_ready_callback=lambda p,m:published.append(p)
            sink=Sink(24000);factory=Mock(return_value=sink);player=StreamPlayback(owner,factory)
            for i,path in enumerate(paths,1):player.offer(path,i)
            player.end();player.thread.join(3)
            self.assertFalse(player.active);self.assertEqual(bytes(sink.data),expected);self.assertEqual(published,paths);factory.assert_called_once_with(24000)
            kinds=[]
            while not owner.events.empty():kinds.append(owner.events.get()['kind'])
            self.assertEqual(kinds,['playback_started','playback_finished']);self.assertTrue(sink.closed)

    def test_stream_cancellation_is_prompt_and_missing_sequence_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'voice.wav'
            with wave.open(str(path),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000);out.writeframes(struct.pack('<h',500)*72000)
            owner=Mock();owner.output_telemetry=OutputTelemetry();owner.events=queue.Queue()
            sink=Sink(24000)
            def slow(raw):time.sleep(.02);sink.data.extend(raw)
            sink.write=slow;player=StreamPlayback(owner,lambda rate:sink)
            with self.assertRaises(ValueError):player.offer(path,2)
            # Failed sequence must not advance the expected ordering.
            self.assertEqual(player.sequence,0)
            player.offer(path,1);time.sleep(.05);began=time.monotonic();player.cancel()
            self.assertLess(time.monotonic()-began,.2);self.assertLess(len(sink.data),144000);self.assertFalse(owner.playing)

    def test_partial_audible_stream_never_retries_whole_sentence(self):
        from reply_voice import ReplyVoice
        voice=ReplyVoice(Mock());voice.current_text='Already partly played';voice.stream=Mock(audible=True)
        self.assertFalse(voice.recover('local_tts_failed'));voice.service.generate.assert_not_called()

    def test_production_defaults_to_stable_queue_and_stream_requires_explicit_opt_in(self):
        from voice_pack_service import VoicePackService
        service=VoicePackService(persistent=True)
        try:
            with patch('voice_pack_service.resolve_pack',return_value={'available':True,'actual':'higgs_leva','reason':'fixture'}),patch.object(service.worker,'start') as start:
                service.generate('higgs_leva','確認しましょう。','ja')
                self.assertFalse(start.call_args.kwargs['initial_message']['stream_audio'])
                service.stream_audio=True;service.generate('higgs_leva','確認しましょう。','ja')
                self.assertTrue(start.call_args.kwargs['initial_message']['stream_audio'])
        finally:service.stop()

if __name__=='__main__':unittest.main()
