"""Download only the two user-authorized GGUFs into the designated D: model root."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

MODEL_ROOT = Path(r"D:\AI\AI Lokal Asisten\AI Models")
TARGETS = [
    ("openbmb/MiniCPM5-2B-GGUF", "MiniCPM5-2B-Q8_0.gguf", "MiniCPM5-2B"),
    ("ggml-org/gemma-4-E2B-it-GGUF", "gemma-4-E2B-it-Q8_0.gguf", "Gemma-4-E2B-IT"),
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(target):
    repo, filename, directory = target
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl unavailable")
    result = subprocess.run([curl, "-4", "--fail", "--silent", "--show-error", "--location",
        "--connect-timeout", "15", "--max-time", "60",
        f"https://huggingface.co/api/models/{repo}?blobs=true"],
        capture_output=True, encoding="utf-8", timeout=65,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(f"Model metadata unavailable: {repo}; curl={result.returncode}")
    metadata = json.loads(result.stdout)
    revision = metadata["sha"]
    file_meta = next(item for item in metadata["siblings"] if item["rfilename"] == filename)
    lfs = file_meta.get("lfs", {})
    expected_hash, expected_size = lfs.get("sha256"), lfs.get("size") or file_meta.get("size")
    if not expected_hash or not expected_size:
        raise RuntimeError("Expected authoritative LFS size and SHA256")
    folder = MODEL_ROOT / directory
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / filename
    source = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}?download=true"
    if destination.exists():
        if destination.stat().st_size != expected_size or sha256(destination) != expected_hash:
            raise RuntimeError(f"Existing file differs; refusing overwrite: {destination.name}")
    else:
        if shutil.disk_usage(MODEL_ROOT).free < expected_size + 2 * 1024**3:
            raise RuntimeError("Insufficient storage headroom")
        partial = destination.with_suffix(".gguf.part")
        print(json.dumps({"event": "download_start", "model": directory,
                          "bytes": expected_size, "destination": str(destination)}), flush=True)
        with (folder / "download.log").open("w", encoding="utf-8") as log:
            process = subprocess.run([curl, "-4", "--fail", "--location", "--silent", "--show-error",
                "--connect-timeout", "15", "--max-time", "1800", "--retry", "3", "--retry-delay", "2",
                "--speed-limit", "1024", "--speed-time", "60", "--continue-at", "-",
                "--output", str(partial), source], stdout=log, stderr=log, timeout=1900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode:
            raise RuntimeError(f"Download incomplete: {directory}; curl={process.returncode}")
        if partial.stat().st_size != expected_size or sha256(partial) != expected_hash:
            raise RuntimeError(f"Size/hash verification failed: {directory}")
        with partial.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise RuntimeError("Downloaded file is not GGUF")
        partial.rename(destination)
    manifest = {"repo": repo, "revision": revision, "filename": filename, "path": str(destination),
                "size": expected_size, "sha256": expected_hash, "verified": True,
                "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "Text inference comparison; no projector or training checkpoint downloaded."}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"event": "verified", "model": directory, "bytes": expected_size}), flush=True)
    return manifest


if __name__ == "__main__":
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        manifests = list(pool.map(download, TARGETS))
    (MODEL_ROOT / "download-manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    print(json.dumps({"event": "all_complete", "models": len(manifests)}), flush=True)
