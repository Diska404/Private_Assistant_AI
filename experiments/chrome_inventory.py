"""Read only Chrome profile display metadata; never reads cookies/history/login databases."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re

from command_resolution import Profile, ProfileCatalog, WIB
from hybrid_engine import DEFAULT_DATA

CHANNELS = {"stable": "Chrome", "beta": "Chrome Beta", "dev": "Chrome Dev", "canary": "Chrome SxS"}


def inspect_profiles(local_app_data: Path) -> dict:
    profiles, errors = [], []
    for channel, folder in CHANNELS.items():
        root = local_app_data / "Google" / folder / "User Data"
        local_state = root / "Local State"
        if not local_state.is_file():
            continue
        try:
            if local_state.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("oversized_metadata")
            data = json.loads(local_state.read_text(encoding="utf-8-sig"))
            cache = data.get("profile", {}).get("info_cache", {})
            if not isinstance(cache, dict):
                raise ValueError("invalid_profile_cache")
            for directory, metadata in cache.items():
                # Profile dirs are direct children; reject absolute/relative path tricks.
                if not isinstance(directory, str) or not re.fullmatch(r"[A-Za-z0-9 _-]+", directory):
                    continue
                if not isinstance(metadata, dict):
                    continue
                name = metadata.get("name")
                if not isinstance(name, str) or not name.strip() or len(name) > 200 or any(ord(c) < 32 for c in name):
                    continue
                profiles.append({"id": f"chrome-{channel}:{directory}", "name": name.strip(),
                                 "channel": channel, "profile_directory": directory,
                                 "user_data_root": str(root), "directory_exists": (root / directory).is_dir()})
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append({"channel": channel, "reason": "metadata_unavailable_or_invalid"})
    return {"captured_at": datetime.now(WIB).isoformat(), "profiles": profiles, "errors": errors,
            "scope": "Local State profile.info_cache display names/directories only; no history, tabs, cookies or account identifiers exported"}


def catalog_from_inventory(path: Path) -> ProfileCatalog:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Oversized profile inventory")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("Invalid profile inventory")
    valid = []
    for profile in profiles:
        if not isinstance(profile, dict) or not isinstance(profile.get("directory_exists"), bool):
            raise ValueError("Invalid profile inventory entry")
        if profile["directory_exists"]:
            if not isinstance(profile.get("id"), str) or not isinstance(profile.get("name"), str):
                raise ValueError("Invalid profile identity")
            valid.append(Profile(profile["id"], profile["name"]))
    return ProfileCatalog(valid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA / "chrome-profile-inventory.json")
    args = parser.parse_args()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        parser.error("LOCALAPPDATA unavailable")
    report = inspect_profiles(Path(local_app_data))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"profiles_found": len(report["profiles"]),
                      "existing_directories": sum(p["directory_exists"] for p in report["profiles"]),
                      "channels": sorted({p["channel"] for p in report["profiles"]}),
                      "errors": report["errors"], "inventory": str(args.output), "cloud_requests": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
