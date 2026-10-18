import json
from pathlib import Path
import tempfile
import unittest

from chrome_inventory import catalog_from_inventory, inspect_profiles


class ChromeInventoryTests(unittest.TestCase):
    def test_only_display_metadata_exported_and_bad_paths_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Google" / "Chrome" / "User Data"
            (root / "Default").mkdir(parents=True)
            (root / "Local State").write_text(json.dumps({"os_crypt": {"encrypted_key": "PRIVATE_SENTINEL"},
                "profile": {"info_cache": {
                    "Default": {"name": "Kuliah", "user_name": "PRIVATE_SENTINEL", "gaia_id": "PRIVATE_SENTINEL"},
                    "Profile 2": {"name": "Hiburan"},
                    "../outside": {"name": "Bad"},
                }}}), encoding="utf-8")
            report = inspect_profiles(base)
            self.assertEqual(len(report["profiles"]), 2)
            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(report))
            self.assertEqual(report["profiles"][0]["id"], "chrome-stable:Default")
            path = base / "inventory.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(list(catalog_from_inventory(path).profiles), ["chrome-stable:Default"])

    def test_corrupt_metadata_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Google" / "Chrome Beta" / "User Data"
            root.mkdir(parents=True)
            (root / "Local State").write_text("PRIVATE_SENTINEL not json", encoding="utf-8")
            report = inspect_profiles(base)
            self.assertEqual(report["profiles"], [])
            self.assertEqual(report["errors"][0]["reason"], "metadata_unavailable_or_invalid")
            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
