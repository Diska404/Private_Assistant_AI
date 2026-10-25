"""Voice identities and actual engine capabilities are deliberately separate."""
import hashlib
from array import array
import json
from pathlib import Path
import sys
import wave

from paths import DATA, ROOT

MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models")
PYTHON = DATA / "environments/voice-proof/Scripts/python.exe"
CANDIDATE_PYTHON = DATA / "environments/voice-leva-bilingual/Scripts/python.exe"
PIPER = MODELS / "Piper-ID/id_ID-news_tts-medium.onnx"
PIPER_HASHES = {
    "id_ID-news_tts-medium.onnx": "ed8f02aa593f7af6b19acbdb8142e0da0dd72f46194eb33d38e0eb10a52597e8",
    "id_ID-news_tts-medium.onnx.json": "1ef677072668a5e172e0759b1d3871f129009d1167f093325a17607f7add5ad7",
}
PACK_IDS = ("leva_gfl2", "higgs_leva", "higgs_native", "higgs_jp_identity", "omnivoice_leva", "omnivoice_native", "neutral_id", "shiroko_rvc")
PREVIEWS = DATA / "voice-pack-previews"

def voice_error_notice(code):
    if code=='voice_gpu_unsupported_for_engine':
        return 'Adapter Kokoro/Seed-VC lama hanya mendukung RTX 4050. Rute GPU tidak dialihkan; pilih rute 4050 atau engine Higgs/OmniVoice yang sesuai. Piper Indonesia tetap memakai CPU.'
    if code=='voice_gpu_headroom_unavailable':
        return 'VRAM untuk engine suara belum cukup. Lepaskan model lokal yang sedang siaga atau pilih OmniVoice/Piper di Voice Packs. Aplikasi lain tidak dihentikan.'
    return 'Keluaran suara berhenti: '+str(code)+'. Jawaban teks tetap tersedia.'


def resource(name):
    return Path(sys._MEIPASS) / name if getattr(sys, "frozen", False) else ROOT / "app" / name


def catalog():
    data = json.loads(resource("voice_packs.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported_voice_catalog")
    packs = {row["id"]: row for row in data["packs"]}
    if set(packs) != set(PACK_IDS):
        raise ValueError("invalid_voice_catalog")
    return packs


def candidate_available():
    profile=MODELS/'Leva-GFL2/SeedVC-bilingual-candidate-v3'
    return CANDIDATE_PYTHON.is_file() and all((profile/name).is_file() for name in ('reference_A.wav','profile.json')) and (MODELS/'Leva-Bilingual-v3/manifest.json').is_file()


def resolve_pack(requested, packs=None, runtime_available=None, candidate_ready=None):
    """No filename or display name can promote a pending voice to a working identity."""
    packs = catalog() if packs is None else packs
    if requested not in PACK_IDS:
        raise ValueError("unknown_voice_pack")
    if requested.startswith(('higgs_','omnivoice_')):
        from audio_cpp_voice import available
        usable=available(requested) and packs[requested]['engine']=='audio_cpp'
        return {'requested':requested,'actual':requested if usable else None,'available':usable,'fallback':False,
                'reason':packs[requested]['name']+' · GPU otomatis sesuai VRAM · '+('gaya dari konteks' if requested.startswith('higgs_') else 'pembanding tanpa tag emosi Higgs') if usable else 'Runtime/model suara belum tersedia.'}
    ready = (PYTHON.is_file() and all((PIPER.parent / name).is_file() for name in PIPER_HASHES)
             if runtime_available is None else runtime_available)
    candidate=candidate_available() if candidate_ready is None else candidate_ready
    if (requested=='leva_gfl2' and ready and candidate and packs[requested]['engine']=='piper_seedvc'
            and packs[requested]['status']=='candidate_file_proven'):
        return {'requested':requested,'actual':'leva_gfl2','available':True,'fallback':False,
                'reason':'Kandidat Leva A · Piper Indonesia → Seed-VC · RTX 4050; konversi per potongan, belum streaming engine.'}
    row = packs["neutral_id"]
    usable = ready and row["engine"] == "piper" and row["status"] == "file_proven"
    return {"requested": requested, "actual": "neutral_id" if usable else None,
            "fallback": requested != "neutral_id", "available": usable,
            "reason": ("Suara Indonesia netral sementara; target belum dapat dijalankan."
                       if requested != "neutral_id" else "TTS Indonesia netral lokal.") if usable
                      else "Runtime atau model Piper belum tersedia."}


def verify_piper(model=PIPER):
    for name, expected in PIPER_HASHES.items():
        path = model.parent / name
        if not path.is_file():
            raise ValueError("piper_asset_missing")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("piper_asset_hash_mismatch")


def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 600 or "\x00" in text:
        raise ValueError("invalid_preview_text")
    return text.strip()


def validate_preview(path, directory=PREVIEWS):
    path = Path(path).resolve()
    if not path.is_relative_to(directory.resolve()) or path.suffix.lower() != ".wav":
        raise ValueError("invalid_preview_path")
    if not path.is_file() or path.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("invalid_preview_file")
    with wave.open(str(path), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
        if (audio.getnchannels() != 1 or audio.getsampwidth() != 2
                or audio.getframerate() not in (22050,24000) or not .1 <= duration <= 150):
            raise ValueError("invalid_preview_audio")
        frames = audio.readframes(audio.getnframes())
        if len(frames) != audio.getnframes() * 2:
            raise ValueError("invalid_preview_audio")
        samples = array("h", frames)
        if not samples or max(abs(v) for v in samples) < 33:
            raise ValueError("silent_preview_audio")
    return path, duration
