"""Cancellable child-worker inference. No executable action tools are exposed to a model."""
from datetime import datetime
import json
import os
import subprocess
import sys
import threading

from hybrid_engine import LocalEngine, HybridEngine, DEFAULT_SERVER, DEFAULT_MODEL, online_generate, EngineError
from paths import ROOT, DATA
from windows_runtime import ProcessJob

PERSONA = (
    "Kamu Leva, asisten pribadi berbahasa Indonesia. Sikapmu tenang, perhatian, tanggap dan boleh "
    "sedikit menggoda dengan ramah. Jawab alami dan jelas. Jangan mengaku sebagai karakter fiksi asli. "
    "Fakta produk: kamu berjalan di aplikasi Windows Leva Desktop versi pratinjau 0.3 yang sudah bisa "
    "dibuka pengguna. Aplikasi menyediakan obrolan AI, tombol/perintah lokal membuka profil Chrome "
    "dan YouTube, serta jeda dan jadwal istirahat Leva. Mode Neural Voice menyediakan percakapan suara Google Live "
    "dan animasi; mikrofon hanya aktif ketika pengguna menekan Mulai suara. Voice lokal dan suara Shiroko belum tersedia. "
    "Aplikasi memiliki pengaturan tersimpan, alias profil yang ditetapkan pengguna dan hitungan kebiasaan profil lokal; "
    "kebiasaan hanya untuk menawarkan pilihan dan bukan training atau ingatan isi percakapan. "
    "Wake word offline, skip iklan, pemulihan tab, riset web langsung, WhatsApp dan autostart belum tersedia. Kamu tidak mengetahui kemajuan "
    "pekerjaan pengembang secara langsung; jangan mengarang laporan proses pembangunan. "
    "Pada saluran obrolan ini kamu tidak memiliki tools komputer atau akses web. Jangan mengaku "
    "sudah membuka aplikasi, membaca layar, mencari web, mengubah file atau mengaktifkan jadwal. "
    "Jika diminta melakukan tindakan, jelaskan keterbatasan atau arahkan ke perintah/tombol aplikasi. "
    "Jangan mengarang hasil browsing atau status resource. Jangan menyebut seseorang dengan nama profil Chrome."
)


def bounded_history(messages):
    chosen, remaining = [], 6500
    for message in reversed(messages[-8:]):
        content = message["content"]
        if len(content) > remaining:
            break
        chosen.append({"role": message["role"], "content": content})
        remaining -= len(content)
    return list(reversed(chosen))


def run_worker(request):
    mode = request.get("mode", "hybrid")
    local = LocalEngine(DEFAULT_SERVER, DEFAULT_MODEL,
                        DATA / "runtime" / datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
                        mode=request.get("local_mode", "gpu4050"), system=PERSONA,
                        context_size=4096, max_output_tokens=384)
    try:
        messages = bounded_history(request["messages"])
        if not messages or messages[-1]["role"] != "user" or not messages[-1]["content"].strip():
            raise EngineError("invalid_chat_request")
        if mode == "local":
            return {"provider": "local", "response": local.generate(messages), "fallback_reason": None}
        router = HybridEngine(lambda m: online_generate(m, ROOT / "API Key.txt", "gemini-3.5-flash-lite",
                                                        system=PERSONA, max_output_tokens=512), local.generate)
        router.online_paused = bool(request.get("online_paused"))
        router.reason = "quota_or_rate_limit" if router.online_paused else None
        return router.generate(messages)
    finally:
        local.close()


class ChatService:
    def __init__(self, worker_command=None):
        self.worker_command = worker_command or ([sys.executable, "--chat-worker"] if getattr(sys, "frozen", False)
            else [sys.executable, "-B", str(ROOT / "app" / "main.py"), "--chat-worker"])
        self.process = self.job = None
        self.lock = threading.Lock()
        self.epoch = 0
        self.online_paused = False
        self.history = []

    def cancel(self):
        with self.lock:
            self.epoch += 1
            job, process = self.job, self.process
            self.job = self.process = None
        if job:
            job.close()
        elif process and process.poll() is None:
            process.terminate()

    def ask(self, text, mode="hybrid", local_mode="gpu4050"):
        with self.lock:
            epoch = self.epoch
            process = subprocess.Popen(self.worker_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, encoding="utf-8",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                job = ProcessJob(process)
            except OSError:
                process.terminate()
                process.wait(timeout=5)
                raise EngineError("worker_containment_failed") from None
            self.process, self.job = process, job
        payload = {"messages": bounded_history([*self.history, {"role": "user", "content": text}]),
                   "mode": mode, "local_mode": local_mode, "online_paused": self.online_paused}
        try:
            output, _ = process.communicate(json.dumps(payload, ensure_ascii=True), timeout=160)
            with self.lock:
                if epoch != self.epoch:
                    return {"cancelled": True}
            if process.returncode != 0:
                raise EngineError("chat_worker_failed")
            try:
                result = json.loads(output)
            except (ValueError, TypeError):
                raise EngineError("invalid_worker_response") from None
            if "error" in result:
                raise EngineError(result["error"])
            if not isinstance(result.get("response"), str):
                raise EngineError("empty_chat_response")
            if result.get("fallback_reason") == "quota_or_rate_limit":
                self.online_paused = True
            self.history = bounded_history([*self.history, {"role": "user", "content": text},
                                           {"role": "assistant", "content": result["response"]}])
            return result
        except subprocess.TimeoutExpired:
            raise EngineError("chat_timeout") from None
        except OSError:
            with self.lock:
                if epoch != self.epoch:
                    return {"cancelled": True}
            raise EngineError("worker_transport_failed") from None
        finally:
            with self.lock:
                if self.process is process:
                    self.process = self.job = None
            job.close()
            if process.poll() is None:
                process.wait(timeout=5)
