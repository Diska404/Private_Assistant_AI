"""Minimal Windows process ownership and read-only input/window evidence."""
import ctypes
from ctypes import wintypes as W
import os
import threading


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(key, ctypes.c_ulonglong) for key in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class ProcessJob:
    """Closing the owner kills only its worker and descendants, including llama-server."""
    def __init__(self, process):
        self.lock = threading.Lock()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
        kernel.CreateJobObjectW.restype = W.HANDLE
        kernel.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel, self.handle = kernel, kernel.CreateJobObjectW(None, None)
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError("Cannot initialize owned process job")
        if not kernel.AssignProcessToJobObject(self.handle, W.HANDLE(int(process._handle))):
            self.close()
            raise OSError("Cannot contain inference worker")

    def close(self):
        with self.lock:
            if getattr(self, "handle", None):
                self.kernel.CloseHandle(self.handle)
                self.handle = None


def chrome_windows():
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [W.HWND]
    found = {}
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def visit(hwnd, _):
        if user.IsWindowVisible(hwnd):
            name, title = ctypes.create_unicode_buffer(128), ctypes.create_unicode_buffer(1024)
            user.GetClassNameW(hwnd, name, 128)
            user.GetWindowTextW(hwnd, title, 1024)
            if name.value.startswith("Chrome_WidgetWin") and "Google Chrome" in title.value:
                found[int(hwnd)] = title.value
        return True
    user.EnumWindows.argtypes = [callback_type, W.LPARAM]
    user.EnumWindows(visit, 0)
    return found


def idle_milliseconds():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF


def restore_worker_streams():
    """Windowed PyInstaller workers receive explicit pipes rather than a console."""
    import sys
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [W.DWORD]
    kernel.GetStdHandle.restype = W.HANDLE
    for name, code, flags, mode in [("stdin", -10, os.O_RDONLY, "r"), ("stdout", -11, os.O_WRONLY, "w")]:
        if getattr(sys, name) is None:
            handle = kernel.GetStdHandle(code & 0xFFFFFFFF)
            if not handle or handle == ctypes.c_void_p(-1).value:
                raise OSError("Worker pipe unavailable")
            fd = msvcrt.open_osfhandle(handle, flags)
            setattr(sys, name, os.fdopen(fd, mode, encoding="utf-8"))
        elif hasattr(getattr(sys, name), "reconfigure"):
            getattr(sys, name).reconfigure(encoding="utf-8")
