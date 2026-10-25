"""Private file-only Leva reference-conditioned candidate; not a trained Leva checkpoint."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models")
OUT = DATA / "verification/leva-openvoice-candidate"
PROFILE = MODELS / "Leva-GFL2/OpenVoice-candidate-v1"
VIDEO = Path(r"C:\Users\Raizei\Videos\VideoProc Converter AI\Cyberpunk 2077 Leva Voice Example.mp4")
TEXTS = [
    ("01_profil", "Halo, aku Leva. Profil Chrome mana yang ingin kamu buka?"),
    ("02_menunggu", "Baik, aku akan menunggu. Panggil aku kalau kamu membutuhkanku."),
    ("03_istirahat", "Sudah pukul empat pagi. Kamu masih ingin melanjutkan, atau beristirahat dulu?"),
]


def sha(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()


def audio_info(path):
    import soundfile as sf
    import numpy as np
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim != 1 or len(audio) < sr or not np.isfinite(audio).all():
        raise RuntimeError("invalid_audio")
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if peak < .001 or rms < .0001: raise RuntimeError("silent_audio")
    return {"path": str(path), "sample_rate": sr, "duration_seconds": round(len(audio)/sr, 4),
            "peak": round(peak, 6), "rms": round(rms, 6),
            "near_full_scale_fraction": round(float(np.mean(np.abs(audio) >= .9999)), 6), "sha256": sha(path)}


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
    proof = {"status": "preparing", "identity": "experimental Leva reference-conditioned voice candidate",
             "dedicated_leva_checkpoint_trained": False, "human_similarity_validated": False,
             "reference_rights": "not established for redistribution; user-provided video, private evaluation only",
             "microphone_opened": False, "speaker_opened": False, "audio_uploaded": False,
             "source_video_sha256": sha(VIDEO), "references": [], "base": [], "converted": [],
             "source_commit": manifest["commit"], "model_revision": manifest["model_revision"]}
    def save():
        (OUT / "proof.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False), encoding="utf-8")
    # Selected using V subtitle windows and offline ASR; not verified by speaker diarization.
    # Each reference remains separate: never use Delamain's dialogue as the target.
    for ident, start, duration in (("ref_v_a", 13.4, 6.2), ("ref_v_b", 64.0, 3.8)):
        reference = OUT / (ident + ".wav")
        if not reference.exists():
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(VIDEO),
                            "-t", str(duration), "-vn", "-ac", "1", "-ar", "22050", "-af", "highpass=f=70,lowpass=f=10000",
                            "-c:a", "pcm_s16le", str(reference)], check=True, creationflags=0x08000000)
        proof["references"].append({"start_seconds": start, "requested_duration": duration,
                                    "selection": "V subtitle + ASR window; speaker purity requires listening", **audio_info(reference)})
    import torch
    import numpy as np
    import soundfile as sf
    import librosa
    from piper import PiperVoice
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or "RTX 4050" not in torch.cuda.get_device_name(0):
        raise RuntimeError("rtx4050_cuda_unavailable")
    started = time.perf_counter()
    voice = PiperVoice.load(str(MODELS / "Piper-ID/id_ID-news_tts-medium.onnx"), use_cuda=False)
    proof["piper_load_seconds"] = round(time.perf_counter()-started, 4)
    for ident, text in TEXTS:
        path = OUT / (ident + "_piper.wav")
        started = time.perf_counter()
        with wave.open(str(path), "wb") as stream: voice.synthesize_wav(text, stream)
        proof["base"].append({"id": ident, "text": text, "synthesis_seconds": round(time.perf_counter()-started, 4), **audio_info(path)})
    del voice
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
    proof.update(engine_load_seconds=round(time.perf_counter()-started, 4), gpu_name=torch.cuda.get_device_name(0),
                 gpu_uuid=candidates[0], torch_version=torch.__version__, cuda_runtime=torch.version.cuda,
                 watermark={"enabled": True, "message": "LEVA", "model_sha256": manifest["watermark"]["sha256"]})
    started = time.perf_counter()
    target = converter.extract_se([r["path"] for r in proof["references"]], str(PROFILE / "target_se.pth"))
    torch.cuda.synchronize()
    proof["target_embedding_seconds"] = round(time.perf_counter()-started, 4)
    print(json.dumps({"state": "model_loaded", "gpu": proof["gpu_name"], "load_seconds": proof["engine_load_seconds"]}), flush=True)
    save()
    for pitch in (0, 6):
        sources = []
        for row in proof["base"]:
            path = Path(row["path"])
            if pitch:
                audio, sr = sf.read(path, dtype="float32")
                shifted = librosa.effects.pitch_shift(audio, sr=sr, n_steps=pitch)
                shifted *= min(1., .94/max(.001, float(np.abs(shifted).max())))
                path = OUT / (row["id"] + "_piper_pitch6.wav")
                sf.write(path, shifted, sr)
            sources.append(str(path))
        source = converter.extract_se(sources, str(PROFILE / f"source_piper_pitch{pitch}_se.pth"))
        for row, input_path in zip(proof["base"], sources):
            output = OUT / f"{row['id']}_leva_candidate_p{pitch:02d}.wav"
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            converter.convert(input_path, source, target, str(output), tau=.3, message="LEVA")
            torch.cuda.synchronize()
            elapsed = time.perf_counter()-started
            info = audio_info(output)
            if abs(info["duration_seconds"]-row["duration_seconds"]) > .2:
                raise RuntimeError("conversion_duration_mismatch")
            result = {"id": row["id"], "text": row["text"], "pitch_semitones": pitch,
                      "tau": .3, "conversion_seconds": round(elapsed, 4), **info,
                      "real_time_factor": round(elapsed/info["duration_seconds"], 4),
                      "torch_peak_allocated_mib": round(torch.cuda.max_memory_allocated()/1048576, 2),
                      "torch_peak_reserved_mib": round(torch.cuda.max_memory_reserved()/1048576, 2),
                      "first_conversion_in_process": not proof["converted"]}
            proof["converted"].append(result)
            save()
            print(json.dumps({"output": output.name, "seconds": round(elapsed, 3), "audio_seconds": info["duration_seconds"]}), flush=True)
    proof["status"] = "file_inference_completed_requires_reference_and_similarity_listening"
    profile = {"id": "leva_openvoice_candidate_v1", "engine": "OpenVoiceV2", "status": "experimental_not_default",
               "base_manifest": str(MODELS / "OpenVoiceV2/leva-candidate-manifest.json"),
               "references": proof["references"], "source_video_sha256": proof["source_video_sha256"],
               "target_embedding_sha256": sha(PROFILE / "target_se.pth"),
               "proof": str(OUT / "proof.json"), "rights": proof["reference_rights"],
               "human_similarity_validated": False, "streaming_verified": False}
    (PROFILE / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    save()
    print(json.dumps({"status": proof["status"], "outputs": len(proof["converted"]), "profile": str(PROFILE)}), flush=True)


if __name__ == "__main__": main()
