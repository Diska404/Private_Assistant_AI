"""Leva Windows desktop preview and isolated inference worker entrypoint."""
import json
import os
from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / "experiments")]

from paths import ROOT, DATA


def main():
    if "--voice-worker" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from live_voice import voice_worker
        request = json.loads(sys.stdin.readline())
        def emit(event):
            sys.stdout.write(json.dumps(event, ensure_ascii=True) + "\n")
            sys.stdout.flush()
        voice_worker(request, emit)
        return
    if "--voice-devices" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from live_voice import audio_devices
        sys.stdout.write(json.dumps(audio_devices(),ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--chat-worker" in sys.argv:
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from chat_service import run_worker
        from hybrid_engine import EngineError
        try:
            request = json.load(sys.stdin)
            result = run_worker(request)
        except EngineError as error:
            result = {"error": str(error)}
        except Exception:
            result = {"error": "worker_configuration_or_runtime_error"}
        sys.stdout.write(json.dumps(result, ensure_ascii=True))
        sys.stdout.flush()
        return
    if "--packaged-self-test" in sys.argv:
        # No network/model/browser effects: validate a packaged worker's pipe and ownership.
        from windows_runtime import restore_worker_streams
        restore_worker_streams()
        from chat_service import ChatService
        service = ChatService()
        results = {}
        try:
            service.ask("", "local")  # Empty message is rejected before any inference starts.
        except Exception as error:
            results["worker_roundtrip"] = str(error) == "invalid_chat_request"
        import tempfile
        from preferences import Preferences
        check_dir = DATA / "verification"
        check_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=check_dir,prefix="storage-self-test-") as folder:
            if not Path(folder).resolve().is_relative_to(check_dir.resolve()):
                raise RuntimeError("invalid_self_test_directory")
            path=Path(folder)/"fixture.sqlite3"
            store=Preferences(path)
            try:
                store.set("voice","Leda")
                store.set_alias("fixture","synthetic-profile")
                for _ in range(3):store.record("youtube","synthetic-profile")
            finally:
                store.close()
            store=Preferences(path)
            try:
                results["storage_roundtrip"]=store.persistent and store.get("voice")=="Leda" and store.suggestions({"synthetic-profile"})=={"youtube":"synthetic-profile"}
            finally:
                store.close()
        sys.stdout.write(json.dumps(results))
        sys.stdout.flush()
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, "Local\\LevaDesktopPreview")
    if ctypes.get_last_error() == 183:
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user.FindWindowW.restype = wintypes.HWND
        window = user.FindWindowW(None, "Leva — Asisten Desktop")
        if window:
            user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user.SetForegroundWindow.argtypes = [wintypes.HWND]
            user.ShowWindow(window, 9)
            user.SetForegroundWindow(window)
        return
    try:
        DATA.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # Preferences show an explicit session-only warning if D is unavailable.
    from gui import LevaWindow
    LevaWindow().run()


if __name__ == "__main__":
    main()
