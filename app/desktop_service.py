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
    def launch(self, profile, youtube=False, url=None):
        if url:
            from assistant_tools import safe_url
            url=safe_url(url,allow_local=True)
        executable = chrome_executable(profile["channel"])
        root = Path(profile["user_data_root"])
        directory = profile["profile_directory"]
        if not re.fullmatch(r"[A-Za-z0-9 _-]+", directory) or not (root / directory).is_dir():
            raise OSError("Profile directory unavailable")
        before = chrome_windows()
        command = [str(executable), "--user-data-dir=" + str(root), "--profile-directory=" + directory,
                   "--force-renderer-accessibility", "--new-window", url or ("https://www.youtube.com/" if youtube else "chrome://newtab/")]
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
                "url_requested": url or ("https://www.youtube.com/" if youtube else "chrome://newtab/")}


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
    def __init__(self, browser=None, preferences=None, schedules=None):
        self.browser = browser or BrowserLauncher()
        self.preferences = preferences
        self.memory_notice = ""
        self.paused = False
        self.pending_browser=None
        self._tools=None
        from scheduled_tasks import ScheduleStore
        self.schedules=schedules or ScheduleStore()
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
        self.stop_owned_processes()
        self.paused = True
        self.controller.sleep.cancel()
        self.controller.pending = None
        self.pending_browser=None

    def resume(self):
        self.paused = False
        self.controller.sleep.cancel()
        self.controller.pending = None
        self.pending_browser=None

    def stop_owned_processes(self):
        if self._tools and getattr(self._tools,'_terminal',None):self._tools._terminal.stop_all(wait=False)
        if self._tools and getattr(self._tools,'_comfy',None):self._tools._comfy.stop()
        if self._tools and getattr(self._tools,'_fooocus',None):self._tools._fooocus.stop()

    @property
    def tools(self):
        if self._tools is None:
            from assistant_tools import AssistantTools
            self._tools=AssistantTools(self)
        return self._tools

    def open_browser(self,profile_label='',url='',authorized=lambda:True):
        catalog=self.profile_catalog()
        profile=catalog.resolve_label(profile_label) if profile_label else None
        if profile is None:
            self.pending_browser={'url':url}
            return {'status':'needs_input','kind':'command','reply':'Untuk membuka '+(url or 'Chrome')+', profil mana yang ingin kamu gunakan: '+', '.join(catalog.label(p) for p in catalog.profiles.values())+'?'}
        row=self.profiles.get(profile.id)
        if not row:return {'status':'failed','kind':'command','reply':'Profil itu sudah tidak tersedia. Segarkan daftar profil.'}
        self.pending_browser=None;self.controller.pending=None
        if not authorized():return {'status':'cancelled','kind':'command','reply':'Permintaan dibatalkan.'}
        try:evidence=self.browser.launch(row,url=url or None)
        except OSError:return {'status':'failed','kind':'command','reply':'Chrome belum berhasil dibuka. Periksa instalasi dan profilnya.'}
        self.controller.active_profile_id=profile.id
        observed=bool(evidence.get('new_window_observed'))
        if self.preferences and observed:
            try:self.preferences.record('chrome',profile.id)
            except (OSError,sqlite3.Error):self.memory_notice='Tindakan selesai, tetapi kebiasaan belum tersimpan.'
        return {'status':'done' if observed else 'unverified','kind':'command',
            'reply':('Kubuka '+(url or 'tab baru')+' melalui Chrome profil '+profile.name+'. '+('Jendela baru terdeteksi.' if observed else 'Permintaannya terkirim; jendela baru belum terkonfirmasi.')),
            'evidence':evidence,'detail':'Tujuan dikirim ke Chrome; isi halaman dan login belum diverifikasi.'}

    def open_edge(self,url='',authorized=lambda:True):
        from assistant_tools import safe_url
        if url:url=safe_url(url,allow_local=True)
        candidates=[Path(base)/'Microsoft/Edge/Application/msedge.exe' for base in
                    (os.environ.get('PROGRAMFILES(X86)'),os.environ.get('PROGRAMFILES'),os.environ.get('LOCALAPPDATA')) if base]
        executable=next((p for p in candidates if p.is_file()),None)
        if not executable:return {'status':'failed','reply':'Instalasi Microsoft Edge belum ditemukan.'}
        if not authorized():return {'status':'cancelled','reply':'Permintaan dibatalkan.'}
        from windows_runtime import application_windows
        before=application_windows('Microsoft Edge','msedge.exe')
        try:subprocess.Popen([str(executable),'--new-window',url or 'edge://newtab/'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:return {'status':'failed','reply':'Permintaan membuka Edge gagal dikirim.'}
        deadline=time.monotonic()+6;observed=[]
        while time.monotonic()<deadline and authorized():
            observed=[w for w in application_windows('Microsoft Edge','msedge.exe') if w not in before]
            if observed:break
            time.sleep(.15)
        return {'status':'done' if observed else 'unverified','reply':'Tujuan '+(url or 'tab baru')+' dikirim ke Microsoft Edge. '+('Jendela baru terdeteksi.' if observed else 'Jendela baru belum terkonfirmasi.'),
                'evidence':{'browser':'edge','url_requested':url,'new_window_observed':bool(observed),'page_verified':False},'detail':'Isi halaman dan login belum diverifikasi.'}

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
        if re.match(r'^(?:tolong )?matikan sistem(?:mu| anda| kamu)?(?:\s|$)',value):
            self.pause();return {'kind':'command','cancel_ai':True,'reply':'Sistem AI dan pendengar lokal dihentikan. Gunakan Aktifkan untuk memulai lagi; laptop tetap menyala.'}
        if value in {"aktifkan", "aktifkan sistemmu", "lanjutkan", "lanjutkan sistem", "bangun", "resume"}:
            self.resume()
            return {"kind": "command",'resumed':True, "reply": "Aku aktif kembali. Jadwal jeda sebelumnya sudah dibatalkan."}
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
            return {"kind": "command", "status":"needs_input", "reply": "Aku sedang jeda. Tekan Aktifkan atau ketik ‘aktifkan’ untuk melanjutkan."}
        # Temporal scope must win over every immediate browser/application shortcut.
        from scheduled_tasks import deferred_request,parse_schedule
        if re.search(r'\b(lihat|daftar|tampilkan|cek)\b.*\b(pengingat|jadwal|memo)\b',value):
            rows=self.schedules.recent()
            return {'kind':'command','status':'done','reply':'\n'.join(r['id']+' · '+r['when']+' · '+r['title']+' · '+r['status'] for r in rows) or 'Belum ada pengingat tersimpan.'}
        if re.search(r'\b(batalkan|hapus)\b.*\b(pengingat|memo|jadwal tugas)\b',value):
            ident=re.search(r'\b[0-9a-f]{12}\b',value)
            if not ident:return {'kind':'command','status':'needs_input','reply':'Sebutkan ID pengingat dari daftar jadwal yang ingin dibatalkan.'}
            done=self.schedules.cancel(ident[0])
            return {'kind':'command','status':'done' if done else 'needs_input','reply':'Pengingat dibatalkan.' if done else 'Pengingat itu tidak ditemukan atau sudah berjalan. Tidak ada tindakan yang diulang.'}
        if deferred_request(text):
            try:
                plan=parse_schedule(text,now);job=self.schedules.add(**plan,now=now)
            except ValueError as error:return {'kind':'command','status':'needs_input','reply':str(error)}
            return {'kind':'command','status':'done','schedule':job,'reply':'Pengingat '+job['id']+' tersimpan untuk '+datetime.fromisoformat(job['when']).strftime('%d-%m-%Y pukul %H.%M WIB')+': '+job['title']+'.'+(' Pada waktu itu, tindakan berikut akan dijalankan: '+job['goal']+'.' if job['goal'] else '')+' Aplikasi belum dibuka sekarang.',
                    'detail':'Pengingat berjalan ketika laptop dan Leva aktif. Saat Jeda, tugas menunggu. Tindakan terlambat lebih dari 15 menit memerlukan arahan ulang.'}
        from assistant_tools import ACTION_WORDS,NEGATED,requested_url,requested_voice_language
        from speech_style import explicit_style
        style=explicit_style(text)
        if style:return {'kind':'command',**self.tools.execute('set_voice_style',{'style':style},text)}
        language=requested_voice_language(text)
        if language:
            return {'kind':'command',**self.tools.execute('set_voice_language',{'language':language},text)}
        # A short answer to an agent question keeps the whole original goal, before browser shortcuts.
        local_pending=(self.pending_browser and not self.pending_browser.get('from_agent')) or self.controller.pending
        continuation=None if local_pending else self.tools.continuation(text)
        if continuation:
            self.pending_browser=None;self.controller.pending=None
            return {'kind':'chat','needs_tools':True,'continuation_id':continuation['id']}
        # Multiple goals go to the agent intact; a Chrome shortcut must not drop Edge or later steps.
        multiple=bool(re.search(r'\b(?:dan|lalu|kemudian|setelah itu|habis itu|sekalian)\s+(?:(?:langsung|juga)\s+)?'+ACTION_WORDS,value))
        if multiple or re.search(r'\bchrome\b.*\bedge\b|\bedge\b.*\bchrome\b',value):
            self.pending_browser=None
            return {'kind':'chat','needs_tools':True}
        if self.pending_browser:
            choice=re.sub(r'^(?:ya[, ]*)?(?:pakai|pake|gunakan|pilih|buka)(?:kan)?\s+','',value)
            profile=self.profile_catalog().resolve_label(choice)
            if profile:return self.open_browser(profile.id,self.pending_browser['url'])
            if value in {'batal','batalkan','tidak jadi'}:
                self.pending_browser=None
                return {'kind':'command','reply':'Baik, pembukaan halaman dibatalkan.'}
            # A fresh request never inherits the destination from an older question.
            self.pending_browser=None
        if re.search(r'\b(jam berapa|pukul berapa|waktu sekarang|tanggal berapa|hari apa)\b',value) and not re.search(NEGATED,value):
            return {'kind':'command','status':'done','reply':'Sekarang pukul '+now.strftime('%H.%M')+' WIB, '+now.strftime('%d-%m-%Y')+'.','evidence':{'source':'system_clock','iso':now.isoformat()}}
        if re.search(ACTION_WORDS,value) and not re.search(NEGATED,value):
            url=requested_url(text)
            if url and (url!='https://www.youtube.com/' or re.search(r'\bedge\b',value) or 'http' in value):
                if re.search(r'\bedge\b',value):return {'kind':'command',**self.open_edge(url)}
                matches=self.profile_catalog().matches(text)
                return self.open_browser(matches[0].id if len(matches)==1 else '',url)
            if re.search(r'\b(discord|dc)\b',value):
                return {'kind':'command',**self.tools.apps.launch('discord')}
        self.sync_preferences()
        plan = self.controller.prepare(text, uuid.uuid4().hex, now)
        if plan.action == "unsupported":
            self.commit(plan)
            # Unsupported operations stay local; they do not become cloud action instructions.
            command_words = r"\b(buka|bukain|bukakan|pulihkan|balikin|hapus|kirim|unduh|jalankan|skip|iklan|cari|carikan)\b"
            if re.search(command_words, value):
                return {"kind": "chat", 'needs_tools':True}
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
