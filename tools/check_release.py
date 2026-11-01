# -*- coding: utf-8 -*-
"""Проверка собранного релиза: распаковать лёгкий zip, запустить exe, дождаться окна,
посчитать лишние окна, закрыть и убедиться, что процесс завершился без мусора."""
import ctypes
import ctypes.wintypes
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
APP_TITLE = "DownloadBro"
WORKDIR = Path.home() / "AppData" / "Local" / "Temp" / "downloadbro_verify"

user32 = ctypes.windll.user32
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.DWORD)]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]


def window_pid(hwnd):
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(ctypes.c_void_p(int(hwnd)), ctypes.byref(pid))
    return pid.value


def toplevels(pids=()):
    """Видимые окна: с заголовком, плюс все окна перечисленных pid — у Tk-подсказок
    заголовок пустой, и без этого фильтра их не видно."""
    rows, errors = [], []
    wanted = set(pids)

    def cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            owner = window_pid(int(hwnd))
            length = user32.GetWindowTextLengthW(hwnd)
            if not length and owner not in wanted:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            rows.append((int(hwnd), owner, title.value, cls.value))
        except Exception as exc:
            errors.append(repr(exc))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    if errors:
        print("ошибки перечисления окон:", errors[:2])
    return rows


def wipe_workdir():
    """Инстанс из временной папки блокирует файл — снимаем его, иначе распаковка падает."""
    script = (
        "Get-Process | Where-Object { $_.Path -like '" + str(WORKDIR) + "\\*' } | "
        "ForEach-Object { Stop-Process -Id $_.Id -Force }"
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   check=False, capture_output=True)
    time.sleep(1.5)
    subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(WORKDIR)], check=False, capture_output=True)
    WORKDIR.mkdir(parents=True, exist_ok=True)


def main():
    zip_path = sorted((ROOT / "release").glob("DownloadBro-*-win64.zip"))[-1]
    wipe_workdir()
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(WORKDIR)
    folder = next(p for p in WORKDIR.iterdir() if p.is_dir())
    exe = folder / f"{APP_TITLE}.exe"
    print(f"архив: {zip_path.name} ({zip_path.stat().st_size / 1048576:.1f} МБ)")
    print("распаковано:", [p.name for p in sorted(folder.iterdir())])

    before = {h for h, _p, _t, _c in toplevels()}
    launcher = subprocess.Popen([str(exe)])
    try:
        hwnd = None
        deadline = time.time() + 60
        while time.time() < deadline:
            handle = user32.FindWindowW(None, APP_TITLE)
            if handle and handle not in before:
                hwnd = handle
                break
            time.sleep(0.4)
        if not hwnd:
            print("ПРОВАЛ: окно «DownloadBro» не появилось")
            return 1

        owner = window_pid(hwnd)
        print(f"окно: hwnd={hwnd} pid={owner} (запускатель={launcher.pid})")
        if not owner:
            print("ПРОВАЛ: не определён pid окна")
            return 1

        time.sleep(4)
        mine = [(h, t, c) for h, p, t, c in toplevels([owner]) if p == owner]
        strays = [(h, t) for h, t, c in mine if c == "TkTopLevel" and t != APP_TITLE]
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        print(f"окон приложения: {len(mine)}, заголовки: {[t for _h, t, _c in mine]}")
        print(f"размер главного окна: {rect.right - rect.left}x{rect.bottom - rect.top}")
        print("лишние всплывающие окна:", strays if strays else "нет")

        user32.PostMessageW(hwnd, 0x0010, 0, 0)
        code = launcher.wait(timeout=30)
        print(f"закрытие по WM_CLOSE, код запуска: {code}")
        return 0 if not strays and code == 0 else 1
    finally:
        if launcher.poll() is None:
            launcher.kill()
        # onefile: за процессом стоит дочерний интерпретатор, он может дожулировать файл
        wipe_workdir()
        print("временная папка удалена:", not any(WORKDIR.iterdir()))


if __name__ == "__main__":
    sys.exit(main())
