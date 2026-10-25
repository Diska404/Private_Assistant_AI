"""Offline ASR for research of the user-provided showcase; never a training export."""
import json
from pathlib import Path
from faster_whisper import WhisperModel

DATA = Path(r"D:\AI\AI Lokal Asisten\Leva\research\leva-gfl2")
VIDEO = Path(r"C:\Users\Raizei\Videos\VideoProc Converter AI\Cyberpunk 2077 Leva Voice Example.mp4")
model = WhisperModel(r"D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small",
                     device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
segments, info = model.transcribe(str(VIDEO), beam_size=3, vad_filter=True)
result = {"source": str(VIDEO), "purpose": "showcase_analysis_only_not_training_or_cloning",
          "language": info.language, "language_probability": info.language_probability,
          "speaker_identification": "not_performed; contains multiple voices and background audio",
          "segments": []}
for segment in segments:
    result["segments"].append({"start": segment.start, "end": segment.end, "text": segment.text,
                               "no_speech_probability": segment.no_speech_prob})
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "video-asr.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"language": result["language"], "probability": round(info.language_probability, 3),
                  "segments": len(result["segments"]), "output": str(DATA / "video-asr.json")}))
