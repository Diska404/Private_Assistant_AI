"""Explicit file-only integration diagnostic. Never opens audio devices or network."""
import json
from pathlib import Path
import queue
import shutil
import time

from paths import DATA
from voice_pack_service import VoicePackService


def check_runtime():
    service = VoicePackService()
    out = DATA / "verification/voice-packs-v06"
    out.mkdir(parents=True, exist_ok=True)
    result = {"target": "leva_gfl2", "leva_voice_proven": False,
              "microphone_opened": False, "speaker_opened": False, "network_used": False}
    try:
        result["resolution"] = service.generate("leva_gfl2", "Ini sampel baru untuk menguji pengelola suara. Suara yang sedang digunakan adalah bahasa Indonesia netral.")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                event = service.events.get_nowait()
            except queue.Empty:
                time.sleep(.03)
                continue
            if event.get("kind") == "error":
                raise RuntimeError(event.get("code"))
            if event.get("kind") == "generated":
                service.accept_generated(event)
                name = "neutral-preview-" + event["sha256"][:12] + ".wav"
                audio = out / name
                if not audio.exists():
                    shutil.copyfile(service.generated, audio)
                result["synthesis"] = {**event, "path": str(audio)}
                break
        else:
            raise RuntimeError("voice_pack_check_timeout")
    finally:
        service.stop()
    result["worker_released"] = not service.active
    result["preview_cleaned"] = service.folder is None
    (out / "runtime-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
