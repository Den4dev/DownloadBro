import json
import os
import sys
import time
from pathlib import Path

APP_FOLDER = "DownloadBro"
CONFIG_NAME = "config.json"
HISTORY_LIMIT = 300

DEFAULTS = {
    "appearance": "dark",
    "accent": "indigo",
    "download_dir": "",
    "format": "mp4",
    "quality": "auto",
    "audio_bitrate": "320",
    "playlist": False,
    "subtitles": "none",
    "filename_template": "%(title)s.%(ext)s",
    "parallel_jobs": 2,
    "fragments": 8,
    "speed_limit": "",
    "cookies_browser": "",
    "ffmpeg_path": "",
    "confirm_close": True,
    "window": {"width": 1060, "height": 700, "x": None, "y": None},
    "history": [],
}


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_FOLDER
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def default_download_dir() -> str:
    home = Path.home()
    for candidate in (home / "Downloads", home / "Загрузки", home):
        if candidate.exists():
            return str(candidate)
    return str(home)


_MUTEX = None


def acquire_single_instance() -> bool:
    # False — такое окно уже открыто. Две копии пишат в один config.json и перетирают настройки друг друга.
    global _MUTEX
    if sys.platform != "win32":
        return True
    import ctypes

    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DownloadBroYouTubeSingleton")
    if not handle:
        return True
    _MUTEX = handle
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _MUTEX = None
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    return True


def focus_existing_window(title: str = "DownloadBro") -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and min(rect.left, rect.top) <= -30000:
        # Окно уехало за край экрана (свёрнулось или потерялось на другом мониторе) — возвращаем на рабочий стол
        width = rect.right - rect.left if rect.right > rect.left else 1060
        height = rect.bottom - rect.top if rect.bottom > rect.top else 700
        user32.MoveWindow(hwnd, 80, 80, width, height, True)
    # SetForegroundWindow из фонового процесса Windows игнорирует — SwitchToThisWindow обходит это
    user32.BringWindowToTop(hwnd)
    user32.SwitchToThisWindow(hwnd, True)
    user32.SetForegroundWindow(hwnd)
    return True


class Settings:

    def __init__(self):
        self.path = data_dir() / CONFIG_NAME
        self.data = dict(DEFAULTS)
        self.data["download_dir"] = default_download_dir()
        self._load()

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if key not in DEFAULTS:
                continue
            if isinstance(value, dict) and isinstance(DEFAULTS[key], dict):
                merged = dict(DEFAULTS[key])
                merged.update(value)
                self.data[key] = merged
            else:
                self.data[key] = value
        if not self.data["download_dir"] or not Path(self.data["download_dir"]).exists():
            self.data["download_dir"] = default_download_dir()

    def save(self):
        payload = {k: v for k, v in self.data.items() if k != "history"}
        payload["history"] = self.data["history"][:HISTORY_LIMIT]
        try:
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def get(self, key, fallback=None):
        return self.data.get(key, fallback if fallback is not None else DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, values: dict):
        self.data.update(values)
        self.save()

    @property
    def history(self):
        return self.data["history"]

    def add_history(self, entry: dict):
        entry = dict(entry)
        entry.setdefault("added_at", time.time())
        history = self.data["history"]
        history = [h for h in history if h.get("url") != entry.get("url")]
        self.data["history"] = [entry] + history
        self.save()

    def remove_history(self, url: str):
        self.data["history"] = [h for h in self.data["history"] if h.get("url") != url]
        self.save()

    def clear_history(self):
        self.data["history"] = []
        self.save()
