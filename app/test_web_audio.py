"""Audio delivery lifecycle/authentication without inference, real speakers or mic."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import urllib.error
import urllib.request
import wave
from unittest.mock import Mock, patch

from web_audio import WebAudio
from web_bridge import WebBridge
from reply_voice import ReplyVoice
from voice_pack_service import VoicePackService
from voice_packs import PREVIEWS


def wav(path):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(24000)
        audio.writeframes(struct.pack('<h', 1000) * 4800)
    return path


class AudioDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = wav(Path(self.folder.name) / 'speech.wav')

    def test_bytes_outlive_owned_tts_temporary_file_but_manifest_has_no_path(self):
        store = WebAudio();original = self.path.read_bytes()
        store.publish(self.path, {'pack': 'test_identity', 'language': 'ja'})
        self.path.unlink()
        manifest = store.manifest()
        self.assertNotIn(str(self.path), json.dumps(manifest))
        self.assertEqual(manifest['clips'][0]['language'], 'ja')
        self.assertEqual(store.read(manifest['epoch'], 1), original)

    def test_cancel_invalidates_already_announced_url(self):
        store = WebAudio();store.publish(self.path)
        old = store.manifest();store.cancel();store.publish(self.path)
        self.assertIsNone(store.read(old['epoch'], 1))
        self.assertNotEqual(store.manifest()['epoch'], old['epoch'])
        self.assertEqual(len(store.manifest()['clips']), 1)

    def test_expiry_and_memory_bounds(self):
        now = [0];store = WebAudio(max_clips=2, ttl=2, clock=lambda: now[0])
        for _ in range(4):store.publish(self.path)
        self.assertEqual([c['seq'] for c in store.manifest()['clips']], [3, 4])
        now[0] = 3
        self.assertEqual(store.manifest()['clips'], [])
        self.assertIsNone(store.read(store.epoch, 4))
        store = WebAudio(max_bytes=self.path.stat().st_size * 2)
        for _ in range(3):store.publish(self.path)
        self.assertEqual(len(store.manifest()['clips']), 2)

    def test_rejects_oversized_and_non_wav_data(self):
        with self.assertRaises(ValueError):WebAudio(max_bytes=50).publish(self.path)
        self.path.write_bytes(b'x' * 100)
        with self.assertRaises((wave.Error, ValueError)):WebAudio().publish(self.path)

    def test_http_wav_requires_active_session_and_cancellation_returns_404(self):
        bridge = WebBridge(None, port=0);bridge.start();self.addCleanup(bridge.stop)
        bridge.publish_audio(self.path, {'pack': 'fixture'})
        clip = bridge.snapshot()['audio']['clips'][0]
        url = bridge.origin + clip['url']
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url)
        self.assertEqual(error.exception.code, 401)
        _, token = bridge.store.device('Isolated test client')
        request = urllib.request.Request(url, headers={'Cookie': 'leva_session=' + token})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.headers['Content-Type'], 'audio/wav')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.read(), self.path.read_bytes())
        bridge.cancel_audio()
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 404)
        ident = bridge.store.authenticate(token)['id'];bridge.store.revoke(ident)
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 401)

    def test_remote_audio_endpoint_cannot_read_file_path(self):
        bridge = WebBridge(None, port=0);bridge.start();self.addCleanup(bridge.stop)
        request = urllib.request.Request(bridge.origin + '/api/audio/../../preferences.sqlite3', headers={'Cookie': 'leva_session=' + bridge.cookie})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 404)

    def test_real_voice_play_publishes_copy_and_user_stop_invalidates_it(self):
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PREVIEWS) as folder:
            path = wav(Path(folder) / 'fixture.wav')
            service = VoicePackService();voice = ReplyVoice(service=service);store = WebAudio()
            voice.audio_cancel_callback = store.cancel;service.audio_ready_callback = store.publish
            sound = Mock();sound.query_devices.return_value = {'name': 'Fixture', 'hostapi': 0}
            sound.query_hostapis.return_value = {'name': 'Fixture'}
            sound.RawOutputStream.return_value.__enter__ = Mock(return_value=Mock())
            sound.RawOutputStream.return_value.__exit__ = Mock(return_value=False)
            with patch.dict('sys.modules', {'sounddevice': sound}),patch.object(service, 'audio_status'):
                voice.speak_cached(path, 'fixture', 'ja');voice.poll();service.play_thread.join(timeout=3)
                current = store.manifest()
                self.assertEqual(current['clips'][0]['language'], 'ja')
                self.assertEqual(current['clips'][0]['pack'], 'fixture')
                voice.poll()  # Local completion cleans the temporary file, not the browser copy.
                self.assertTrue(store.read(current['epoch'], current['latest']))
                voice.stop()
                self.assertIsNone(store.read(current['epoch'], current['latest']))

    def test_missing_laptop_output_does_not_cancel_valid_remote_audio(self):
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PREVIEWS) as folder:
            path = wav(Path(folder) / 'fixture.wav')
            service = VoicePackService();voice = ReplyVoice(service=service);store = WebAudio()
            voice.audio_cancel_callback = store.cancel;service.audio_ready_callback = store.publish
            sound = Mock();sound.query_devices.side_effect = RuntimeError('No local output')
            with patch.dict('sys.modules', {'sounddevice': sound}),patch.object(service, 'audio_status'):
                voice.speak_cached(path, 'fixture');voice.poll();service.play_thread.join(timeout=3)
                self.assertTrue(voice.poll())
                self.assertEqual(len(store.manifest()['clips']), 1)
            voice.stop()


if __name__ == '__main__':unittest.main()
