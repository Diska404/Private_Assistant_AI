from pathlib import Path
import os
import sys


def project_root():
    if getattr(sys, "frozen", False):
        binary = Path(sys.executable).resolve()
        for parent in list(binary.parents)[:4]:
            if (parent / "LEVA_PROJECT.json").is_file():
                return parent
        raise RuntimeError("Leva harus dijalankan dari folder proyek yang lengkap.")
    return Path(__file__).resolve().parents[1]


ROOT = project_root()
DATA = Path(os.environ.get("LEVA_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Leva"))
