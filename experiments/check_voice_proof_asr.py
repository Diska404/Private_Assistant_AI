"""Independent local ASR sanity check; does not measure voice identity or live latency."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

OUT = Path(r"D:\AI\AI Lokal Asisten\Leva\verification\shiroko-voice-proof")


def words(text):
    return re.findall(r"\w+", text.casefold())


def distance(first, last):
    row = list(range(len(last) + 1))
    for i, a in enumerate(first, 1):
        new = [i]
        for j, b in enumerate(last, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = new
    return row[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-only", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from faster_whisper import WhisperModel
    model = WhisperModel(r"D:\AI\AI Lokal Asisten\AI Models\faster-whisper-small", device="cpu",
                         compute_type="int8", cpu_threads=4, num_workers=1, local_files_only=True)
    proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
    inputs = proof["base"] + ([] if args.base_only else proof.get("converted", []))
    results = {"method": "faster-whisper-small CPU int8; language=id; no initial prompt", "human_reviewed": False,
               "note": "Synthetic-file intelligibility sanity check only; ASR errors are not exact speech errors, voice similarity or live latency", "files": []}
    for row in inputs:
        started = time.perf_counter()
        segments, info = model.transcribe(row["path"], language="id", beam_size=5, vad_filter=False,
                                          condition_on_previous_text=False)
        transcript = " ".join(s.text.strip() for s in segments)
        reference = words(row["text"])
        result = {"file": Path(row["path"]).name, "reference": row["text"], "asr_unreviewed": transcript,
                  "word_edit_rate": round(distance(reference, words(transcript)) / max(1, len(reference)), 4),
                  "asr_seconds": round(time.perf_counter() - started, 3)}
        results["files"].append(result)
        (OUT / ("asr-base.json" if args.base_only else "asr-check.json")).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
