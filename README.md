# DownloadBro

Приложение для Windows: вставил ссылку — получил видео или аудио. YouTube, Rutube, VK, OK, Дзен
и ещё ~1700 площадок, которые понимает yt-dlp. Внутри — yt-dlp + FFmpeg, интерфейс на customtkinter.

## Запуск из исходников

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

FFmpeg нужен для MP3/M4A/OPUS и для склейки видео в MP4 выше 720p. Ищем его в порядке:
`ffmpeg.exe` рядом с программой → `%LOCALAPPDATA%\DownloadBro\ffmpeg\bin` → PATH. Если не найден,
в «Настройках» есть кнопка «Скачать» — приложение само загрузит официальную сборку.

## Скачать

`https://github.com/Den4dev/DownloadBro/releases/latest` — один файл
`DownloadBro-<версия>-setup.exe`: установщик Inno Setup, ставится в профиль без прав
администратора, ярлыки на рабочем столе и в меню «Пуск». FFmpeg уже внутри, так что
MP3/M4A/OPUS и склейка MP4 работают сразу. Настройки и история — в `%APPDATA%\DownloadBro`.

При первом запуске SmartScreen может написать «Неизвестный издатель»: сборка не подписана
сертификатом — «Подробнее» → «Выполнить в любом случае».

## Релиз локально

```
.venv\Scripts\python.exe tools\release.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DownloadBro.iss
```

На выходе в папке `release\`:

| Файл | Что внутри | Когда нужен |
| --- | --- | --- |
| `DownloadBro-<версия>-setup.exe` | установщик (Inno Setup 6) + FFmpeg | то, что лежит в релизе |
| `DownloadBro-<версия>-win64.zip` | exe + памятка | ~25 МБ, портативный, FFmpeg докачивается по кнопке |
| `DownloadBro-<версия>-win64-ffmpeg.zip` | exe + ffmpeg.exe + ffprobe.exe | портативный офлайн-вариант |

Архивы в релиз не выкладываются: распаковывается в любую папку и запускается двойным кликом,
но для обычной установки достаточно setup.exe.
Настройки и история лежат в `%APPDATA%\DownloadBro\config.json`, каталог приложения не трогает.

Inno Setup 6 — [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php); при установке от
пользователя без админ-прав ISCC лежит в `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

Ручная сборка одного exe без архивов — `Собрать_EXE.bat` (результат в `dist\DownloadBro.exe`).

## Публикация релиза

`git tag v2.1.0 && git push origin v2.1.0` — GitHub Actions соберёт exe, установщик
и приложит `DownloadBro-<версия>-setup.exe` к релизу (`.github/workflows/release.yml`).
Версия из тега попадает в заголовок окна и в «DownloadBro» в сайдбаре.

## Проверка интерфейса

`tools/check_ui.py` — прогон реального окна: вставка ссылок, подсказка поля, превью, докачка
FFmpeg. Запуск: `.venv\Scripts\python.exe tools\check_ui.py`.

## Лицензии

Движок — yt-dlp (The Unlicense), FFmpeg — сборка с gyan.dev под GPL/LGPL (её и скачивает приложение,
в лёгком архиве её нет). Интерфейс — customtkinter (MIT).
