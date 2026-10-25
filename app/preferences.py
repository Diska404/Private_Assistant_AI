"""Local preferences and aggregate command habits; no chat, audio or credentials."""
import json
from pathlib import Path
import re
import sqlite3
import threading

from paths import DATA,ROOT

from pipeline_routing import SINGLE_CHOICES,DUAL_CHOICES,LEGACY
MODES = SINGLE_CHOICES
VOICES = ("Kore", "Aoede", "Leda", "Puck")
DEFAULTS = {"provider": MODES[0], "dual_gpu": False, "learn_habits": True,
            "animation": "normal", "voice": "Kore", "input_device_name": "", "output_device_name": "",
            "target_voice_pack": "leva_gfl2", "spoken_replies": True, "saluki_acceleration": "auto", 'keep_models_warm':True,'speech_language':'id',
            'auto_memory':True,'always_listen':True,'autostart':True,'briefing':True,'proactive':True,'weather_city':'Cikarang','theme':'cyan','briefing_last_date':'',
            'use_device_location':True,'input_hostapi':'','output_hostapi':'',
            'router_url':'http://127.0.0.1:20128/v1','router_model':'','router_local_model':'saluki','speech_style':'auto','workspace_root':str(ROOT),
            'comfy_root':'','comfy_url':'http://127.0.0.1:8188','fooocus_root':'','fooocus_url':'http://127.0.0.1:7866','image_model_roots':'[]',
            'asr_model':'qwen_asr_06b','asr_gpu':'rtx5070','tts_gpu':'auto','asr_language':'id',
            'companion_idle':True,'companion_playful':True,'companion_idle_delay':'120','show_japanese':False,
            'companion_enabled':False,'companion_label':'Leva ♡','companion_avatar_model':'qwen4b','companion_avatar_gpu':'gpu5070','experimental_models_enabled':False,
            'streaming_text':True,'realtime_speech':False,'native_voice_stream':False,
            'companion_avatar_asset':'placeholder','companion_renderer_gpu':'rtx4050','companion_renderer_backend':'vrm',
            'chat_model':'auto','chat_gpu':'gpu5070','secret_model':'qwen4b','secret_gpu':'gpu5070',
            'agent_local_model':'saluki','agent_provider':'RTX 5070','agent_gpu':'auto','separate_agent':True,'route_single_gpu':'rtx4050','obsidian_vault':'','web_port':'8769','web_remote_origin':'','web_remote_enabled':False}


def validate_setting(key, value):
    if key not in DEFAULTS:
        raise ValueError("unknown_setting")
    if key in {"dual_gpu", "learn_habits", "spoken_replies", 'keep_models_warm','auto_memory','always_listen','autostart','briefing','proactive','use_device_location','separate_agent','web_remote_enabled','companion_idle','companion_playful','show_japanese','companion_enabled','experimental_models_enabled','streaming_text','realtime_speech','native_voice_stream'}:
        valid = type(value) is bool
    elif key in ("provider",'agent_provider'):
        valid = value in SINGLE_CHOICES+DUAL_CHOICES or value in LEGACY
    elif key=='companion_avatar_asset':valid=value in ('placeholder','pixiv_sample','pixiv_polished','custom','leva_original')
    elif key=='companion_renderer_gpu':valid=value in ('rtx4050','rtx5070')
    elif key=='companion_renderer_backend':valid=value in ('vrm','vts','live2d')
    elif key == "voice":
        valid = value in VOICES
    elif key == "target_voice_pack":
        from voice_packs import PACK_IDS
        valid = value in PACK_IDS
    elif key == "animation":
        valid = isinstance(value,str) and value in {"normal", "hemat"}
    elif key=='saluki_acceleration':
        valid=isinstance(value,str) and value in ('auto','plain','mtp','dflash')
    elif key=='speech_language':valid=value in ('id','ja')
    elif key=='companion_idle_delay':valid=value in ('120','300','600')
    elif key=='speech_style':valid=value in ('auto','assistant','personal')
    elif key=='theme':valid=value in ('cyan','gold','violet')
    elif key=='router_url':
        from provider_urls import base_url
        try:base_url(value);valid=True
        except (ValueError,TypeError,AttributeError):valid=False
    elif key=='router_local_model':valid=value in ('saluki','qwen4b')
    elif key=='agent_local_model':valid=isinstance(value,str) and (value in ('saluki','qwen4b','qwen35b','minicpm2b','translator2b') or value in __import__('personal_models').PROFILES)
    elif key in ('chat_model','secret_model','companion_avatar_model'):valid=isinstance(value,str) and (value in ('qwen4b','saluki','qwen35b','minicpm2b','translator2b') or value in __import__('personal_models').PROFILES or value in __import__('model_registry').TRIALS or key=='chat_model' and value=='auto')
    elif key in ('chat_gpu','secret_gpu','companion_avatar_gpu'):valid=value in ('gpu4050','gpu5070','dual')
    elif key=='companion_label':valid=isinstance(value,str) and 1<=len(value.strip())<=40 and not any(ord(c)<32 for c in value)
    elif key=='agent_gpu':valid=value in ('auto','rtx4050','rtx5070','dual')
    elif key=='asr_model':valid=value in ('qwen_asr_06b','qwen_asr_17b','whisper_cpu')
    elif key=='asr_gpu':valid=value in ('auto','rtx4050','rtx5070','dual')
    elif key=='tts_gpu':valid=value in ('auto','rtx4050','rtx5070')
    elif key=='route_single_gpu':valid=value in ('rtx4050','rtx5070')
    elif key=='asr_language':valid=value in ('id','ja','auto')
    elif key=='image_model_roots':
        try:
            from pathlib import Path
            rows=json.loads(value)
            valid=isinstance(value,str) and len(value)<=3000 and isinstance(rows,list) and len(rows)<=12 and all(isinstance(row,str) and Path(row).is_absolute() and Path(row).is_dir() for row in rows)
        except (ValueError,TypeError,OSError):valid=False
    elif key in ('comfy_url','fooocus_url'):
        from comfy_service import ComfyClient
        try:ComfyClient(value);valid=True
        except (ValueError,TypeError,AttributeError):valid=False
    elif key in ('comfy_root','fooocus_root'):
        valid=isinstance(value,str) and len(value)<=1000 and not any(c in value for c in '\r\n\x00')
        if valid and value:
            from pathlib import Path
            folder=Path(value)
            valid=folder.is_absolute() and (((folder/'Fooocus/webui.py').is_file()) if key=='fooocus_root' else ((folder/'ComfyUI/main.py').is_file() or (folder/'main.py').is_file()))
    elif key=='web_port':valid=isinstance(value,str) and value.isdigit() and (value=='0' or 1024<=int(value)<=65535)
    elif key=='web_remote_origin':
        from web_bridge import remote_origin
        try:remote_origin(value);valid=isinstance(value,str)
        except ValueError:valid=False
    elif key=='obsidian_vault':
        try:
            from second_brain import vault_root
            valid=isinstance(value,str) and (value=='' or bool(vault_root(value)))
        except (ValueError,OSError,TypeError):valid=False
    elif key=='workspace_root':
        try:
            from file_workspace import checked_path
            valid=checked_path(value).is_dir()
        except (ValueError,OSError,TypeError):valid=False
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
            if key=='provider':value=LEGACY.get(value,value)
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
