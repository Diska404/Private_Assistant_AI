"""Offline file-only Piper -> RVC experiment. Never opens microphone or playback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models")
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
OUT = DATA / "verification/shiroko-voice-proof"
VENDOR = ROOT / "experiments/vendor/Applio-c7be7282af0f7b6382cbb2ac780b11242da12916"
TEXTS = [
    ("01_sapaan", "Halo, aku Leva. Aku siap membantu kamu hari ini."),
    ("02_profil", "Untuk membuka Chrome, sebutkan profil yang ingin kamu gunakan."),
    ("03_jeda", "Kalau kamu ingin beristirahat, kamu bisa meminta aku untuk jeda."),
]


def save(proof):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "proof.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False), encoding="utf-8")


def audio_info(path):
    import numpy as np
    import soundfile as sf
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim != 1 or len(audio) < sr or not np.isfinite(audio).all():
        raise RuntimeError("Invalid or empty generated audio: " + str(path))
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if peak < .001 or rms < .0001:
        raise RuntimeError("Generated audio is effectively silent")
    return {"path": str(path), "sample_rate": sr, "duration_seconds": round(len(audio) / sr, 4),
            "peak": round(peak, 5), "rms": round(rms, 5), "near_full_scale_fraction": round(float(np.mean(np.abs(audio) >= .9999)), 6),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def make_tts(proof):
    from piper import PiperVoice
    started = time.perf_counter()
    voice = PiperVoice.load(str(MODELS / "Piper-ID/id_ID-news_tts-medium.onnx"), use_cuda=False)
    proof["tts_load_seconds"] = round(time.perf_counter() - started, 4)
    proof["tts_backend"] = "piper-tts 1.8.0 / ONNX CPU / id_ID-news_tts-medium"
    proof["base"] = []
    for ident, text in TEXTS:
        path = OUT / (ident + "_piper.wav")
        started = time.perf_counter()
        with wave.open(str(path), "wb") as stream:
            voice.synthesize_wav(text, stream)
        elapsed = time.perf_counter() - started
        row = {"id": ident, "text": text, **audio_info(path), "synthesis_seconds": round(elapsed, 4)}
        row["real_time_factor"] = round(elapsed / row["duration_seconds"], 4)
        proof["base"].append(row)
        save(proof)
        print(json.dumps({"tts": ident, "seconds": row["synthesis_seconds"], "audio_seconds": row["duration_seconds"]}), flush=True)


def convert(proof):
    listing = subprocess.check_output(["nvidia-smi", "--query-gpu=uuid,name", "--format=csv,noheader"], text=True)
    candidates = [line.split(",", 1)[0].strip() for line in listing.splitlines() if "RTX 4050" in line]
    if len(candidates) != 1:
        raise RuntimeError("Expected exactly one RTX 4050; do not silently select another GPU")
    uuid = candidates[0]
    os.environ["CUDA_VISIBLE_DEVICES"] = uuid
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HOME"] = str(DATA / "cache/hf-voice-proof")
    os.environ["NUMBA_CACHE_DIR"] = str(DATA / "cache/numba-voice-proof")
    sys.path.insert(0, str(VENDOR))
    os.chdir(MODELS / "RVC")
    started = time.perf_counter()
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available() or "RTX 4050" not in torch.cuda.get_device_name(0):
        raise RuntimeError("RTX 4050 CUDA inference is unavailable")
    from rvc.infer.infer import VoiceConverter
    converter = VoiceConverter()
    proof.update({"rvc_backend": "Applio 3.6.2 / pinned c7be7282af0f7b6382cbb2ac780b11242da12916",
                  "torch_version": torch.__version__, "cuda_runtime": torch.version.cuda,
                  "gpu_name": torch.cuda.get_device_name(0), "gpu_uuid": uuid,
                  "runtime_import_seconds": round(time.perf_counter() - started, 4),
                  "voice_version": "v2", "voice_sample_rate": 40000,
                  "settings": {"f0_method": "rmvpe", "index_rate": .5, "protect": .33, "volume_envelope": 1.0},
                  "converted": []})
    sampler = subprocess.Popen(["nvidia-smi", "--id=" + uuid, "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits", "--loop-ms=200"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    observations = []
    def collect():
        for line in sampler.stdout:
            try:
                memory, utilization = map(int, line.strip().split(","))
                observations.append({"at": round(time.perf_counter(), 3), "used_mib": memory, "gpu_percent": utilization})
            except ValueError:
                pass
    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    voice = MODELS / "RVC/Shiroko/SunaookamiShiroko.pth"
    index = MODELS / "RVC/Shiroko/added_IVF873_Flat_nprobe_1_SunaookamiShiroko_v2.index"
    try:
        for row in proof["base"]:
            for pitch in (0, 6, 12):
                output = OUT / f"{row['id']}_shiroko_p{pitch:02d}.wav"
                torch.cuda.reset_peak_memory_stats()
                started = time.perf_counter()
                converter.convert_audio(row["path"], str(output), str(voice), str(index), pitch=pitch,
                                        f0_method="rmvpe", index_rate=.5, protect=.33, volume_envelope=1.0,
                                        split_audio=False, f0_autotune=False, clean_audio=False,
                                        embedder_model="contentvec", export_format="WAV")
                torch.cuda.synchronize()
                elapsed = time.perf_counter() - started
                info = audio_info(output)  # Upstream logs and swallows some failures: require a valid output.
                if info["sample_rate"] != 40000 or abs(info["duration_seconds"] - row["duration_seconds"]) > .25:
                    raise RuntimeError("Unexpected converted duration or rate")
                converted = {"id": row["id"], "pitch_semitones": pitch, "text": row["text"], **info,
                             "conversion_seconds": round(elapsed, 4), "real_time_factor": round(elapsed / info["duration_seconds"], 4),
                             "torch_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1048576, 2),
                             "torch_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1048576, 2),
                             "first_conversion_in_process": not proof["converted"]}
                proof["converted"].append(converted)
                save(proof)
                print(json.dumps({"rvc": row["id"], "pitch": pitch, "seconds": round(elapsed, 3), "audio_seconds": info["duration_seconds"]}), flush=True)
    finally:
        sampler.terminate()
        sampler.wait(timeout=5)
        reader.join(timeout=2)
        proof["gpu_sampling"] = {"interval_ms": 200, "sample_count": len(observations),
                                 "whole_gpu_peak_used_mib": max((v["used_mib"] for v in observations), default=None),
                                 "peak_utilization_percent": max((v["gpu_percent"] for v in observations), default=None),
                                 "note": "nvidia-smi totals include other processes; not a per-model VRAM measurement"}
        (OUT / "gpu-samples.json").write_text(json.dumps(observations), encoding="utf-8")
        converter.cleanup_model()
        save(proof)
    warm = [row["real_time_factor"] for row in proof["converted"] if not row["first_conversion_in_process"]]
    proof["warm_conversion_median_rtf"] = round(statistics.median(warm), 4)
    proof["status"] = "file_conversion_completed_requires_human_listening"
    save(proof)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tts-only", action="store_true")
    parser.add_argument("--convert-only", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    if args.convert_only:
        proof = json.loads((OUT / "proof.json").read_text(encoding="utf-8"))
    else:
        proof = {"status": "preparing", "microphone_opened": False, "speaker_opened": False,
                 "cloud_audio_upload": False, "llm_started": False,
                 "note": "Prerecorded synthesis examples, not desktop command execution or live full duplex"}
        make_tts(proof)
    if not args.tts_only:
        convert(proof)
    print(json.dumps({"proof": str(OUT / "proof.json"), "status": proof["status"]}), flush=True)


if __name__ == "__main__":
    main()
