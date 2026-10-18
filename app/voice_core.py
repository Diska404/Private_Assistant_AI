"""Bounded audio buffers and transport-independent voice state helpers."""
from array import array
from collections import deque
import math
import queue
import re
import threading

STATES = ("idle", "connecting", "listening", "thinking", "speaking", "clarifying", "interrupted", "sleeping", "error")


class VoiceEvents:
    """Coalesce meters so a busy GUI never loses terminal events to audio progress."""
    def __init__(self, capacity=128):
        self.events = deque(maxlen=capacity)
        self.meter = None
        self.lock = threading.Lock()

    def put_nowait(self, event):
        with self.lock:
            if event.get("kind") == "meter":
                self.meter = event
            else:
                if event.get("kind") in {"error", "stopped"}:
                    self.meter = None
                self.events.append(event)

    put = put_nowait

    def get_nowait(self):
        with self.lock:
            if self.events:
                return self.events.popleft()
            if self.meter is not None:
                meter,self.meter = self.meter,None
                return meter
            raise queue.Empty

    def empty(self):
        with self.lock:
            return not self.events and self.meter is None


def preferred_device(devices, saved_name, default):
    """Restore a unique device name, never silently switch a saved microphone."""
    if saved_name:
        matches = [d["id"] for d in devices if d["name"] == saved_name]
        return matches[0] if len(matches) == 1 else None
    return default if any(d["id"] == default for d in devices) else None


VOICE_ERRORS = {
    "live_quota_or_capacity": "Kuota atau kapasitas Google Live belum tersedia. Coba nanti atau gunakan teks lokal.",
    "live_access_or_model_rejected": "Google menolak akses sesi suara. Periksa akses API/model pada akun Anda.",
    "audio_output_backlog": "Audio menumpuk terlalu lama. Sesi dihentikan agar ucapan lama tidak diputar.",
    "audio_device_unavailable": "Perangkat audio tidak dapat digunakan. Segarkan perangkat dan pilih ulang mikrofon/headset.",
    "live_connection_or_audio_error": "Koneksi atau stream suara terputus. Periksa jaringan/perangkat, lalu mulai sesi baru.",
    "voice_worker_unexpected_exit": "Worker suara berhenti sebelum sesi selesai. Mulai lagi atau gunakan teks lokal.",
}


def direct_command(text):
    """Explicit opt-in still required by UI; models cannot invoke this function themselves."""
    value=text.casefold().strip()
    if not re.match(r"^leva\b",value):
        return False
    value=re.sub(r"^leva[\s,.:]+","",value)
    if re.search(r"\b(contoh|jangan|bukan|tidak|nggak|kalau|jika)\b",value):
        return False
    if re.match(r"^(?:buka|bukakan|bukain)\b",value):
        return bool(re.search(r"\b(chrome|youtube)\b",value))
    return bool(re.match(r"^(?:jeda|jedakan|bekukan|aktifkan|lanjutkan|batalkan jadwal|batalkan tidur)\b",value))


def pcm_level(data):
    if not data:
        return 0.0
    samples = array("h")
    samples.frombytes(bytes(data)[:len(data) // 2 * 2])
    return min(1.0, math.sqrt(sum(x*x for x in samples) / max(1, len(samples))) / 7000)


class PlaybackBuffer:
    """Drops the entire queued response on barge-in; never replays stale speech."""
    def __init__(self, max_bytes=24000 * 2 * 18):
        self.data = bytearray()
        self.max_bytes = max_bytes
        self.lock = threading.Lock()

    def push(self, data):
        with self.lock:
            if len(self.data) + len(data) > self.max_bytes:
                raise BufferError("voice_playback_backlog")
            self.data.extend(data)

    def pop(self, count):
        with self.lock:
            data = bytes(self.data[:count])
            del self.data[:count]
        return data, data + bytes(count - len(data))

    def clear(self):
        with self.lock:
            self.data.clear()

    def __len__(self):
        with self.lock:
            return len(self.data)


def voice_setup(model="gemini-3.8-live", voice="Kore", manual_activity=False):
    instruction = (
        "Kamu Leva, asisten pribadi berbahasa Indonesia yang tenang, perhatian, tanggap dan sedikit jenaka. "
        "Ini mode suara pratinjau Leva Desktop 0.3. Jawab singkat, alami, dan beri ruang pengguna menyela. "
        "Jangan mengaku sebagai karakter anime asli. Kamu tidak memiliki tools komputer pada saluran ini. "
        "Jangan mengaku membuka aplikasi, mencari web, mengubah pengaturan atau membuat jadwal. "
        "Tindakan komputer ditangani aplikasi lokal terpisah: pengguna bisa meninjau transkrip dan "
        "menekan Jalankan perintah, atau mengaktifkan opsi perintah langsung berawalan Leva. Hasil tindakan "
        "ditampilkan oleh aplikasi. Jangan menebak hasilnya atau mengucapkan ulang kalimat perintah "
        "berawalan Leva yang bisa terbaca sebagai perintah. Jika ambigu, tanyakan klarifikasi. "
        "Suara ini suara bawaan Google; belum suara Shiroko."
    )
    return {"setup": {
        "model": "models/" + model,
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
        "systemInstruction": {"parts": [{"text": instruction}]},
        "inputAudioTranscription": {}, "outputAudioTranscription": {},
        "realtimeInputConfig": {"automaticActivityDetection": {"disabled": manual_activity},
                                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS"},
    }}
