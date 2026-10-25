"""Compare three clean Nexus dialogues against the previous video-conditioned candidate."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from leva_openvoice_candidate import audio_info, sha

DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models")
SOURCE = Path(r"D:\AI\AI Lokal Asisten\Model Suara Leva\SWATJudge")
OLD = DATA / "verification/leva-openvoice-candidate"
OUT = DATA / "verification/leva-nexus-candidate-v2"
PROFILE = MODELS / "Leva-GFL2/OpenVoice-nexus-candidate-v2"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      HF_HOME=str(DATA / "cache/hf-openvoice"), NUMBA_CACHE_DIR=str(DATA / "cache/numba-openvoice"),
                      OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", TEMP=str(OUT), TMP=str(OUT))
    listing = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid,name", "--format=csv,noheader"], text=True)
    candidates = [line.split(",", 1)[0].strip() for line in listing.splitlines() if "RTX 4050" in line]
    if len(candidates) != 1: raise RuntimeError("expected_one_rtx4050")
    os.environ["CUDA_VISIBLE_DEVICES"] = candidates[0]
    manifest = json.loads((MODELS / "OpenVoiceV2/leva-candidate-manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"] + [manifest["watermark"]]:
        if sha(item["path"]) != item["sha256"]: raise RuntimeError("asset_hash_mismatch")
    original = json.loads((OLD / "proof.json").read_text(encoding="utf-8"))
    subtitles = {r["Key"]: r["Dialogue"] for r in csv.DictReader((SOURCE / "sub_ja.csv").open(encoding="utf-8-sig"))}
    import torch
    import librosa
    import numpy as np
    import soundfile as sf
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or "RTX 4050" not in torch.cuda.get_device_name(0):
        raise RuntimeError("rtx4050_unavailable")
    proof = {"status": "preparing", "identity": "Nexus Leva reference-conditioned candidate v2",
             "dedicated_leva_checkpoint_trained": False, "human_similarity_validated": False,
             "reference_rights": "author permission not received; user-supplied assets; local evaluation, not a redistribution license",
             "source_directory_modified": False, "microphone_opened": False, "speaker_opened": False,
             "audio_uploaded": False, "references": [], "base": [], "converted": [],
             "gpu_name": torch.cuda.get_device_name(0), "gpu_uuid": candidates[0],
             "torch_version": torch.__version__, "cuda_runtime": torch.version.cuda,
             "source_commit": manifest["commit"], "model_revision": manifest["model_revision"],
             "watermark": {"enabled": True, "message": "LEVA", "model_sha256": manifest["watermark"]["sha256"]}}
    def save(): (OUT / "proof.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False), encoding="utf-8")
    for ident in ("PanicRoom04_A_01", "PanicRoom04_A_02", "PanicRoom06_B_01"):
        path = SOURCE / (ident + ".ogg")
        before_hash = sha(path)
        info = sf.info(str(path))
        raw, sr = sf.read(str(path), dtype="float32")
        if raw.ndim != 1 or not np.isfinite(raw).all(): raise RuntimeError("invalid_reference")
        trimmed, interval = librosa.effects.trim(raw, top_db=35)
        trimmed = librosa.resample(trimmed, orig_sr=sr, target_sr=22050)
        reference = OUT / (ident + "_reference.wav")
        sf.write(reference, trimmed, 22050, subtype="PCM_16")
        proof["references"].append({"original_path": str(path), "original_sha256": before_hash,
            "original_format": info.format, "original_subtype": info.subtype, "original_rate": sr,
            "trim_interval_original_samples": [int(i) for i in interval],
            "reference_transcript": subtitles[ident], **audio_info(reference)})
    for row in original["base"]:
        target = OUT / Path(row["path"]).name
        shutil.copyfile(row["path"], target)
        if sha(target) != row["sha256"]: raise RuntimeError("base_copy_mismatch")
        proof["base"].append({**row, "path": str(target), "reused_from_v1": True})
    sys.path.insert(0, manifest["vendor"])
    import wavmark
    load_watermark = wavmark.load_model
    wavmark.load_model = lambda: load_watermark(manifest["watermark"]["path"])
    from openvoice.api import ToneColorConverter
    started = time.perf_counter()
    converter = ToneColorConverter(str(MODELS / "OpenVoiceV2/converter/config.json"), device="cuda:0")
    weights = torch.load(MODELS / "OpenVoiceV2/converter/checkpoint.pth", map_location="cpu", weights_only=True)
    converter.model.load_state_dict(weights["model"], strict=True)
    del weights
    torch.cuda.synchronize()
    proof["engine_load_seconds"] = round(time.perf_counter()-started, 4)
    started = time.perf_counter()
    target = converter.extract_se([r["path"] for r in proof["references"]], str(PROFILE / "target_se.pth"))
    torch.cuda.synchronize()
    proof["target_embedding_seconds"] = round(time.perf_counter()-started, 4)
    source = torch.load(MODELS / "Leva-GFL2/OpenVoice-candidate-v1/source_piper_pitch0_se.pth", map_location="cuda:0", weights_only=True)
    torch.save(source.cpu(), PROFILE / "source_piper_se.pth")
    save()
    for row in proof["base"]:
        output = OUT / (row["id"] + "_leva_nexus_candidate.wav")
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        converter.convert(row["path"], source, target, str(output), tau=.3, message="LEVA")
        torch.cuda.synchronize()
        elapsed = time.perf_counter()-started
        details = audio_info(output)
        if abs(details["duration_seconds"]-row["duration_seconds"]) > .2:
            raise RuntimeError("duration_mismatch")
        proof["converted"].append({"id": row["id"], "text": row["text"], "pitch_semitones": 0,
            "tau": .3, "conversion_seconds": round(elapsed, 4), "real_time_factor": round(elapsed/details["duration_seconds"], 4),
            "torch_peak_allocated_mib": round(torch.cuda.max_memory_allocated()/1048576, 2),
            "torch_peak_reserved_mib": round(torch.cuda.max_memory_reserved()/1048576, 2),
            "first_conversion_in_process": not proof["converted"], **details})
        save()
        print(json.dumps({"output": output.name, "seconds": round(elapsed, 3)}), flush=True)
    for row in proof["references"]:
        if sha(row["original_path"]) != row["original_sha256"]: raise RuntimeError("original_source_changed")
    proof["source_hashes_unchanged"] = True
    proof["status"] = "file_inference_completed_requires_similarity_listening"
    (PROFILE / "profile.json").write_text(json.dumps({"id": "leva_openvoice_nexus_candidate_v2", "status": "experimental_not_default",
        "engine": "OpenVoiceV2", "base_manifest": str(MODELS / "OpenVoiceV2/leva-candidate-manifest.json"),
        "target_embedding_sha256": sha(PROFILE / "target_se.pth"), "references": proof["references"],
        "proof": str(OUT / "proof.json"), "human_similarity_validated": False, "streaming_verified": False,
        "rights": proof["reference_rights"]}, indent=2, ensure_ascii=False), encoding="utf-8")
    save()
    print(json.dumps({"status": proof["status"], "profile": str(PROFILE)}), flush=True)


if __name__ == "__main__": main()
