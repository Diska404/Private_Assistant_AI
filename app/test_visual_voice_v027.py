import io
import queue
from pathlib import Path
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock
from PIL import Image
from profile_avatar import ProfileAvatar
from web_bridge import WebBridge
from web_store import WebStore
from reply_voice import ReplyVoice,speech_chunks

def picture():
    buffer=io.BytesIO();Image.new('RGB',(80,120),'teal').save(buffer,'PNG');return buffer.getvalue()

class VisualVoiceTests(unittest.TestCase):
    def test_frozen_package_can_live_on_data_drive_with_validated_source_pointer(self):
        import json
        import sys
        from unittest.mock import patch
        from paths import project_root
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);source=root/'project';package=root/'package'
            source.mkdir();package.mkdir()
            (source/'LEVA_PROJECT.json').write_text(json.dumps({'name':'Leva'}),encoding='utf8')
            pointer=package/'project-root.txt';pointer.write_text(str(source),encoding='utf8')
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(package/'Leva.exe')):
                self.assertEqual(project_root(),source.resolve())
                pointer.write_text('invalid-relative-path',encoding='utf8')
                with self.assertRaises(RuntimeError):project_root()

    def test_avatar_normalization_and_hostile_input(self):
        with tempfile.TemporaryDirectory() as name:
            store=ProfileAvatar(name);self.assertFalse(store.metadata()['url'])
            result=store.save(picture());self.assertIn('/api/avatar?v=',result['url'])
            with Image.open(io.BytesIO(store.read())) as photo:self.assertEqual(photo.size,(512,512));self.assertFalse(photo.info)
            old=store.read()
            for raw in [b'<svg/>',b'not-an-image',b'x'*(5*1024*1024+1)]:
                with self.assertRaises(ValueError):store.save(raw)
                self.assertEqual(old,store.read())

    def test_avatar_requires_session_origin_and_syncs_across_clients(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);store=WebStore(root/'remote.sqlite3');self.addCleanup(store.close)
            bridge=WebBridge(None,port=0,store=store,avatar=ProfileAvatar(root/'profile'));bridge.start();self.addCleanup(bridge.stop)
            def post(headers):return urllib.request.urlopen(urllib.request.Request(bridge.origin+'/api/avatar',data=picture(),headers=headers))
            with self.assertRaises(urllib.error.HTTPError) as denied:post({'Origin':bridge.origin})
            self.assertEqual(denied.exception.code,401)
            headers={'Origin':bridge.origin,'Cookie':'leva_session='+bridge.cookie}
            with post(headers) as response:self.assertEqual(response.status,200)
            with self.assertRaises(urllib.error.HTTPError) as denied:post({**headers,'Origin':'https://evil.example'})
            self.assertEqual(denied.exception.code,403)
            _,token=store.device('Android fixture')
            request=urllib.request.Request(bridge.origin+'/api/avatar',headers={'Cookie':'leva_session='+token})
            with urllib.request.urlopen(request) as response:self.assertEqual(response.read(),bridge.avatar.read())
            bridge.stop();store.close()

    def test_long_japanese_no_24_chunk_ceiling_and_preserves_every_character(self):
        original='今日は予定を確認して、一緒に順番に進めましょう。'*140
        chunks=speech_chunks(original,'ja');self.assertGreater(len(chunks),24)
        self.assertEqual(''.join(chunks),original);self.assertTrue(all(len(c)<=90 for c in chunks))

    def test_retry_never_replays_completed_prefix_and_cancel_stops_retry(self):
        service=Mock(active=False,can_play=False);service.events=queue.Queue();service.check_timeout.return_value=False
        service.generate.return_value={'actual':'higgs_leva'}
        voice=ReplyVoice(service);voice.speak('最初の文章です。'+'次の文章について詳しく説明します。'*12,'higgs_leva','ja')
        prefix=voice.current_text;service.events.put({'kind':'playback_finished'});voice.poll()
        failed=voice.current_text;count=service.generate.call_count
        service.events.put({'kind':'error','code':'local_tts_failed'});self.assertTrue(voice.poll())
        self.assertEqual(service.generate.call_count,count+1);self.assertNotEqual(voice.current_text,prefix)
        self.assertIn(voice.current_text,failed);self.assertEqual(voice.completed_chunks,1)
        voice.cancel();self.assertFalse(voice.active);self.assertFalse(voice.pending)

    def test_retry_is_bounded_and_capacity_error_does_not_retry(self):
        for code in ['local_tts_failed','voice_gpu_headroom_unavailable']:
            service=Mock(active=False,can_play=False);service.events=queue.Queue();service.check_timeout.return_value=False;service.generate.return_value={'actual':'higgs_leva'}
            voice=ReplyVoice(service);voice.speak('こんにちは。'*30,'higgs_leva','ja')
            for i in range(5):service.events.put({'kind':'error','code':code});voice.poll()
            self.assertLessEqual(service.generate.call_count,4 if code=='local_tts_failed' else 1)

    def test_stop_invalidates_waiting_speech_without_cancelling_agent(self):
        from gui import LevaWindow
        main=LevaWindow.__new__(LevaWindow);main.generation=12;main._tts_waiting=True
        main.reply_voice=Mock();main.chat=Mock();main.frontend=Mock();main.closed=False
        main.root=Mock();main.desktop=Mock(paused=False,sleeping=False)
        main.stop_reply_voice();main.wait_voice_resources('stale voice','ja','assistant',12,0)
        self.assertFalse(main._tts_waiting);self.assertEqual(main._muted_voice_generation,12)
        main.chat.cancel.assert_not_called();main.frontend.cancel.assert_not_called();main.root.after.assert_not_called()
        main._translation_pending=True;main.stop_reply_voice()
        main.frontend.cancel.assert_called_once();main.chat.cancel.assert_not_called();self.assertFalse(main._translation_pending)

if __name__=='__main__':unittest.main()
