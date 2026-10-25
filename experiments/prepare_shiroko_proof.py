"""Download pinned public inference assets; preserve the user's original voice ZIP."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = Path(r"D:\AI\AI Lokal Asisten\AI Models")
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
VENDOR = ROOT / "experiments/vendor/Applio-c7be7282af0f7b6382cbb2ac780b11242da12916"
PIPER_REV = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
RVC_REV = "e908bdd5bf9f18cede26bbbec724b1a4bc7c2f14"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    tmp = DATA / "tmp/voice-proof"
    tmp.mkdir(parents=True, exist_ok=True)
    manifest = {"source_commit": VENDOR.name.removeprefix("Applio-"), "downloads": [], "local_voice": []}
    files = [
        ("rhasspy/piper-voices", PIPER_REV, "id/id_ID/news_tts/medium/" + name, MODELS / "Piper-ID" / name)
        for name in ["id_ID-news_tts-medium.onnx", "id_ID-news_tts-medium.onnx.json", "MODEL_CARD"]
    ] + [
        ("IAHispano/Applio", RVC_REV, "Resources/embedders/contentvec/" + name,
         MODELS / "RVC/rvc/models/embedders/contentvec" / name)
        for name in ["config.json", "pytorch_model.bin"]
    ] + [("IAHispano/Applio", RVC_REV, "Resources/predictors/rmvpe.pt", MODELS / "RVC/rvc/models/predictors/rmvpe.pt")]
    for repo, rev, remote, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{repo}/resolve/{rev}/{remote}"
        headers = tmp / (target.name + ".headers")
        print(json.dumps({"downloading": target.name}), flush=True)
        if not target.exists():
            partial = target.with_suffix(target.suffix + ".partial")
            subprocess.run(["curl.exe", "-4", "-sS", "-L", "--fail", "--connect-timeout", "12", "--max-time", "240",
                            "--retry", "1", "-D", str(headers), url, "-o", str(partial)], check=True)
            checksum = digest(partial)
            expected = []
            for line in headers.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("x-linked-etag:"):
                    value = line.split(":", 1)[1].strip().strip('"')
                    if len(value) == 64:
                        expected.append(value)
            if expected and checksum not in expected:
                raise RuntimeError("Downloaded asset checksum does not match HF LFS ETag")
            partial.replace(target)
        manifest["downloads"].append({"url": url, "path": str(target), "bytes": target.stat().st_size, "sha256": digest(target)})
        print(json.dumps({"ready": target.name, "bytes": target.stat().st_size}), flush=True)
    voice = MODELS / "RVC/Shiroko"
    voice.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ROOT / "SunaookamiShiroko.zip") as archive:
        for name in ["SunaookamiShiroko.pth", "added_IVF873_Flat_nprobe_1_SunaookamiShiroko_v2.index"]:
            target = voice / name
            target.write_bytes(archive.read(name))
            manifest["local_voice"].append({"path": str(target), "bytes": target.stat().st_size, "sha256": digest(target)})
    configs = MODELS / "RVC/rvc/configs"
    configs.mkdir(parents=True, exist_ok=True)
    for path in (VENDOR / "rvc/configs").glob("*.json"):
        shutil.copy2(path, configs / path.name)
    manifest["original_zip_sha256"] = digest(ROOT / "SunaookamiShiroko.zip")
    (MODELS / "voice-proof-download-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Pinned assets and voice copies prepared.", flush=True)


if __name__ == "__main__":
    main()
