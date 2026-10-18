"""Limited text-only feasibility experiment; no desktop tools or persistent service."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = Path(os.environ.get("LEVA_LOCAL_SERVER", "llama-server.exe"))
DEFAULT_MODEL = Path(os.environ.get("LEVA_LOCAL_MODEL", "model.gguf"))
DEFAULT_DATA = Path(os.environ.get("LEVA_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Leva")) / "experiments"
SYSTEM = (
    "Kamu Leva, asisten pribadi. Jawab Bahasa Indonesia secara singkat dan jujur. "
    "Percobaan ini hanya teks: kamu tidak mempunyai tools untuk membuka aplikasi, "
    "mengakses browser, atau mengubah komputer. Jangan mengaku sudah melakukan tindakan."
)


class EngineError(Exception):
    """Only sanitized classifications are allowed out of provider adapters."""


class OnlineUnavailable(EngineError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def check_online_status(status: int, body: dict) -> None:
    if status == 200:
        return
    code = body.get("error", {}).get("status", "UNKNOWN")
    if status == 429 and code == "RESOURCE_EXHAUSTED":
        raise OnlineUnavailable("quota_or_rate_limit")
    # Do not hide bad credentials, policy blocks, malformed input, or server errors.
    raise EngineError(f"online_http_{status}")


def _online_request(payload: str, key_file: Path, model: str) -> dict:
    key = os.environ.get("GEMINI_API_KEY") or key_file.read_text(encoding="utf-8-sig").strip()
    if not key or any(c in key for c in '\r\n"'):
        raise EngineError("invalid_credential_file")
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise EngineError("curl_not_available")
    # Key and prompt go through stdin, never command-line args or a temporary file.
    escaped_payload = payload.replace("\\", "\\\\").replace('"', '\\"')
    config = f'header = "x-goog-api-key: {key}"\ndata = "{escaped_payload}"\n'
    try:
        result = subprocess.run([
            curl, "-4", "--silent", "--connect-timeout", "8", "--max-time", "30",
            "--config", "-", "--header", "Content-Type: application/json",
            "--write-out", "\n%{http_code}",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ], input=config, capture_output=True, encoding="utf-8", timeout=35,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        raise EngineError("online_transport_failure") from None
    if result.returncode:
        raise EngineError("online_transport_failure")
    try:
        raw, code = result.stdout.rsplit("\n", 1)
        body = json.loads(raw)
        status = int(code)
    except (ValueError, TypeError):
        raise EngineError("invalid_online_response") from None
    check_online_status(status, body)
    return body


def online_generate(messages: list[dict], key_file: Path, model: str,
                    system: str = SYSTEM, max_output_tokens: int = 256,
                    response_json: bool = False) -> str:
    generation = {"maxOutputTokens": max_output_tokens}
    if response_json:
        generation["responseMimeType"] = "application/json"
    payload = json.dumps({"systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "model" if m["role"] == "assistant" else "user",
                      "parts": [{"text": m["content"]}]}
                     for m in messages if m["role"] != "system"],
        "generationConfig": generation}, ensure_ascii=False)
    body = _online_request(payload, key_file, model)
    candidates = body.get("candidates", [])
    if not candidates:
        raise EngineError("online_no_candidate")
    text = "".join(
        p.get("text", "") for p in candidates[0].get("content", {}).get("parts", [])
        if not p.get("thought")
    ).strip()
    if not text or candidates[0].get("finishReason") != "STOP":
        raise EngineError("online_incomplete_response")
    return text


def online_propose_tool(messages: list[dict], key_file: Path, model: str,
                        system: str, tools: list[dict]) -> dict:
    declarations = []
    for tool in tools:
        function = tool["function"]
        schema = {k: v for k, v in function["parameters"].items() if k != "additionalProperties"}
        declarations.append({"name": function["name"], "description": function["description"],
                             "parameters": schema})
    payload = json.dumps({"systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "model" if m["role"] == "assistant" else "user",
                      "parts": [{"text": m["content"]}]}
                     for m in messages if m["role"] != "system"],
        "tools": [{"functionDeclarations": declarations}],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
        "generationConfig": {"maxOutputTokens": 512}}, ensure_ascii=False)
    body = _online_request(payload, key_file, model)
    candidates = body.get("candidates", [])
    if not candidates or candidates[0].get("finishReason") != "STOP":
        raise EngineError("online_incomplete_tool_response")
    calls = [p["functionCall"] for p in candidates[0].get("content", {}).get("parts", [])
             if "functionCall" in p]
    if len(calls) != 1:
        raise EngineError("online_expected_one_tool_call")
    return {"action": calls[0].get("name"), "args": calls[0].get("args", {}),
            "usage": body.get("usageMetadata"), "native_tool_calls": calls}


def select_gpu_devices(device_output: str, mode: str) -> tuple[list[str], list[float]]:
    devices = []
    for line in device_output.splitlines():
        match = re.match(r"\s*(CUDA\d+): (.+?) \((\d+) MiB, (\d+) MiB free\)", line)
        if match:
            devices.append((match[1], match[2], int(match[4])))
    primary = next((d for d in devices if "RTX 4050" in d[1]), None)
    secondary = next((d for d in devices if "RTX 5070" in d[1]), None)
    if mode == "cpu":
        return [], []
    if primary is None:
        raise EngineError("rtx4050_not_available")
    selected = [primary]
    if mode == "dual":
        if secondary is None:
            raise EngineError("rtx5070_not_available_for_dual_mode")
        selected.append(secondary)
    # Relative split weights follow selected-device order, never nvidia-smi indices.
    # Reserve VRAM for other applications; --fit may retain layers in system RAM.
    budgets = [max(0, d[2] - 1024) for d in selected]
    if any(budget == 0 for budget in budgets):
        raise EngineError("insufficient_free_gpu_memory")
    return [d[0] for d in selected], [float(b) for b in budgets]


class LocalEngine:
    def __init__(self, server: Path, model: Path, data_dir: Path, mode: str = "gpu4050",
                 system: str = SYSTEM, max_output_tokens: int = 128,
                 context_size: int = 2048, response_json: bool = False,
                 sampling: dict | None = None, thinking_budget: int = 0):
        self.server, self.model, self.data_dir = server, model, data_dir
        self.process = None
        self.log = None
        self.endpoint = None
        self.api_key = secrets.token_urlsafe(32)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.load_seconds = None
        self.mode = mode
        self.devices = []
        self.gpu_snapshot_before = []
        self.gpu_snapshot_loaded = []
        self.gpu_allocations = []
        self.system = system
        self.max_output_tokens = max_output_tokens
        self.context_size = context_size
        self.response_json = response_json
        self.sampling = sampling or {"temperature": 0.2}
        self.thinking_budget = thinking_budget

    def gpu_snapshot(self):
        executable = shutil.which("nvidia-smi")
        if not executable:
            return []
        try:
            result = subprocess.run([executable,
                "--query-gpu=uuid,name,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, encoding="utf-8", timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return [{"uuid": row[0].strip(), "name": row[1].strip(),
                     "used_mib": int(row[2].strip())}
                    for row in csv.reader(result.stdout.splitlines()) if len(row) == 3]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []

    def process_gpu_allocations(self):
        executable = shutil.which("nvidia-smi")
        if not executable or not self.process:
            return []
        try:
            result = subprocess.run([executable,
                "--query-compute-apps=pid,gpu_uuid,used_gpu_memory", "--format=csv,noheader,nounits"],
                capture_output=True, encoding="utf-8", timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return [{"gpu_uuid": row[1].strip(), "used_memory_reported": row[2].strip()}
                    for row in csv.reader(result.stdout.splitlines())
                    if len(row) == 3 and row[0].strip() == str(self.process.pid)]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []

    def request(self, path: str, body: dict | None = None, timeout: float = 3) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.endpoint + path, data=data,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {self.api_key}"})
        with self.opener.open(request, timeout=timeout) as response:
            return json.load(response)

    def start(self):
        if self.process:
            return
        if not self.server.is_file() or not self.model.is_file():
            raise EngineError("local_runtime_or_model_missing")
        with self.model.open("rb") as file:
            if file.read(4) != b"GGUF":
                raise EngineError("local_model_not_gguf")
        gpu_args = ["--device", "none", "--gpu-layers", "0"]
        if self.mode != "cpu":
            self.gpu_snapshot_before = self.gpu_snapshot()
            try:
                discovery = subprocess.run([str(self.server), "--list-devices"],
                    capture_output=True, encoding="utf-8", timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.TimeoutExpired):
                raise EngineError("gpu_discovery_failed") from None
            if discovery.returncode:
                raise EngineError("gpu_discovery_failed")
            self.devices, budgets = select_gpu_devices(
                discovery.stdout + "\n" + discovery.stderr, self.mode)
            gpu_args = ["--device", ",".join(self.devices), "--gpu-layers", "auto",
                        "--fit", "on", "--fit-target", "1024", "--fit-ctx", str(self.context_size),
                        "--main-gpu", "0", "--split-mode", "layer" if self.mode == "dual" else "none"]
            if self.mode == "dual":
                gpu_args += ["--tensor-split", ",".join(str(b) for b in budgets)]
        # No public bind, no existing server reused, and no existing process stopped.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.endpoint = f"http://127.0.0.1:{port}"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log = (self.data_dir / f"local-runtime-{self.mode}.log").open("w", encoding="utf-8")
        started = time.monotonic()
        try:
            worker_env = os.environ.copy()
            worker_env.pop("GEMINI_API_KEY", None)
            worker_env.pop("GOOGLE_API_KEY", None)
            worker_env["LLAMA_API_KEY"] = self.api_key
            self.process = subprocess.Popen([
                str(self.server), "--model", str(self.model), "--host", "127.0.0.1",
                "--port", str(port), *gpu_args,
                "--threads", "4", "--threads-batch", "4", "--ctx-size", str(self.context_size),
                "--parallel", "1", "--reasoning-budget", str(self.thinking_budget), "--no-webui",
                "--cors-origins", "http://127.0.0.1", "--no-cors-credentials",
            ], stdout=self.log, stderr=self.log, env=worker_env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = started + 90
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise EngineError("local_runtime_exited_during_startup")
                try:
                    health = self.request("/health", timeout=1)
                    if health.get("status") == "ok":
                        self.load_seconds = round(time.monotonic() - started, 3)
                        if self.mode != "cpu":
                            self.gpu_snapshot_loaded = self.gpu_snapshot()
                            self.gpu_allocations = self.process_gpu_allocations()
                        return
                except (OSError, ValueError):
                    pass
                time.sleep(0.25)
            raise EngineError("local_startup_timeout")
        except BaseException:
            self.close()
            raise

    def generate(self, messages: list[dict]) -> str:
        self.start()
        try:
            payload = {
                "messages": [{"role": "system", "content": self.system}] + messages,
                "max_tokens": self.max_output_tokens, **self.sampling,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            if self.response_json:
                payload["response_format"] = {"type": "json_object"}
            result = self.request("/v1/chat/completions", payload, timeout=90)
            choice = result["choices"][0]
            text = choice["message"].get("content", "").strip()
            if not text or choice.get("finish_reason") != "stop":
                raise EngineError("local_incomplete_response")
            return text
        except (OSError, ValueError, KeyError, IndexError):
            raise EngineError("local_generation_failure") from None

    def propose_tool(self, messages: list[dict], tools: list[dict]) -> dict:
        """Use the model's embedded template and server's native tool-call parser."""
        self.start()
        try:
            result = self.request("/v1/chat/completions", {
                "messages": [{"role": "system", "content": self.system}] + messages,
                "tools": tools, "tool_choice": "required", "parallel_tool_calls": False,
                "max_tokens": self.max_output_tokens, **self.sampling,
                "chat_template_kwargs": {"enable_thinking": self.thinking_budget != 0},
            }, timeout=90)
            choice = result["choices"][0]
            message = choice["message"]
            calls = message.get("tool_calls", [])
            output = {"content": message.get("content"), "tool_calls": calls,
                      "finish_reason": choice.get("finish_reason"), "usage": result.get("usage")}
            if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                output["error"] = "incomplete_native_tool_response"
                return output
            if len(calls) != 1:
                output["error"] = "expected_one_native_tool_call"
                return output
            function = calls[0]["function"]
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            output["action"], output["args"] = function["name"], arguments
            return output
        except (OSError, ValueError, KeyError, IndexError):
            raise EngineError("native_tool_response_or_transport_failure") from None

    def close(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None
        if self.log:
            self.log.close()
            self.log = None


class HybridEngine:
    def __init__(self, online, local):
        self.online, self.local = online, local
        self.online_paused = False
        self.reason = None

    def generate(self, messages: list[dict]) -> dict:
        if not self.online_paused:
            try:
                text = self.online(messages)
                return {"provider": "google", "fallback_reason": None, "response": text}
            except OnlineUnavailable as error:
                # Session sticky: subsequent prompts do not repeatedly hit exhausted quota.
                self.online_paused, self.reason = True, error.reason
        text = self.local(messages)
        return {"provider": "local", "fallback_reason": self.reason, "response": text}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--simulate-online-quota", action="store_true",
                        help="Skip Google and inject a synthetic 429; local inference is real.")
    parser.add_argument("--key-file", type=Path, default=ROOT / "API Key.txt")
    parser.add_argument("--online-model", default="gemini-3.5-flash-lite",
                        choices=["gemini-3.5-flash-lite", "gemini-3.8-flash"])
    parser.add_argument("--local-server", type=Path, default=DEFAULT_SERVER)
    parser.add_argument("--local-model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--local-mode", default="gpu4050", choices=["gpu4050", "dual", "cpu"],
                        help="Default: RTX 4050 first; dual explicitly adds RTX 5070; CPU is opt-in.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    local = LocalEngine(args.local_server, args.local_model, args.data_dir, args.local_mode)
    def online(messages):
        if args.simulate_online_quota:
            check_online_status(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        return online_generate(messages, args.key_file, args.online_model)
    engine = HybridEngine(online, local.generate)
    started = time.monotonic()
    try:
        result = engine.generate([{"role": "user", "content": args.prompt}])
        result.update(simulated_quota=args.simulate_online_quota,
                      online_model=args.online_model, local_model=args.local_model.name,
                      local_mode=args.local_mode, local_devices=local.devices,
                      gpu_snapshot_before=local.gpu_snapshot_before,
                      gpu_snapshot_loaded=local.gpu_snapshot_loaded,
                      process_gpu_allocations=local.gpu_allocations,
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      local_load_seconds=local.load_seconds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except EngineError as error:
        print(json.dumps({"success": False, "error": str(error),
                          "online_paused": engine.online_paused}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({"success": False, "error": "configuration_or_transport_error"}))
        return 1
    finally:
        local.close()


if __name__ == "__main__":
    raise SystemExit(main())
