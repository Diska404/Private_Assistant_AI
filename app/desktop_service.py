"""Desktop command dispatcher. Models never choose executable paths or shell commands."""
from dataclasses import asdict
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import uuid

from action_contract import SimulationSession
from chrome_inventory import inspect_profiles
from command_resolution import Profile, ProfileCatalog, WIB, normalized, resolve_wake
from conversation_controller import ConversationController
from windows_runtime import chrome_windows, idle_milliseconds


def chrome_executable(channel):
    folder = {"stable": "Chrome", "beta": "Chrome Beta", "dev": "Chrome Dev", "canary": "Chrome SxS"}[channel]
    for base in [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]:
        if base:
            path = Path(base) / "Google" / folder / "Application" / "chrome.exe"
            if path.is_file():
                return path
    raise OSError("Chrome executable unavailable")


class BrowserLauncher:
    def launch(self, profile, youtube=False):
        executable = chrome_executable(profile["channel"])
        root = Path(profile["user_data_root"])
        directory = profile["profile_directory"]
        if not re.fullmatch(r"[A-Za-z0-9 _-]+", directory) or not (root / directory).is_dir():
            raise OSError("Profile directory unavailable")
        before = chrome_windows()
        command = [str(executable), "--user-data-dir=" + str(root), "--profile-directory=" + directory,
                   "--new-window", "https://www.youtube.com/" if youtube else "chrome://newtab/"]
        # Chrome is a user application, deliberately outside the inference job's lifecycle.
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        observed = []
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            windows = chrome_windows()
            observed = [hwnd for hwnd in windows if hwnd not in before]
            if observed:
                break
            if process.poll() not in {None, 0}:
                raise OSError("Chrome rejected launch")
            time.sleep(0.2)
        return {"dispatched": True, "profile_id": profile["id"], "profile_name": profile["name"],
                "new_window_observed": bool(observed), "window_handles": observed,
                "profile_verified_in_window": False,
                "url_requested": "https://www.youtube.com/" if youtube else "chrome://newtab/"}


class DesktopExecutor(SimulationSession):
    simulated = False

    def __init__(self, state, browser, profiles):
        super().__init__(state)
        self.browser, self.profiles = browser, profiles
        self.plan = None
        self.evidence = {}

    def perform(self, action, args, fail=False):
        if fail:
            return False
        if action in {"open_profile", "open_youtube"}:
            profile = self.profiles.get(self.plan.profile_id) if self.plan else None
            if not profile or profile["name"] != args.get("profile"):
                return False
            try:
                self.evidence[self.plan.request_id] = self.browser.launch(profile, action == "open_youtube")
            except OSError:
                self.evidence[self.plan.request_id] = {"dispatched": False}
                return False
        # Browser session recovery/research are not implemented as desktop tools in v0.1.
        if action in {"restore_session", "recommend_source"}:
            return False
        return True


class DesktopService:
    def __init__(self, browser=None, preferences=None):
        self.browser = browser or BrowserLauncher()
        self.preferences = preferences
        self.memory_notice = ""
        self.paused = False
        self.refresh_profiles()

    def refresh_profiles(self):
        report = inspect_profiles(Path(os.environ["LOCALAPPDATA"]))
        self.profiles = {p["id"]: p for p in report["profiles"] if p["directory_exists"]}
        catalog = self.profile_catalog()
        self.controller = ConversationController(catalog)
        self.controller.executor = DesktopExecutor(self.controller.executor.state, self.browser, self.profiles)
        return list(self.profiles.values())

    def profile_catalog(self):
        aliases = self.preferences.aliases() if self.preferences else {}
        return ProfileCatalog([Profile(p["id"], p["name"], tuple(a for a, pid in aliases.items() if pid == p["id"]))
                               for p in self.profiles.values()])

    def sync_preferences(self):
        self.controller.catalog = self.profile_catalog()
        self.controller.habits = self.preferences.suggestions(self.profiles) if self.preferences else {}

    def add_alias(self, alias, profile_id):
        if not self.preferences or profile_id not in self.profiles:
            raise ValueError("unknown_profile")
        existing = self.profile_catalog().matches(alias)
        if any(p.id != profile_id for p in existing):
            raise ValueError("alias_conflicts_with_profile")
        self.preferences.set_alias(alias, profile_id)
        self.sync_preferences()

    def commit(self, plan):
        result = self.controller.commit(plan)
        executor = self.controller.executor
        for records in (self.controller.results,executor.receipts,executor.evidence):
            while len(records)>128:
                records.pop(next(iter(records)))
        return result

    def pause(self):
        self.paused = True
        self.controller.sleep.cancel()
        self.controller.pending = None

    def resume(self):
        self.paused = False
        self.controller.sleep.cancel()
        self.controller.pending = None

    def tick(self, now=None):
        now = now or datetime.now(WIB)
        machine = self.controller.sleep
        old_mode = machine.mode
        machine.advance(now)
        if machine.mode == "observing":
            idle = idle_milliseconds()
            start = machine.next_transition - timedelta(minutes=30)
            # A recent event counts only if it occurred inside the current observation window.
            if idle is not None and now - timedelta(milliseconds=idle) >= start:
                machine.cancel()
        return old_mode != machine.mode

    @property
    def sleeping(self):
        return self.controller.sleep.mode == "paused"

    def handle(self, text, now=None):
        now = now or datetime.now(WIB)
        value = normalized(text).strip(" .!?,")
        value = re.sub(r"^leva\s*[, ]*", "", value)
        if value in {"aktifkan", "aktifkan sistemmu", "lanjutkan", "lanjutkan sistem", "bangun", "resume"}:
            self.resume()
            return {"kind": "command", "reply": "Aku aktif kembali. Jadwal jeda sebelumnya sudah dibatalkan."}
        if re.match(r"^(?:tolong )?(?:jeda|jedakan|pause|bekukan)(?:\s|$)", value):
            self.pause()
            if re.search(r"\b(hingga|sampai|jam|pukul)\b", value):
                wake = resolve_wake(value, now)
                if not wake.wake:
                    return {"kind": "command", "cancel_ai": True,
                            "reply": "Aku dijeda. " + wake.question + " Gunakan ‘aktifkan’ untuk melanjutkan."}
                self.paused = False
                self.controller.sleep.arm(wake.wake)
                return {"kind": "command", "cancel_ai": True,
                        "reply": "Aku dijeda sampai " + wake.wake.strftime("%H.%M WIB pada %d-%m-%Y")
                        + ". Saat aktif, observasi 30 menit dimulai; aktivitas membatalkan siklus tidur."}
            return {"kind": "command", "cancel_ai": True,
                    "reply": "Aku dijeda. Proses AI dilepas; Chrome tetap terbuka. Tekan Aktifkan atau ketik ‘aktifkan’ untuk melanjutkan."}
        # Allow cancellation of the assistant's timer even while waiting for the scheduled wake.
        cancel_sleep = bool(re.search(r"\b(batalkan|hapus|hentikan)\b.*\b(tidur|jadwal|mekanisme)\b", value))
        if (self.paused or self.sleeping) and not cancel_sleep and value not in {"batal", "batalkan"}:
            return {"kind": "command", "reply": "Aku sedang jeda. Tekan Aktifkan atau ketik ‘aktifkan’ untuk melanjutkan."}
        self.sync_preferences()
        plan = self.controller.prepare(text, uuid.uuid4().hex, now)
        if plan.action == "unsupported":
            self.commit(plan)
            # Unsupported operations stay local; they do not become cloud action instructions.
            command_words = r"\b(buka|bukain|bukakan|pulihkan|balikin|hapus|kirim|unduh|jalankan|skip|iklan|cari|carikan)\b"
            if re.search(command_words, value):
                return {"kind": "command", "reply": "Fungsi itu belum tersedia. Saat ini aku bisa membuka profil Chrome/YouTube, mengatur jeda, dan mengobrol lewat AI."}
            return {"kind": "chat"}
        executor = self.controller.executor
        executor.plan = plan
        result = self.commit(plan)
        receipt = result["receipt"]
        if not receipt or not receipt["success"]:
            return {"kind": "command", "reply": "Tindakan belum berhasil. Periksa apakah Chrome dan direktori profil masih tersedia.", "success": False}
        if plan.action in {"open_profile", "open_youtube"}:
            evidence = executor.evidence[plan.request_id]
            name = self.controller.catalog.label(self.controller.catalog.profiles[plan.profile_id])
            reply = ("Permintaan membuka " + ("YouTube di profil " if plan.action == "open_youtube" else "profil ")
                     + name + " sudah dikirim ke Chrome. ")
            reply += "Jendela Chrome baru terdeteksi." if evidence["new_window_observed"] else "Jendela baru belum terdeteksi; periksa Chrome."
            if self.preferences and evidence.get("dispatched") and evidence["new_window_observed"]:
                try:
                    self.preferences.record("youtube" if plan.action == "open_youtube" else "chrome", plan.profile_id)
                except (OSError, sqlite3.Error):
                    self.memory_notice = "Tindakan selesai, tetapi catatan kebiasaan belum tersimpan."
            return {"kind": "command", "reply": reply, "evidence": evidence,
                    "detail": "Target profil dikirim lewat parameter Chrome; identitas profil dan isi halaman belum diverifikasi dari jendela."}
        if plan.action == "schedule_sleep":
            return {"kind": "command", "cancel_ai": True,
                    "reply": "Baik, aku jeda sampai " + plan.wake.strftime("%H.%M WIB pada %d-%m-%Y")
                    + ". Setelah itu aku mengamati aktivitas 30 menit. Tanpa aktivitas aku jeda 1 jam, lalu mengulangi observasi. Ini hanya menjeda Leva."}
        if plan.action == "cancel_sleep":
            self.paused = False
            return {"kind": "command", "reply": "Jadwal istirahat sudah dibatalkan. Aku aktif kembali."}
        if plan.action == "ask_session":
            return {"kind": "command", "reply": "Pemulihan kelompok tab belum tersedia pada versi ini. Aku belum membaca riwayat atau memulihkan tab."}
        return {"kind": "command", "reply": result["reply"]}
