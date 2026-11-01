# -*- coding: utf-8 -*-
"""Сборка релиза «DownloadBro» для GitHub.

Делает два архива:
  release/DownloadBro-<версия>-win64.zip          — только exe (~25 МБ), ffmpeg докачивает сама программа
  release/DownloadBro-<версия>-win64-ffmpeg.zip   — exe + ffmpeg, распаковал и работает без интернета

Запуск:  .venv\\Scripts\\python.exe tools\\release.py
Флаги:   --skip-build  переупаковать уже собранный exe
         --ffmpeg local|essentials|none  что класть во второй архив (по умолчанию essentials)
         --set-version 2.1.0  прописать версию в downloadbro/__init__.py (использует CI по git-тегу)
"""
import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Консоль Windows в cp866/cp1251: юникодные стрелки и рамки в логе роняют сборку
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

APP = "DownloadBro"
OUT = ROOT / "release"
CACHE = OUT / "ffmpeg-cache"


def log(text):
    print(text, flush=True)


def set_version(ver):
    """Прописывает версию в downloadbro/__init__.py — так тег git и надпись в окне не разъезжаются."""
    init = ROOT / "downloadbro" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    new, count = re.subn(r'__version__ = "[^"]*"', f'__version__ = "{ver}"', text, count=1)
    if not count:
        raise SystemExit("в downloadbro/__init__.py нет строки __version__")
    init.write_text(new, encoding="utf-8")


def app_version():
    from downloadbro import __version__

    return __version__


def build_exe():
    icon = ROOT / "assets" / "icon.ico"
    if not icon.exists():
        subprocess.run([sys.executable, str(ROOT / "assets" / "make_icon.py")], cwd=ROOT, check=False)
    log("собираю exe через PyInstaller (1-3 минуты)…")
    if subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", f"{APP}.spec"], cwd=ROOT).returncode:
        raise SystemExit("PyInstaller завершился с ошибкой — смотри вывод выше")
    exe = ROOT / "dist" / f"{APP}.exe"
    if not exe.is_file():
        raise SystemExit(f"нет {exe} — сборка не оставила exe")
    return exe


def ffmpeg_pair(mode):
    """Путь к паре (ffmpeg.exe, ffprobe.exe) для bundling или (None, None)."""
    if mode == "none":
        return None, None
    cached = CACHE / "bin" / "ffmpeg.exe"
    if mode == "essentials":
        if not cached.is_file():
            from downloadbro.engine import download_ffmpeg

            log("качаю ffmpeg essentials (~90 МБ) в кеш релиза…")
            download_ffmpeg(dest=CACHE)
        return cached, cached.with_name("ffprobe.exe")
    from downloadbro.engine import find_ffmpeg

    found = find_ffmpeg()
    if not found:
        return None, None
    source = Path(found)
    return source, source.with_name("ffprobe.exe")


def readme_text(ver, has_ffmpeg):
    ffmpeg_note = (
        "ffmpeg лежит рядом — MP3, M4A, OPUS и склейка видео работают сразу, интернет не нужен."
        if has_ffmpeg
        else (
            "ffmpeg в этом архиве нет: для MP3, M4A, OPUS и склейки MP4 его нужно один раз докачать — "
            "Настройки → FFmpeg → «Скачать». Скачанное приложение находит само."
        )
    )
    return f"""{APP} {ver} — скачивание видео с 1700+ площадок

КТО ПЕРВЫЙ РАЗ
1. Распакуйте папку туда, куда удобно (Рабочий стол, D:\\Программы — куда угодно).
2. Запустите {APP}.exe. Установка не нужна: приложение портативное.
3. Вставьте ссылку на видео в первое поле и нажмите «Скачать».

ГДЕ ФАЙЛЫ И НАСТРОЙКИ
· Видео уходят в папку «Загрузки» — поменять: Настройки → «Куда сохранять».
· Настройки и история: %APPDATA%\\{APP}\\config.json. Удалите файл — и всё начнётся с чистого листа.
· {ffmpeg_note}

ЕСЛИ НЕ ЗАПУСКАЕТСЯ
· Windows пишет «не проверено приложение» — «Дополнительно» → «Выполнить в любом случае».
· Антивирус ругается на exe — это ложняк сборки PyInstaller, добавьте папку в исключения.
· Сбой окна сохраняется в {APP}_ошибка.txt рядом с exe.

ГОРЯЧИЕ КЛАВИШИ
Ctrl+V — вставить ссылку · Ctrl+L — поле ссылки · Ctrl+D — скачать · Esc — отменить всё
"""


def pack(exe, ver, pair, suffix):
    ffmpeg_exe, ffprobe_exe = pair
    folder = OUT / f"{APP}-{ver}-win64{suffix}"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    shutil.copy2(exe, folder / f"{APP}.exe")
    bundled = False
    if ffmpeg_exe and ffmpeg_exe.is_file():
        shutil.copy2(ffmpeg_exe, folder / "ffmpeg.exe")
        bundled = True
        if ffprobe_exe and ffprobe_exe.is_file():
            shutil.copy2(ffprobe_exe, folder / "ffprobe.exe")
    (folder / "КАК УСТАНОВИТЬ.txt").write_text(readme_text(ver, bundled), encoding="utf-8-sig")
    zip_path = OUT / f"{folder.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(OUT).as_posix())
    return folder, zip_path


def write_version_include(ver):
    """installer/version.inc — чтобы .iss и GitHub Actions брали одну и ту же версию."""
    target = ROOT / "installer" / "version.inc"
    text = f'; Версия для установщика; перезаписывает tools\\release.py.\n#define MyAppVersion "{ver}"\n'
    # Inno Setup понимает UTF-8 только с BOM, а без него читает как ANSI и ломает кириллицу
    target.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--ffmpeg", choices=("essentials", "local", "none"), default="essentials")
    parser.add_argument("--set-version", help="прописать версию в downloadbro/__init__.py (для CI: версия = git-тег)")
    args = parser.parse_args()

    if args.set_version:
        set_version(args.set_version)

    exe = ROOT / "dist" / f"{APP}.exe"
    if args.skip_build:
        if not exe.is_file():
            raise SystemExit(f"нет {exe} — сначала соберите без --skip-build")
    else:
        exe = build_exe()

    ver = app_version()
    write_version_include(ver)
    OUT.mkdir(exist_ok=True)

    results = []
    light_folder, light_zip = pack(exe, ver, (None, None), "")
    results.append((light_zip, light_folder))
    if args.ffmpeg != "none":
        try:
            pair = ffmpeg_pair(args.ffmpeg)
        except Exception as exc:
            log(f"⚠ ffmpeg для второго архива получить не удалось: {exc}")
            pair = (None, None)
        if pair[0]:
            full_folder, full_zip = pack(exe, ver, pair, "-ffmpeg")
            results.append((full_zip, full_folder))

    # Корневая копия: привычка «двойной клик по DownloadBro.exe в папке проекта»
    root_copy = ROOT / f"{APP}.exe"
    shutil.copy2(exe, root_copy)

    log("")
    log(f"exe: {exe}  ({exe.stat().st_size / 1048576:.1f} МБ)")
    for zip_path, folder in results:
        log(f"архив: {zip_path}  ({zip_path.stat().st_size / 1048576:.1f} МБ)  [папка {folder.name}]")
    log(f"копия в корне: {root_copy}")
    log("")
    log("установщик (необязательно): ISCC installer\\DownloadBro.iss → release\\DownloadBro-%s-setup.exe" % ver)


if __name__ == "__main__":
    main()
