"""Pin official OpenVoice source/weights for an isolated local candidate experiment."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models\OpenVoiceV2")
OUT = DATA / "verification/leva-openvoice-candidate"
DOWNLOADS = DATA / "downloads/leva-openvoice"
for folder in (MODELS, OUT, DOWNLOADS): folder.mkdir(parents=True, exist_ok=True)


def get(url, destination, maximum=200_000_000):
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl.exe", "-4", "-fLsS", "--retry", "2", "--max-time", "180", "--max-filesize", str(maximum),
                    "-o", str(destination), url], check=True, creationflags=0x08000000)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


source_meta = DOWNLOADS / "source-commit.json"
get("https://api.github.com/repos/myshell-ai/OpenVoice/commits/main", source_meta, 1_000_000)
commit = json.loads(source_meta.read_text(encoding="utf-8"))["sha"]
source_zip = DOWNLOADS / ("OpenVoice-" + commit + ".zip")
source_hash = (hashlib.sha256(source_zip.read_bytes()).hexdigest() if source_zip.exists() else
               get("https://codeload.github.com/myshell-ai/OpenVoice/zip/" + commit, source_zip, 30_000_000))
vendor = ROOT / "experiments/vendor" / ("OpenVoice-" + commit)
if not vendor.exists():
    with zipfile.ZipFile(source_zip) as archive:
        for member in archive.infolist():
            if not (vendor.parent / member.filename).resolve().is_relative_to(vendor.resolve()):
                raise ValueError("unsafe_source_archive")
        archive.extractall(vendor.parent)

meta_path = DOWNLOADS / "model-metadata.json"
get("https://huggingface.co/api/models/myshell-ai/OpenVoiceV2?blobs=true", meta_path, 2_000_000)
metadata = json.loads(meta_path.read_text(encoding="utf-8"))
revision = metadata["sha"]
files = []
for relative in ("converter/config.json", "converter/checkpoint.pth"):
    record = next(row for row in metadata["siblings"] if row["rfilename"] == relative)
    target = MODELS / relative
    url = "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/" + revision + "/" + relative
    expected = record.get("lfs", {}).get("sha256")
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    if not actual or expected and actual != expected:
        actual = get(url, target)
    if expected and actual != expected:
        raise ValueError("model_hash_mismatch")
    files.append({"path": str(target), "url": url, "sha256": actual, "bytes": target.stat().st_size,
                  "lfs_hash_verified": bool(expected)})
manifest = {"source": "https://github.com/myshell-ai/OpenVoice", "commit": commit,
            "source_sha256": source_hash, "vendor": str(vendor), "model_revision": revision, "files": files,
            "identity": "general OpenVoice V2 converter, not a dedicated Leva checkpoint",
            "reference": "user-provided showcase video; provenance retained, redistribution rights not established"}
water_meta = DOWNLOADS / "watermark-metadata.json"
get("https://huggingface.co/api/models/M4869/WavMark?blobs=true", water_meta, 1_000_000)
wm = json.loads(water_meta.read_text(encoding="utf-8"))
wm_name = "step59000_snr39.99_pesq4.35_BERP_none0.30_mean1.81_std1.81.model.pkl"
wm_row = next(row for row in wm["siblings"] if row["rfilename"] == wm_name)
wm_target = MODELS / "watermark" / wm_name
wm_expected = wm_row.get("lfs", {}).get("sha256")
wm_actual = hashlib.sha256(wm_target.read_bytes()).hexdigest() if wm_target.exists() else None
wm_url = "https://huggingface.co/M4869/WavMark/resolve/" + wm["sha"] + "/" + wm_name
if not wm_actual or wm_expected and wm_actual != wm_expected:
    wm_actual = get(wm_url, wm_target)
if wm_expected and wm_expected != wm_actual: raise ValueError("watermark_hash_mismatch")
manifest["watermark"] = {"path": str(wm_target), "url": wm_url, "sha256": wm_actual,
                         "bytes": wm_target.stat().st_size, "revision": wm["sha"]}
(MODELS / "leva-candidate-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest), flush=True)
