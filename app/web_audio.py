"""Bounded, ephemeral WAV delivery. No paths or microphone recordings reach clients."""
from collections import deque
import io
from pathlib import Path
import secrets
import threading
import time
import wave


class WebAudio:
    def __init__(self, max_bytes=24 * 1024 * 1024, max_clips=12, ttl=90, clock=time.monotonic):
        self.lock = threading.RLock()
        self.max_bytes, self.max_clips, self.ttl, self.clock = max_bytes, max_clips, ttl, clock
        self.epoch = secrets.token_hex(12)
        self.sequence = 0
        self.clips = deque()

    def _prune(self):
        now = self.clock()
        while self.clips and (now - self.clips[0]['at'] > self.ttl or len(self.clips) > self.max_clips or sum(len(c['data']) for c in self.clips) > self.max_bytes):
            self.clips.popleft()

    def publish(self, path, metadata=None):
        path = Path(path)
        if not 44 <= path.stat().st_size <= min(self.max_bytes, 12 * 1024 * 1024):
            raise ValueError('web_audio_size_limit')
        raw = path.read_bytes()
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            rate, frames = audio.getframerate(), audio.getnframes()
            duration = frames / rate
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or rate not in (22050, 24000) or not .1 <= duration <= 150:
                raise ValueError('invalid_web_audio')
            if len(audio.readframes(frames)) != frames * 2:
                raise ValueError('truncated_web_audio')
        metadata = metadata or {}
        with self.lock:
            self.sequence += 1
            item = {'seq': self.sequence, 'at': self.clock(), 'data': raw,
                    'duration': round(duration, 3), 'pack': str(metadata.get('pack', ''))[:80],
                    'language': metadata.get('language', 'id')}
            self.clips.append(item)
            self._prune()
            return self.sequence

    def cancel(self):
        with self.lock:
            self.clips.clear()
            self.epoch = secrets.token_hex(12)

    def manifest(self):
        with self.lock:
            self._prune()
            return {'epoch': self.epoch, 'latest': self.sequence, 'clips': [
                {'seq': c['seq'], 'duration': c['duration'], 'pack': c['pack'], 'language': c['language'],
                 'url': '/api/audio/' + self.epoch + '/' + str(c['seq']) + '.wav'} for c in self.clips]}

    def read(self, epoch, sequence):
        with self.lock:
            self._prune()
            if epoch != self.epoch:
                return None
            return next((c['data'] for c in self.clips if c['seq'] == sequence), None)
