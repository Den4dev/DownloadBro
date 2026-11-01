import os
import queue
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from pathlib import Path

import yt_dlp

# Площадки, которым приложение даёт привычное имя. yt-dlp умеет больше полутора тысяч сайтов,
# всё остальное отдаётся ему как есть.
PLATFORMS = (
    ("YouTube", "youtube.com", "youtu.be", "youtube-nocookie.com"),
    ("Rutube", "rutube.ru"),
    ("ВКонтакте", "vk.com", "vk.ru", "vkvideo.ru", "vkplay.ru"),
    ("Одноклассники", "ok.ru", "odnoklassniki.ru"),
    ("Дзен", "dzen.ru", "zen.yandex.ru"),
    ("Яндекс Видео", "yandex.ru", "yandex.by", "yandex.kz", "yandex.com"),
    ("Смотрим", "smotrim.ru"),
    ("Кинопоиск", "kinopoisk.ru"),
    ("Иви", "ivi.ru"),
    ("Mail.ru", "mail.ru"),
    ("TikTok", "tiktok.com"),
    ("X / Twitter", "twitter.com", "x.com"),
    ("Instagram", "instagram.com"),
    ("Facebook", "facebook.com", "fb.watch"),
    ("Twitch", "twitch.tv", "clips.twitch.tv"),
    ("Vimeo", "vimeo.com"),
    ("Dailymotion", "dailymotion.com"),
    ("Reddit", "reddit.com", "redd.it"),
    ("SoundCloud", "soundcloud.com"),
    ("Bilibili", "bilibili.com"),
    ("Archive.org", "archive.org"),
)

# Ключи экстракторов yt-dlp -> привычные названия (своя логика у "RutubeMovie", "VKWallPost" и т.п.)
EXTRACTOR_NAMES = {
    "youtube": "YouTube",
    "rutube": "Rutube",
    "vk": "ВКонтакте",
    "odnoklassniki": "Одноклассники",
    "ok": "Одноклассники",
    "zenyandex": "Дзен",
    "yandex": "Яндекс Видео",
    "smotrim": "Смотрим",
    "kinopoisk": "Кинопоиск",
    "ivi": "Иви",
    "mailru": "Mail.ru",
    "tiktok": "TikTok",
    "twitter": "X / Twitter",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "twitch": "Twitch",
    "vimeo": "Vimeo",
    "dailymotion": "Dailymotion",
    "reddit": "Reddit",
    "soundcloud": "SoundCloud",
    "bilibili": "Bilibili",
    "archiveorg": "Archive.org",
    "telegram": "Telegram",
}


def platform_of(url):
    """Имя площадки по домену ссылки, либо "" если площадка не из списка известных."""
    host = urllib.parse.urlparse(url).netloc.lower()
    host = re.sub(r"^[^@/]*@", "", host)
    host = re.sub(r":\d+$", "", host).strip(".")
    for name, *domains in PLATFORMS:
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return name
    return ""


def extractor_name(key, url=""):
    """Название площадки по ключу экстрактора, который вернул yt-dlp."""
    key = (key or "").lower()
    for prefix, name in EXTRACTOR_NAMES.items():
        if key.startswith(prefix):
            return name
    if key and key != "generic":
        return (key or "")[:1].upper() + (key or "")[1:]
    return platform_of(url)


SUPPORTED_HINT = " · ".join(name for name, *_ in PLATFORMS[:10])

# ffmpeg нужен для склейки MP4 и звука в MP3. В релизе он лежит рядом с exe,
# а если его нет — приложение может докачать официальную сборку в профиль пользователя.
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def app_dir():
    """Папка, где лежит exe (в onefile __file__ указывает во временную распаковку)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def ffmpeg_install_dir():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "DownloadBro" / "ffmpeg"


def find_ffmpeg():
    """ffmpeg рядом с exe, в профиле пользователя или в PATH — что найдётся первым."""
    base = app_dir()
    candidates = [
        base / "ffmpeg.exe",
        base / "ffmpeg" / "bin" / "ffmpeg.exe",
        base / "ffmpeg" / "ffmpeg.exe",
        base / "bin" / "ffmpeg.exe",
        ffmpeg_install_dir() / "bin" / "ffmpeg.exe",
        ffmpeg_install_dir() / "ffmpeg.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return shutil.which("ffmpeg") or ""


def download_ffmpeg(report=None, dest=None):
    """Качает официальную сборку ffmpeg (gyan.dev) и кладёт ffmpeg.exe/ffprobe.exe в профиль.

    dest нужен сборщику релиза: он распаковывает те же бинарники в папку рядом с exe.
    """
    import ssl
    import tempfile
    import urllib.request
    import zipfile

    bin_dir = Path(dest) / "bin" if dest else ffmpeg_install_dir() / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        context = ssl.create_default_context()
    request = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "downloadbro"})
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        total = int(response.headers.get("Content-Length") or 0)
        with tempfile.TemporaryFile() as buffer:
            done = 0
            while True:
                chunk = response.read(512 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
                done += len(chunk)
                if report:
                    report(done, total)
            buffer.seek(0)
            with zipfile.ZipFile(buffer) as archive:
                wanted = {"ffmpeg.exe", "ffprobe.exe"}
                for member in archive.namelist():
                    parts = member.replace("\\", "/").split("/")
                    name = parts[-1].lower()
                    if name in wanted and "bin" in (part.lower() for part in parts[:-1]):
                        with archive.open(member) as src, open(bin_dir / name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
    result = bin_dir / "ffmpeg.exe"
    if not result.is_file():
        raise RuntimeError("в скачанном архиве не оказалось ffmpeg.exe")
    return str(result)


QUALITIES = [
    ("auto", "Максимум"),
    ("2160", "2160p"),
    ("1440", "1440p"),
    ("1080", "1080p"),
    ("720", "720p"),
    ("480", "480p"),
    ("360", "360p"),
]

FORMATS = {
    "mp4": {"label": "Видео · MP4", "kind": "video"},
    "src": {"label": "Видео · исходник", "kind": "video"},
    "mp3": {"label": "Аудио · MP3", "kind": "audio"},
    "m4a": {"label": "Аудио · M4A", "kind": "audio"},
    "opus": {"label": "Аудио · OPUS", "kind": "audio"},
}

SUBTITLE_LANGS = {
    "none": [],
    "ru": ["ru", "rus"],
    "en": ["en", "eng"],
    "auto": ["en", "ru", ".*"],
}

STATE_WAITING = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_CANCELLED = "cancelled"


def human_size(value):
    if not value:
        return "—"
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.0f} {unit}" if size >= 100 else f"{size:.1f} {unit}"
        size /= 1024


def human_speed(value):
    return f"{human_size(value)}/с" if value else "—"


def human_time(seconds):
    if seconds in (None, "", 0):
        return "—"
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return "—"
    if seconds < 60:
        return f"{seconds}с"
    if seconds < 3600:
        return f"{seconds // 60}м {seconds % 60:02d}с"
    return f"{seconds // 3600}ч {(seconds % 3600) // 60}м"


ERROR_HINTS = (
    ("unsupported url",
     "Площадка не распознана: ссылка не похожа на страницу видео. Возьмите ссылку прямо со страницы ролика."),
    ("this video is unavailable",
     "Видео недоступно: удалено, закрыто по региону или это закончившаяся трансляция."),
    ("no video formats",
     "Площадка не отдаёт ни одного формата — чаще всего это прямой эфир или ролик с ограничениями."),
    ("sign in to confirm",
     "Видео только для взрослых или приватное. Включите cookie браузера в настройках."),
    ("is private",
     "Видео приватное. Включите cookie браузера в настройках."),
    ("login required",
     "Площадка требует входа. Включите cookie браузера в настройках."),
    ("not available in your country",
     "Видео недоступно из вашего региона — нужен VPN."),
    ("only available",
     "Видео доступно только часть аудитории (регион, подписка или вход)."),
    ("requested format is not available",
     "Такого качества нет для этого видео. Поставьте «Максимум»."),
    ("drm",
     "Ролик защищён DRM, обычным способом он не скачивается."),
    ("ffmpeg",
     "Не найден ffmpeg — без него MP3 и склейка видео невозможны. Укажите путь к ffmpeg.exe в настройках."),
    ("403",
     "Площадка блокирует запрос с этого адреса. Подождите пару часов или включите cookie браузера в настройках."),
    ("getaddrinfo",
     "Нет интернета или адрес площадки не резолвится."),
    ("unable to download webpage",
     "Нет связи с площадкой — проверьте интернет или VPN."),
    ("timed out",
     "Площадка не отвечает — попробуйте позже."),
    ("attribute 'video'",
     "YouTube не отдаёт это видео обычным способом: это прямой эфир, премьера или ролик с ограничениями."),
    ("unable to extract",
     "Похоже, площадка поменяла сайт, а закладка yt-dlp ещё не обновлена. Помогает свежая версия: "
     "pip install -U yt-dlp, для exe — пересборка."),
    ("unable to parse",
     "Закладка yt-dlp перестала понимать ответы этой площадки — нужна свежая версия (pip install -U yt-dlp)."),
    ("failed to parse",
     "Закладка yt-dlp перестала понимать ответы этой площадки — нужна свежая версия (pip install -U yt-dlp)."),
    ("could not find",
     "yt-dlp не нашёл в странице того, что искал: скорее всего площадка изменила вёрстку или требует входа. "
     "Попробуйте включить cookie браузера, затем обновить yt-dlp."),
    ("signature",
     "Площадка поменяла защиту ссылок на потоки — это чинится только обновлением yt-dlp (pip install -U yt-dlp)."),
)

YTDLP_VERSION = yt_dlp.version.__version__


def version_tuple(text):
    """'2026.08.19' и '2026.8.19' — одна версия: PyPI не дополняет нулями."""
    return tuple(int(part) for part in re.split(r"[.\-]", text or "") if part.isdigit())


def latest_ytdlp_version(timeout=8):
    """Свежий релиз yt-dlp с PyPI или "" если не отвечает."""
    import json
    import urllib.request

    try:
        request = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": "downloadbro"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return str(json.loads(response.read())["info"]["version"])
    except Exception:
        return ""


def explain_error(raw):
    text = (raw or "").lower()
    if not text.strip():
        return "Неизвестная ошибка"
    for needle, hint in ERROR_HINTS:
        if needle in text:
            return hint
    return (raw or "")[:300]


class Job:

    def __init__(self, url, spec):
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.spec = spec
        self.title = ""
        self.platform = platform_of(url)
        self.state = STATE_WAITING
        self.phase = "В очереди"
        self.percent = 0.0
        self.speed = 0.0
        self.eta = None
        self.downloaded = 0
        self.total = 0
        self.filepath = ""
        self.error = ""
        self.created_at = time.time()
        self.finished_at = None
        self._last_publish = 0.0
        self._cancel = threading.Event()

    @property
    def format(self):
        return self.spec.get("format", "mp4")

    def cancel(self):
        self._cancel.set()

    @property
    def wants_cancel(self):
        return self._cancel.is_set()

    def check_cancel(self):
        if self._cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled()

    def snapshot(self):
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "platform": self.platform,
            "state": self.state,
            "phase": self.phase,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded": self.downloaded,
            "total": self.total,
            "filepath": self.filepath,
            "error": self.error,
            "format": self.format,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class _Logger:

    def __init__(self, engine, job):
        self._engine = engine
        self._job = job

    def debug(self, msg):
        if msg.startswith("[debug] ") or not msg.strip():
            return
        self._engine.log(self._job.id, msg)

    def info(self, msg):
        self._engine.log(self._job.id, msg)

    def warning(self, msg):
        self._engine.log(self._job.id, f"⚠ {msg}")

    def error(self, msg):
        self._engine.log(self._job.id, f"✖ {msg}")


class Engine:

    def __init__(self, publish, worker_count=2):
        self._publish = publish
        self._jobs = {}
        self._order = []
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._worker_count = max(1, int(worker_count))
        self._start_workers()

    def set_worker_count(self, count):
        count = max(1, int(count))
        if count == self._worker_count:
            return
        difference = count - self._worker_count
        self._worker_count = count
        for _ in range(abs(difference)):
            if difference > 0:
                self._spawn_worker()
            else:
                self._queue.put(None)

    def _start_workers(self):
        for _ in range(self._worker_count):
            self._spawn_worker()

    def _spawn_worker(self):
        threading.Thread(target=self._worker_loop, daemon=True).start()

    def _worker_loop(self):
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            job = self._jobs.get(job_id)
            if job is None:
                continue
            if job.wants_cancel and job.state == STATE_WAITING:
                self._finish(job, STATE_CANCELLED, "Отменено")
                continue
            self._run(job)

    def log(self, job_id, text):
        for line in str(text).splitlines():
            line = line.strip()
            if line:
                self._publish({"type": "log", "job_id": job_id, "text": line})

    def submit(self, urls, spec):
        ids = []
        for url in urls:
            job = Job(url, dict(spec))
            with self._lock:
                self._jobs[job.id] = job
                self._order.append(job.id)
            self._publish({"type": "job", "job": job.snapshot()})
            self._queue.put(job.id)
            ids.append(job.id)
        return ids

    def cancel(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.cancel()
        if job.state == STATE_WAITING:
            self._finish(job, STATE_CANCELLED, "Отменено до начала загрузки")
        else:
            self.log(job_id, "Запрошена отмена...")

    def cancel_all(self):
        for job_id in list(self._jobs):
            job = self._jobs[job_id]
            if job.state in (STATE_WAITING, STATE_RUNNING):
                self.cancel(job_id)

    def retry(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            return
        new_id = self.submit([job.url], job.spec)[0]
        self.forget(job_id)
        return new_id

    def forget(self, job_id):
        job = self._jobs.get(job_id)
        if not job or job.state == STATE_RUNNING:
            return False
        with self._lock:
            self._jobs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)
        self._publish({"type": "job_removed", "job_id": job_id})
        return True

    def clear_finished(self):
        for job_id in list(self._order):
            job = self._jobs.get(job_id)
            if job and job.state in (STATE_DONE, STATE_ERROR, STATE_CANCELLED):
                self.forget(job_id)

    def snapshots(self):
        with self._lock:
            return [self._jobs[job_id].snapshot() for job_id in self._order if job_id in self._jobs]

    def active_count(self):
        return sum(
            1
            for job in self._jobs.values()
            if job.state in (STATE_WAITING, STATE_RUNNING)
        )

    def fetch_info(self, url, spec):
        threading.Thread(
            target=self._info_task, args=(url, dict(spec)), daemon=True
        ).start()

    def _info_task(self, url, spec):
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not spec.get("playlist"),
            "skip_download": True,
            "extract_flat": False,
        }
        location = spec.get("ffmpeg_path")
        if location:
            options["ffmpeg_location"] = location
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadCancelled:
            return
        except Exception as exc:
            self._publish({"type": "info_error", "url": url, "error": str(exc)[:400]})
            return
        entry = info
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            entry = entries[0] if entries else info
            self._publish(
                {
                    "type": "info",
                    "url": url,
                    "data": {
                        "title": info.get("title") or "Плейлист",
                        "uploader": info.get("uploader") or info.get("channel") or "",
                        "platform": extractor_name(
                            info.get("extractor") or (entries[0].get("extractor") if entries else ""), url
                        ),
                        "count": len(entries),
                        "duration": sum(e.get("duration") or 0 for e in entries),
                        "thumbnail": (entries[0].get("thumbnail") if entries else None) or info.get("thumbnail"),
                        "heights": sorted(
                            {
                                e.get("height")
                                for e in (entry.get("formats") or [])
                                if e.get("height")
                            },
                            reverse=True,
                        ),
                    },
                }
            )
            return
        self._publish(
            {
                "type": "info",
                "url": url,
                "data": {
                    "title": entry.get("title") or "",
                    "uploader": entry.get("uploader") or entry.get("channel") or "",
                    "platform": extractor_name(entry.get("extractor"), url),
                    "live": bool(entry.get("is_live")),
                    "count": 1,
                    "duration": entry.get("duration") or 0,
                    "thumbnail": entry.get("thumbnail"),
                    "view_count": entry.get("view_count"),
                    "heights": sorted(
                        {
                            f.get("height")
                            for f in (entry.get("formats") or [])
                            if f.get("height") and f.get("vcodec") != "none"
                        },
                        reverse=True,
                    ),
                },
            }
        )

    def _progress(self, job, d):
        job.check_cancel()
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes") or 0
        fragments = d.get("fragment_count")
        if not total and fragments:
            index = d.get("fragment_index") or 0
            percent = (index + 1) / fragments * 100
        elif total:
            percent = min(99.5, downloaded / total * 100)
        else:
            percent = job.percent
        job.percent = percent
        job.phase = "Загрузка" if percent > 0 else job.phase
        job.downloaded = downloaded
        job.total = total
        job.speed = d.get("speed") or 0
        job.eta = d.get("eta")
        if not job.platform:
            found = extractor_name((d.get("info_dict") or {}).get("extractor"), job.url)
            if found:
                job.platform = found
        if not job.title:
            real_title = (d.get("info_dict") or {}).get("title")
            if real_title:
                job.title = real_title
            elif d.get("filename"):
                job.title = Path(d["filename"]).stem
        now = time.time()
        if now - job._last_publish > 0.12:
            job._last_publish = now
            self._publish({"type": "job", "job": job.snapshot()})

    def _postprocessor(self, job, d):
        status = d.get("status")
        if status == "started":
            job.phase = "Конвертация"
            self._publish({"type": "job", "job": job.snapshot()})
        elif status == "processing":
            detail = d.get("postprocessor") or ""
            self.log(job.id, f"Постобработка: {detail}")

    def _finished_file(self, job, info):
        try:
            if isinstance(info, dict) and info.get("title") and not job.title:
                job.title = info["title"]
            if isinstance(info, dict) and not job.platform:
                job.platform = extractor_name(info.get("extractor"), job.url)
            paths = []
            downloads = info.get("requested_downloads") or []
            if isinstance(downloads, dict):
                downloads = [downloads]
            for download in downloads:
                path = download if isinstance(download, str) else (
                    download.get("filepath") if isinstance(download, dict) else "")
                if path:
                    paths.append(path)
            if info.get("filepath"):
                paths.append(info["filepath"])
            for path in paths:
                if Path(path).exists():
                    job.filepath = path
                    return
            job.filepath = self._newest_file(job)
        except Exception as exc:
            job.filepath = self._newest_file(job) or ""
            if not job.filepath:
                self.log(job.id, f"⚠ не удалось определить имя файла: {exc}")

    @staticmethod
    def _newest_file(job):
        folder = Path(job.spec.get("directory") or os.getcwd())
        if not folder.exists():
            return ""
        candidates = [
            path for path in folder.iterdir()
            if path.is_file() and path.suffix not in (".part", ".ytdl")
            and path.stat().st_mtime >= job.created_at - 5
        ]
        if not candidates:
            return ""
        return str(max(candidates, key=lambda path: path.stat().st_mtime))

    def _finish(self, job, state, message=""):
        job.state = state
        job.phase = message or state
        job.finished_at = time.time()
        job.speed = 0
        job.eta = None
        self._publish({"type": "job", "job": job.snapshot()})

    def _run(self, job):
        if job.wants_cancel:
            self._finish(job, STATE_CANCELLED, "Отменено")
            return
        job.state = STATE_RUNNING
        job.phase = "Получаю информацию"
        self._publish({"type": "job", "job": job.snapshot()})
        options = self.build_options(job.spec)
        options["progress_hooks"] = [lambda d: self._progress(job, d)]
        options["postprocessor_hooks"] = [lambda d: self._postprocessor(job, d)]
        options["post_hooks"] = [lambda info: self._finished_file(job, info)]
        options["logger"] = _Logger(self, job)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([job.url])
            if job.state == STATE_CANCELLED:
                return
            job.percent = 100.0
            if not job.title:
                job.title = Path(job.filepath or "").stem or job.url
            self._finish(job, STATE_DONE, "Готово")
            self._publish({"type": "completed", "job": job.snapshot()})
        except yt_dlp.utils.DownloadCancelled:
            self._finish(job, STATE_CANCELLED, "Отменено")
        except yt_dlp.utils.ExtractorError as exc:
            self._fail(job, str(exc))
        except Exception as exc:
            self._fail(job, str(exc))
            self.log(job.id, "⚠ " + traceback.format_exc().replace("\n", " ")[-500:])
        finally:
            if job.state == STATE_RUNNING:
                self._finish(job, STATE_ERROR, "Остановлено")

    def _fail(self, job, raw):
        raw = (raw or "").strip()
        job.error = explain_error(raw)
        self._finish(job, STATE_ERROR, "Ошибка")
        self.log(job.id, f"✖ {raw[:400]}")

    @staticmethod
    def build_options(spec):
        target_dir = Path(spec.get("directory") or os.getcwd())
        target_dir.mkdir(parents=True, exist_ok=True)
        fmt = spec.get("format", "mp4")
        kind = FORMATS.get(fmt, FORMATS["mp4"])["kind"]
        quality = str(spec.get("quality", "auto"))

        options = {
            "outtmpl": str(target_dir / (spec.get("filename_template") or "%(title)s.%(ext)s")),
            "noplaylist": not spec.get("playlist"),
            "ignoreerrors": False,
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": int(spec.get("fragments", 8)),
            "windowsfilenames": True,
            "quiet": True,
            "noprogress": True,
        }

        if kind == "audio":
            options["format"] = "bestaudio/best"
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": str(spec.get("audio_bitrate", "320")),
            }]
        elif fmt == "src":
            options["format"] = "best"
        else:
            cap = "" if quality in ("", "auto", "none") else f"[height<=?{quality}]"
            options["format"] = (
                f"bestvideo[ext=mp4]{cap}+bestaudio[ext=m4a]/"
                f"bestvideo{cap}+bestaudio/"
                f"best{cap}/best"
            )
            options["merge_output_format"] = "mp4"

        langs = SUBTITLE_LANGS.get(spec.get("subtitles", "none"), [])
        if langs and kind == "video":
            options["writesubtitles"] = True
            options["writeautomaticsub"] = True
            options["subtitleslangs"] = langs
            options["subtitlesformat"] = "srt/best"

        location = spec.get("ffmpeg_path") or find_ffmpeg()
        if location:
            options["ffmpeg_location"] = str(Path(location).parent)
        for runtime in ("deno", "node", "bun"):
            found = shutil.which(runtime) or shutil.which(runtime + ".exe")
            if found:
                options["js_runtimes"] = {runtime: {"path": None}}
                break
        browser = (spec.get("cookies_browser") or "").strip()
        if browser:
            options["cookiesfrombrowser"] = (browser,)
        limit = str(spec.get("speed_limit", "")).strip()
        if limit:
            try:
                options["ratelimit"] = int(float(limit) * 1024 * 1024)
            except ValueError:
                pass
        return options


def check_ffmpeg(spec):
    location = spec.get("ffmpeg_path") or find_ffmpeg()
    return bool(location)
