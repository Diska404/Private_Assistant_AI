"""Stable project and data locations, including packages deployed on another drive."""
import json
from pathlib import Path
import sys


def project_root():
    if getattr(sys, "frozen", False):
        binary = Path(sys.executable).resolve()
        pointer = binary.parent / "project-root.txt"
        if pointer.is_file():
            candidate = Path(pointer.read_text(encoding="utf-8-sig").strip())
            marker = candidate / "LEVA_PROJECT.json"
            try:
                valid = candidate.is_absolute() and marker.is_file() and json.loads(marker.read_text(encoding="utf-8-sig")).get("name") == "Leva"
            except (OSError, ValueError):
                valid = False
            if not valid:
                raise RuntimeError("Lokasi proyek Leva pada project-root.txt tidak valid.")
            return candidate.resolve()
        for parent in list(binary.parents)[:4]:
            if (parent / "LEVA_PROJECT.json").is_file():
                return parent
        raise RuntimeError("Leva harus dijalankan dari folder proyek yang lengkap.")
    return Path(__file__).resolve().parents[1]


ROOT = project_root()
DATA = Path(r"D:\AI\AI Lokal Asisten\Leva")
