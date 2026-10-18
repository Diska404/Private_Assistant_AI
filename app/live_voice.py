"""Native Google Live audio worker. Microphone starts only on explicit UI activation."""
import base64
from datetime import datetime
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

from paths import ROOT
from voice_core import PlaybackBuffer, VoiceEvents, pcm_level, voice_setup
from windows_runtime import ProcessJob

ENDPOINT = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


def connect_live():
    from websockets.sync.client import connect
    key = os.environ.get("GEMINI_API_KEY") or (ROOT / "API Key.txt").read_text(encoding="utf-8-sig").strip()
    if not key or any(x in key for x in '\r\n"'):
        raise ValueError("invalid_voice_credential")
    address = socket.getaddrinfo("generativelanguage.googleapis.com", 443, socket.AF_INET, socket.SOCK_STREAM)[0][4]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(12)
        sock.connect(address)
        return connect(ENDPOINT, sock=sock, additional_headers={"x-goog-api-key": key}, proxy=None,
                       open_timeout=12, close_timeout=2, max_size=8*1024*1024,
                       max_queue=32, compression=None)
    except BaseException:
        sock.close()
        raise


def audio_devices():
    import sounddevice as sd
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    # MME supports these 16/24 kHz mono streams via shared-mode conversion on this laptop.
    inputs, outputs = [], []
    for index, device in enumerate(devices):
        api = hostapis[device["hostapi"]]["name"]
        if api != "MME" or "Sound Mapper" in device["name"]:
            continue
        row = {"id": index, "name": device["name"]}
        if device["max_input_channels"]:
            inputs.append(row)
        if device["max_output_channels"]:
            outputs.append(row)
    default_input, default_output = map(int, sd.default.device)
    # Prefer the matching headset, without modifying Windows' default devices.
    microphone = next((d["name"].lower() for d in inputs if d["id"] == default_input), "")
    matching = [d for d in outputs if "headphone" in d["name"].lower()
                and any(word in microphone for word in d["name"].lower().replace("(", " ").split()
                        if len(word) >= 4 and word not in {"headphones", "microphone"})]
    if matching:
        default_output = matching[0]["id"]
    return {"inputs": inputs, "outputs": outputs, "default_input": default_input, "default_output": default_output}


def voice_worker(request, emit):
    """Four independent loops: capture, send, receive, output callback. No capture muting during speech."""
    import sounddevice as sd
    playback = PlaybackBuffer()
    capture = queue.Queue(maxsize=24)
    commands = queue.Queue(maxsize=8)
    stopped = threading.Event()
    state = {"sent_at": 0.0, "heard_at": 0.0, "sounding": False, "turn_done": True,
             "input_text": "", "output_text": "", "input_meter": 0.0, "output_meter": 0.0}
    lock = threading.Lock()
    started = time.monotonic()

    def event(kind, **fields):
        with lock:
            emit({"kind": kind, **fields})

    def stdin_commands():
        for line in sys.stdin:
            try:
                commands.put_nowait(json.loads(line))
            except (ValueError, queue.Full):
                continue
        stopped.set()
    threading.Thread(target=stdin_commands, daemon=True).start()

    def on_input(indata, frames, clock, status):
        data = bytes(indata)
        level = pcm_level(data)
        state["input_meter"] = level
        if level > 0.045:
            state["heard_at"] = time.monotonic()
        try:
            capture.put_nowait(data)
        except queue.Full:
            # Discard oldest audio instead of accumulating several seconds of stale commands.
            try:
                capture.get_nowait()
                capture.put_nowait(data)
            except (queue.Empty, queue.Full):
                pass

    def on_output(outdata, frames, clock, status):
        actual, padded = playback.pop(frames * 2)
        outdata[:] = padded
        state["output_meter"] = pcm_level(actual)
        state["sounding"] = bool(actual)

    event("state", state="connecting")
    ws = None
    microphone = speaker = None
    try:
        ws = connect_live()
        ws.send(json.dumps(voice_setup(voice=request.get("voice", "Kore"))))
        setup = json.loads(ws.recv(timeout=15))
        if "setupComplete" not in setup:
            raise ValueError("live_setup_rejected")
        if request.get("probe_only"):
            event("ready", microphone_open=False, model="gemini-3.8-live")
            return
        # Never open microphone before successful connection/setup or when only previewing visuals.
        microphone = sd.RawInputStream(device=request["input_device"], samplerate=16000, blocksize=640,
                                       channels=1, dtype="int16", callback=on_input)
        speaker = sd.RawOutputStream(device=request["output_device"], samplerate=24000, blocksize=960,
                                    channels=1, dtype="int16", callback=on_output)
        def receive():
            try:
                while not stopped.is_set():
                    try:
                        message = json.loads(ws.recv(timeout=1))
                    except TimeoutError:
                        continue
                    content = message.get("serverContent", {})
                    if content.get("interrupted"):
                        playback.clear()
                        state["turn_done"] = True
                        state["output_text"] = ""
                        event("state", state="interrupted")
                    for part in content.get("modelTurn", {}).get("parts", []):
                        audio = part.get("inlineData", {})
                        if audio.get("mimeType", "").startswith("audio/pcm") and audio.get("data"):
                            playback.push(base64.b64decode(audio["data"]))
                            state["turn_done"] = False
                    transcript = content.get("inputTranscription")
                    if transcript:
                        state["input_text"] += transcript.get("text", "")
                        event("input_text", text=state["input_text"], final=bool(transcript.get("finished")))
                        if transcript.get("finished"):
                            state["turn_done"] = False
                            state["input_text"] = ""
                    transcript = content.get("outputTranscription")
                    if transcript:
                        state["output_text"] += transcript.get("text", "")
                        event("output_text", text=state["output_text"])
                    if content.get("turnComplete"):
                        if state["input_text"]:
                            event("input_text", text=state["input_text"], final=True)
                        event("turn_finished", text=state["output_text"])
                        state["input_text"] = ""
                        state["output_text"] = ""
                        state["turn_done"] = True
                    if message.get("goAway"):
                        event("notice", code="session_time_limit")
            except Exception as error:
                event("error", code=classify_voice_error(error))
                stopped.set()
        with microphone, speaker:
            threading.Thread(target=receive, daemon=True).start()
            event("state", state="listening", microphone_open=True)
            last_meter = 0.0
            while not stopped.is_set():
                # Fixed upper bound prevents unattended streaming beyond this preview session.
                if time.monotonic() - started > 15*60:
                    event("notice", code="preview_session_ended")
                    break
                while not commands.empty():
                    command = commands.get_nowait()
                    if command.get("kind") == "stop":
                        stopped.set()
                        break
                    if command.get("kind") == "interrupt":
                        playback.clear()
                        ws.send(json.dumps({"clientContent": {"turns": [{"role": "user", "parts": [{"text": "Berhenti berbicara, tunggu aku."}]}], "turnComplete": True}}))
                    if command.get("kind") == "text":
                        ws.send(json.dumps({"realtimeInput": {"text": command.get("text", "")[:1200]}}))
                try:
                    data = capture.get(timeout=0.04)
                    ws.send(json.dumps({"realtimeInput": {"audio": {
                        "mimeType": "audio/pcm;rate=16000", "data": base64.b64encode(data).decode("ascii")}}}))
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_meter >= 0.1:
                    mode = "speaking" if (state["sounding"] or len(playback)) else "listening"
                    if mode == "listening" and not state["turn_done"]:
                        mode = "listening" if now-state["heard_at"]<0.65 else "thinking"
                    event("meter", input=round(state["input_meter"], 4), output=round(state["output_meter"], 4), state=mode)
                    last_meter = now
    except Exception as error:
        event("error", code=classify_voice_error(error))
    finally:
        stopped.set()
        playback.clear()
        # Stream construction opens a PortAudio handle even before __enter__.
        # Close either handle if constructing its partner failed.
        for stream in (microphone,speaker):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        event("stopped", microphone_open=False)


def classify_voice_error(error):
    code = getattr(getattr(error, "rcvd", None), "code", None)
    reason = str(getattr(getattr(error, "rcvd", None), "reason", "")).lower()
    if code == 1011 and any(s in reason for s in ["quota", "resource", "exhaust"]):
        return "live_quota_or_capacity"
    if code == 1008:
        return "live_access_or_model_rejected"
    if isinstance(error, BufferError):
        return "audio_output_backlog"
    if type(error).__name__ == "PortAudioError":
        return "audio_device_unavailable"
    return "live_connection_or_audio_error"


class LiveVoiceService:
    def __init__(self, worker_command=None):
        self.process = self.job = None
        self.events = VoiceEvents()
        self.epoch = 0
        self.worker_command=worker_command

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def start(self, input_device, output_device, voice="Kore"):
        if self.active:
            return
        self.stop()
        self.epoch += 1
        epoch = self.epoch
        command = self.worker_command or ([sys.executable, "--voice-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-B", str(ROOT/"app"/"main.py"), "--voice-worker"])
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            job = ProcessJob(process)
        except OSError:
            process.terminate()
            process.wait(timeout=5)
            raise
        self.process, self.job = process, job
        try:
            process.stdin.write(json.dumps({"input_device": input_device, "output_device": output_device, "voice": voice}) + "\n")
            process.stdin.flush()
        except (OSError,ValueError):
            self.stop()
            raise OSError("voice_worker_start_failed") from None
        def read():
            stopped_seen = False
            try:
                for line in process.stdout:
                    if epoch != self.epoch:
                        break
                    try:
                        event=json.loads(line)
                        if not isinstance(event,dict):
                            continue
                        stopped_seen = stopped_seen or event.get("kind")=="stopped"
                        self.events.put_nowait(event)
                    except (ValueError, queue.Full):
                        pass
            except (OSError, ValueError):
                pass
            finally:
                job.close()
                if epoch == self.epoch:
                    if not stopped_seen:
                        self.events.put_nowait({"kind":"error","code":"voice_worker_unexpected_exit"})
                        self.events.put_nowait({"kind": "stopped", "microphone_open": False})
        threading.Thread(target=read, daemon=True).start()

    def send(self, message):
        if self.active:
            try:
                self.process.stdin.write(json.dumps(message, ensure_ascii=True) + "\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.stop()

    def stop(self):
        self.epoch += 1
        process, job = self.process, self.job
        self.process = self.job = None
        if job:
            job.close()
        if process:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            try:
                process.stdin.close()
                process.stdout.close()
            except (OSError, ValueError):
                pass
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
