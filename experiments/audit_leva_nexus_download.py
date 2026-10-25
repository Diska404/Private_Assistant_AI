"""Read-only audit of the user-extracted Nexus files. Outputs only research metadata."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import soundfile as sf

SOURCE = Path(r"D:\AI\AI Lokal Asisten\Model Suara Leva")
OUT = Path(r"D:\AI\AI Lokal Asisten\Leva\research\leva-gfl2")
files = sorted(path for path in SOURCE.rglob("*") if path.is_file())
result = {"source": str(SOURCE), "mode": "read_only_no_extraction_or_inference", "file_count": len(files),
          "extensions": dict(Counter(p.suffix.lower() for p in files)), "model_files": [], "audio": [], "csv": [], "archives": []}
for path in files:
    relative = str(path.relative_to(SOURCE))
    if path.suffix.lower() in {".pth", ".ckpt", ".index", ".onnx", ".safetensors", ".pt", ".bin"}:
        result["model_files"].append(relative)
    elif path.suffix.lower() == ".ogg":
        try:
            info = sf.info(str(path))
            result["audio"].append({"file": relative, "duration": round(info.duration, 4),
                                     "samplerate": info.samplerate, "channels": info.channels,
                                     "format": info.format, "subtype": info.subtype, "bytes": path.stat().st_size})
        except Exception as error:
            result["audio"].append({"file": relative, "error": type(error).__name__})
    elif path.suffix.lower() == ".csv":
        with path.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result["csv"].append({"file": relative, "bytes": path.stat().st_size, "sha256": digest})
    elif path.suffix.lower() == ".archive":
        with path.open("rb") as stream:
            header = stream.read(40)
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result["archives"].append({"file": relative, "bytes": path.stat().st_size,
                                    "first40_hex": header.hex(), "magic_ascii": header[:4].decode("ascii", errors="replace"),
                                    "sha256": digest, "internal_contents_parsed": False})
good = [row for row in result["audio"] if "duration" in row]
result["audio_summary"] = {"readable_count": len(good), "unreadable_count": len(result["audio"])-len(good),
    "total_seconds": round(sum(row["duration"] for row in good), 2),
    "sample_rates": dict(Counter(row["samplerate"] for row in good)),
    "channels": dict(Counter(row["channels"] for row in good)),
    "min_seconds": min((row["duration"] for row in good), default=None),
    "max_seconds": max((row["duration"] for row in good), default=None),
    "formats": dict(Counter(row["format"] for row in good)),
    "subtypes": dict(Counter(row["subtype"] for row in good))}
ja = list(csv.DictReader((SOURCE / "SWATJudge/sub_ja.csv").open(encoding="utf-8-sig")))
keys = [row["Key"] for row in ja]
audio_keys = {Path(row["file"]).stem for row in good}
result["japanese_alignment"] = {"csv_rows": len(ja), "unique_keys": len(set(keys)),
    "audio_without_subtitle": sorted(audio_keys-set(keys)),
    "subtitle_without_audio": sorted(set(keys)-audio_keys), "duplicate_key_count": len(keys)-len(set(keys))}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "nexus-download-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "audio"}))
print(json.dumps({"reference_candidates": [row for row in good if 4 <= row["duration"] <= 10 and not any(
    token in row["file"].lower() for token in ("pain", "death", "bleedout", "scream", "breath"))][:15]}))
