"""Public metadata only: no checkpoint/audio downloads and no credentials."""
import json
from pathlib import Path
import subprocess
from urllib.parse import quote

OUT = Path(r"D:\AI\AI Lokal Asisten\Leva\research\leva-gfl2")


def fetch(url):
    call = subprocess.run(["curl.exe", "-4", "-fLsS", "--max-time", "25", "--max-filesize", "3000000", url],
                          capture_output=True, encoding="utf-8", creationflags=0x08000000)
    if call.returncode:
        return {"error": "public_metadata_unavailable"}
    try:
        return json.loads(call.stdout)
    except ValueError:
        return {"error": "not_json"}


results = {"queries": {}, "candidates": {}}
for query in ("Leva", "GFL2", "UMP45", "莱娅", "GirlsFrontline"):
    rows = fetch("https://huggingface.co/api/models?search=" + quote(query) + "&limit=200&full=true")
    results["queries"][query] = rows
for ident in ("MrM0dZ/UMP45_Mineuchi_Tomomi", "Trolge/ump45model", "Ai-Tunes/modelos_publicos", "mohammedaly22/leva-tts"):
    results["candidates"][ident] = fetch("https://huggingface.co/api/models/" + ident)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "hf-metadata-expanded.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
for query, rows in results["queries"].items():
    print(json.dumps({"query": query, "count": len(rows) if isinstance(rows, list) else None,
                      "ids": [r["id"] for r in rows] if isinstance(rows, list) else []}, ensure_ascii=True))
for ident, row in results["candidates"].items():
    print(json.dumps({"candidate": ident, "card": row.get("cardData"),
                      "files": [f["rfilename"] for f in row.get("siblings", []) if ident != "Ai-Tunes/modelos_publicos" or "ump45" in f["rfilename"].lower()]}, ensure_ascii=True))
