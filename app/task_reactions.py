"""Immediate, non-completion reactions. Cached audio never needs a model/GPU."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time

from paths import DATA
from voice_packs import PREVIEWS, resolve_pack, validate_preview

TEXT = 'Tunggu sebentar, aku sedang memeriksa permintaanmu.'
SPEECH = {'id': TEXT, 'ja': '少し待ってね。今、お願いを確認しているよ。'}
CACHE = PREVIEWS / 'task-reactions-v1'


def cache_key(pack, language, speech=None):
    if language not in SPEECH: raise ValueError('unsupported_voice_language')
    return hashlib.sha256(json.dumps([pack, language, 'assistant', SPEECH[language] if speech is None else speech], ensure_ascii=False).encode()).hexdigest()


def cached_reaction(pack, language, root=None, speech=None):
    """Reject wrong identities, corrupt audio and changed wording instead of guessing."""
    folder = Path(root) if root is not None else CACHE
    key = cache_key(pack, language, speech)
    try:
        row = json.loads((folder / (key + '.json')).read_text('utf-8'))
        path = folder / (key + '.wav')
        if row.get('key') != key or row.get('actual_pack') != pack: return None
        validate_preview(path, directory=folder)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']: return None
        return path
    except (OSError, ValueError, KeyError): return None


def prepare_reaction(pack, language, gpu='auto', service=None, root=None, cancelled=lambda:False, speech=None, stop_service=True):
    """Explicit idle preparation, file synthesis only. Never play or open a microphone."""
    old = cached_reaction(pack, language, root, speech)
    if old: return {'cached': True, 'path': str(old), 'actual_pack': pack}
    resolved = resolve_pack(pack)
    if not resolved['available'] or resolved['actual'] != pack:
        raise ValueError('reaction_identity_unavailable')
    from voice_pack_service import VoicePackService
    voice = service or VoicePackService(persistent=True)
    voice.gpu_preference = gpu
    folder = Path(root) if root is not None else CACHE
    folder.mkdir(parents=True, exist_ok=True)
    key = cache_key(pack, language, speech)
    spoken = SPEECH[language] if speech is None else speech
    started = time.perf_counter()
    try:
        voice.generate(pack, spoken, language=language, style='assistant')
        while time.perf_counter() - started < 180:
            if cancelled():raise RuntimeError('reaction_prepare_cancelled')
            event = voice.events.get_nowait() if not voice.events.empty() else None
            if not event:
                if voice.check_timeout(): raise RuntimeError('reaction_prepare_timeout')
                time.sleep(.03); continue
            if event.get('kind') == 'error': raise RuntimeError(event.get('code', 'reaction_prepare_failed'))
            if event.get('kind') != 'generated': continue
            voice.accept_generated(event)
            # Commit audio before manifest; readers validate the hash in either order.
            with tempfile.NamedTemporaryFile(dir=folder, suffix='.wav', delete=False) as tmp:
                temporary = Path(tmp.name)
            try:
                shutil.copyfile(voice.generated, temporary)
                validate_preview(temporary, directory=folder)
                digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
                temporary.replace(folder / (key + '.wav'))
            finally: temporary.unlink(missing_ok=True)
            row = {'key': key, 'actual_pack': pack, 'language': language, 'speech_text': spoken,
                   'sha256': digest, 'prepare_seconds': round(time.perf_counter()-started, 4),
                   'synthesis': event, 'microphone_opened': False, 'speaker_opened': False}
            (folder / (key + '.json')).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
            return {**row, 'path': str(folder / (key + '.wav')), 'cached': False}
        raise RuntimeError('reaction_prepare_timeout')
    finally:
        if stop_service:voice.stop()


def needs_reaction(text):
    from conversation_frontend import ACTION_WORDS
    import re
    if re.match(r'^(?:leva[, ]*)?(?:jeda|jedakan|pause|bekukan|matikan sistem)', text, re.I): return False
    return bool(ACTION_WORDS.search(text))
