"""Local intelligibility probe, not a voice-identity or human listening score."""
import json
import argparse
from pathlib import Path
import re
from faster_whisper import WhisperModel

parser = argparse.ArgumentParser()
parser.add_argument("--folder", default=r"D:\AI\AI Lokal Asisten\Leva\verification\leva-openvoice-candidate")
parser.add_argument("--skip-base", action="store_true")
args = parser.parse_args()
OUT = Path(args.folder)
proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
model = WhisperModel(r"D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small", device="cpu",
                     compute_type="int8", cpu_threads=4, local_files_only=True)


def words(text): return re.sub(r"[^\w\s]", " ", text.casefold()).split()


def wer(reference, actual):
    ref, hyp = words(reference), words(actual)
    previous = list(range(len(hyp)+1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(word != other)))
        previous = current
    return {"word_errors": previous[-1], "reference_word_count": len(ref),
            "wer": round(previous[-1]/max(1, len(ref)), 4)}


results = {"model": "faster-whisper-small / CPU int8", "purpose": "ASR proxy only; human similarity not assessed", "rows": []}
for category in ("base", "converted", "references"):
    if args.skip_base and category == "base": continue
    for row in proof[category]:
        kwargs = {"language": "id"} if category != "references" else {}
        segments, info = model.transcribe(row["path"], beam_size=3, vad_filter=True, **kwargs)
        text = " ".join(segment.text.strip() for segment in segments)
        item = {"category": category, "file": Path(row["path"]).name, "transcript": text,
                "language": info.language, "language_probability": round(info.language_probability, 4)}
        if row.get("text"): item.update(wer(row["text"], text))
        results["rows"].append(item)
        print(json.dumps(item, ensure_ascii=True), flush=True)
        (OUT / "asr-check.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
