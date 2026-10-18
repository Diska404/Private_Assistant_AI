"""Local preferences and aggregate command habits; no chat, audio or credentials."""
import json
from pathlib import Path
import re
import sqlite3
import threading

from paths import DATA

MODES = ("Hybrid · Google → Lokal", "Lokal · RTX 4050", "Perintah saja · Tanpa AI")
VOICES = ("Kore", "Aoede", "Leda", "Puck")
DEFAULTS = {"provider": MODES[0], "dual_gpu": False, "learn_habits": True,
            "animation": "normal", "voice": "Kore", "input_device_name": "", "output_device_name": ""}


def validate_setting(key, value):
    if key not in DEFAULTS:
        raise ValueError("unknown_setting")
    if key in {"dual_gpu", "learn_habits"}:
        valid = type(value) is bool
    elif key == "provider":
        valid = value in MODES
    elif key == "voice":
        valid = value in VOICES
    elif key == "animation":
        valid = isinstance(value,str) and value in {"normal", "hemat"}
    else:
        valid = isinstance(value, str) and len(value) <= 200 and not any(c in value for c in "\r\n\x00")
    if not valid:
        raise ValueError("invalid_setting")


class Preferences:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DATA / "preferences.sqlite3"
        self.lock = threading.RLock()
        self.persistent = True
        self.warning = ""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=3)
            self.db.execute("PRAGMA journal_mode=WAL")
            self._schema()
        except (OSError, sqlite3.Error):
            if hasattr(self, "db"):
                self.db.close()
            self.persistent = False
            self.warning = "Penyimpanan pengaturan belum tersedia. Perubahan hanya berlaku selama sesi ini."
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
            self._schema()

    def _schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, profile_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS habits (
                action TEXT NOT NULL, profile_id TEXT NOT NULL, uses INTEGER NOT NULL,
                last_used TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(action,profile_id));
        """)

    def get(self, key):
        if key not in DEFAULTS:
            raise ValueError("unknown_setting")
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        try:
            value = json.loads(row[0]) if row else DEFAULTS[key]
            validate_setting(key, value)
            return value
        except (ValueError, TypeError):
            return DEFAULTS[key]

    def set(self, key, value):
        self.set_many({key:value})

    def set_many(self, values):
        for key,value in values.items():
            validate_setting(key, value)
        with self.lock, self.db:
            self.db.executemany("INSERT OR REPLACE INTO settings VALUES (?,?)", [(key,json.dumps(value)) for key,value in values.items()])

    def aliases(self):
        with self.lock:
            return dict(self.db.execute("SELECT alias,profile_id FROM aliases ORDER BY alias"))

    def set_alias(self, alias, profile_id):
        alias = " ".join(alias.casefold().split())
        if not re.fullmatch(r"[\w -]{2,48}", alias) or not isinstance(profile_id, str) or not profile_id:
            raise ValueError("invalid_alias")
        if set(alias.split()) & {"buka", "chrome", "youtube", "ya", "iya", "tidak", "jangan", "batal", "profil", "leva"}:
            raise ValueError("reserved_alias")
        with self.lock, self.db:
            existing = self.db.execute("SELECT profile_id FROM aliases WHERE alias=?", (alias,)).fetchone()
            if existing and existing[0] != profile_id:
                raise ValueError("alias_already_assigned")
            self.db.execute("INSERT OR REPLACE INTO aliases VALUES (?,?)", (alias, profile_id))

    def remove_alias(self, alias):
        with self.lock, self.db:
            self.db.execute("DELETE FROM aliases WHERE alias=?", (alias,))

    def record(self, action, profile_id):
        if action not in {"chrome", "youtube"} or not self.get("learn_habits"):
            return
        with self.lock, self.db:
            self.db.execute("""INSERT INTO habits(action,profile_id,uses) VALUES (?,?,1)
                ON CONFLICT(action,profile_id) DO UPDATE SET uses=MIN(uses+1,1000000),last_used=CURRENT_TIMESTAMP""",
                (action, profile_id))

    def habits(self):
        with self.lock:
            rows = self.db.execute("SELECT action,profile_id,uses,last_used FROM habits ORDER BY action,uses DESC,profile_id").fetchall()
        return [dict(zip(("action", "profile_id", "uses", "last_used"), row)) for row in rows]

    def suggestions(self, known_profiles):
        if not self.get("learn_habits"):
            return {}
        choices = {}
        for action in ("chrome", "youtube"):
            rows = [r for r in self.habits() if r["action"] == action and r["profile_id"] in known_profiles]
            if rows and rows[0]["uses"] >= 3 and (len(rows) == 1 or rows[0]["uses"] > rows[1]["uses"]):
                choices[action] = rows[0]["profile_id"]
        return choices

    def clear_habits(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM habits")

    def close(self):
        with self.lock:
            self.db.close()
