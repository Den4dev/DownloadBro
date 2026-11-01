import io
import os
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__, theme as T
from .engine import (
    Engine, FORMATS, PLATFORMS, QUALITIES, SUPPORTED_HINT, YTDLP_VERSION, download_ffmpeg, find_ffmpeg,
    human_size, human_speed, human_time, latest_ytdlp_version, platform_of, version_tuple,
)
from .settings import data_dir, resource_path
from .widgets import (
    Caption, Card, Chip, Field, GhostButton, LogBox, Option, PrimaryButton, Switch, Tile, Tooltip, UrlBox,
    hide_tooltips,
)

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

PAGES = [
    ("download", "Скачивание", "Вставьте ссылку и выберите, что получить на выходе", "download"),
    ("queue", "Очередь", "Активные и завершённые задачи", "queue"),
    ("history", "История", "Всё, что уже лежит на диске", "history"),
    ("settings", "Настройки", "Папки, качество по умолчанию, тема оформления", "settings"),
]

MAX_LOG_LINES = 400

SUBTITLE_LABELS = {"none": "без субтитров", "ru": "русские", "en": "английские", "auto": "все доступные"}


def reveal_in_explorer(path):
    target = str(path)
    if os.path.isdir(target):
        os.startfile(target)
    elif os.path.isfile(target):
        subprocess.Popen(["explorer", "/select,", target])
    else:
        return False
    return True


class App(ctk.CTk):

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.events = queue.Queue()
        self.engine = Engine(self.events.put_nowait, settings.get("parallel_jobs"))
        ctk.set_appearance_mode(self._appearance())
        T.apply(self._mode())
        self.palette = T.Palette(settings.get("accent"))
        self.current = "download"
        self.pages = {}
        self.rows = {}
        self.log_lines = []
        self._photo = None
        self._info_data = None
        self._ffmpeg_busy = False
        self._closing = False

        self.title("DownloadBro")
        window = settings.get("window")
        width, height = self._fit(window.get("width", 1060), window.get("height", 700))
        x, y = window.get("x"), window.get("y")
        if x is None or y is None or not self._on_screen(x, y):
            x = y = None
        position = f"+{x}+{y}" if x is not None and y is not None else ""
        self.geometry(f"{width}x{height}{position}")
        self.minsize(*self._fit(880, 600))
        self.configure(fg_color=T.BG)
        icon = resource_path(os.path.join("assets", "icon.ico"))
        if icon.exists():
            try:
                self.iconbitmap(str(icon), default=str(icon))
            except tk.TclError:
                pass

        self._build_sidebar()
        self._build_content()
        self._build_statusbar()
        self._render_pages()
        self.show_page(self.current)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-l>", lambda _e: self._focus_url())
        self.bind("<Control-v>", lambda e: self._paste_clipboard(e))
        self.bind("<Control-d>", lambda _e: self.start_download())
        self.bind("<Escape>", lambda _e: self.engine.cancel_all())
        self.after(80, self._drain_events)

    def _mode(self):
        pref = self.settings.get("appearance")
        if pref in ("dark", "light"):
            return pref
        return "dark" if str(ctk.get_appearance_mode()).lower() == "dark" else "light"

    def _appearance(self):
        return self.settings.get("appearance") if self.settings.get("appearance") in ("dark", "light") else "system"

    def _scaling(self):
        try:
            return float(self._get_window_scaling()) or 1.0
        except Exception:
            return 1.0

    def _fit(self, width, height):
        # CTk умножает geometry() на DPI-масштаб, поэтому размеры берём в логических пикселях экрана
        scaling = self._scaling()
        cap_w = self.winfo_screenwidth() / scaling - 40
        cap_h = self.winfo_screenheight() / scaling - 60
        return int(min(width, cap_w)), int(min(height, cap_h))

    def _on_screen(self, x, y):
        """Свёрнутое окно Windows отдаёт координаты -32000 — их нельзя ни сохранять, ни восстанавливать."""
        if x <= -30000 or y <= -30000:
            return False
        try:
            if os.name == "nt":
                import ctypes

                user32 = ctypes.windll.user32
                left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
                top = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
                # Tk и GetSystemMetrics могут расходиться в ориентации/DPI, берём максимум
                width = max(user32.GetSystemMetrics(79), self.winfo_screenwidth())
                height = max(user32.GetSystemMetrics(78), self.winfo_screenheight())
            else:
                left = top = 0
                width, height = self.winfo_screenwidth(), self.winfo_screenheight()
        except Exception:
            return True
        return left - 40 <= x <= left + width - 100 and top - 40 <= y <= top + height - 60

    def _wrap_note(self, label):
        """Длинные подписи в карточках: перенос по фактической ширине, а не по угаданной."""
        def on_resize(event):
            if event.width > 1 and event.width != label.cget("wraplength"):
                label.configure(wraplength=event.width)

        label.bind("<Configure>", on_resize)
        return label

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=224)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=68)
        brand.pack(fill="x", padx=18, pady=(18, 6))
        brand.pack_propagate(False)
        logo = ctk.CTkLabel(
            brand,
            text=T.GLYPH["download"],
            font=T.Fonts().icon_big,
            text_color=self.palette.on_main,
            fg_color=self.palette.main,
            width=38,
            height=38,
            corner_radius=12,
        )
        logo.pack(side="left")
        texts = ctk.CTkFrame(brand, fg_color="transparent")
        texts.pack(side="left", padx=12)
        ctk.CTkLabel(texts, text="DownloadBro", font=T.Fonts().h2, text_color=T.TEXT).pack(anchor="w")
        ctk.CTkLabel(texts, text=f"1700+ площадок · v{__version__}", font=T.Fonts().tiny, text_color=T.FAINT).pack(anchor="w")
        self.logo_label = logo

        ctk.CTkFrame(self.sidebar, height=1, fg_color=T.BORDER).pack(fill="x", padx=18, pady=(8, 14))

        self.nav_items = {}
        for key, label, _desc, glyph in PAGES:
            item = ctk.CTkButton(
                self.sidebar,
                text=f"{T.GLYPH[glyph]}    {label}",
                font=T.Fonts().nav,
                fg_color="transparent",
                hover_color=T.CARD_SOFT,
                text_color=T.MUTED,
                anchor="w",
                height=40,
                corner_radius=11,
                command=lambda k=key: self.show_page(k),
            )
            item.pack(fill="x", padx=12, pady=3)
            self.nav_items[key] = item

        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        self.theme_button = GhostButton(
            self.sidebar,
            text="Светлая" if self._mode() == "dark" else "Тёмная",
            icon="sun" if self._mode() == "dark" else "moon",
            command=self.toggle_appearance, width=196,
        )
        self.theme_button.pack(side="bottom", padx=14, pady=(0, 6))
        footer = ctk.CTkLabel(
            self.sidebar, text="yt-dlp + FFmpeg", font=T.Fonts().tiny, text_color=T.FAINT
        )
        footer.pack(side="bottom", pady=(0, 12))

    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True, padx=(0, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_statusbar(self):
        self.statusbar = ctk.CTkFrame(self.content, fg_color=T.CARD, corner_radius=0, height=36)
        self.statusbar.grid(row=1, column=0, sticky="ew")
        self.statusbar.pack_propagate(False)
        self.status_dot = ctk.CTkLabel(self.statusbar, text="●", font=T.Fonts().small, text_color=T.OK)
        self.status_dot.pack(side="left", padx=(16, 6))
        self.status_text = ctk.CTkLabel(
            self.statusbar, text="Готово к работе", font=T.Fonts().small, text_color=T.MUTED
        )
        self.status_text.pack(side="left")
        self.status_right = ctk.CTkLabel(
            self.statusbar, text="", font=T.Fonts().small, text_color=T.FAINT
        )
        self.status_right.pack(side="right", padx=16)

    def _render_pages(self):
        for key, _label, _desc, _glyph in PAGES:
            frame = ctk.CTkFrame(self.content, fg_color=T.BG, corner_radius=0)
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_remove()
            self.pages[key] = frame
        self._build_download_page(self.pages["download"])
        self._build_queue_page(self.pages["queue"])
        self._build_history_page(self.pages["history"])
        self._build_settings_page(self.pages["settings"])

    def show_page(self, key):
        hide_tooltips()
        self.current = key
        for name, frame in self.pages.items():
            if name == key:
                frame.grid()
                frame.tkraise()
        for name, item in self.nav_items.items():
            active = name == key
            item.configure(
                fg_color=self.palette.glow if active else "transparent",
                text_color=T.TEXT if active else T.MUTED,
                border_width=1 if active else 0,
                border_color=T.BORDER,
            )
        _, label, desc, _ = next(p for p in PAGES if p[0] == key)
        self.status_text.configure(text=label + " — " + desc)
        if key == "history":
            self._render_history()
        if key == "queue":
            self._render_queue()

    # ------------------------------------------------------------------ helpers
    def header(self, parent, title, subtitle):
        box = ctk.CTkFrame(parent, fg_color=T.BG, corner_radius=0)
        box.pack(fill="x", padx=26, pady=(24, 10))
        ctk.CTkLabel(box, text=title, font=T.Fonts().h1, text_color=T.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(box, text=subtitle, font=T.Fonts().body, text_color=T.MUTED, anchor="w").pack(
            anchor="w", pady=(3, 0)
        )
        return box

    # --------------------------------------------------------------- download page
    def _build_download_page(self, page):
        self.header(page, "Скачать с любой площадки", "YouTube, Rutube, VK и другие · формат, качество — и в очередь")
        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(2, 6))
        self.download_body = body

        url_card = Card(body)
        url_card.pack(fill="x", pady=(0, 14))
        self.url_card = url_card
        inner = url_card.inner
        Caption(inner, "ссылка на видео").pack(fill="x")
        ctk.CTkFrame(inner, height=8, fg_color="transparent").pack()
        self.url_box = UrlBox(inner, height=78)
        self.url_box.pack(fill="x")
        self.url_box.bind_text("<KeyRelease>", lambda _e: self._update_platform_hint())
        self.platform_label = ctk.CTkLabel(inner, text="", font=T.Fonts().tiny, text_color=T.FAINT, anchor="w")
        self.platform_label.pack(fill="x", pady=(6, 0))
        self._update_platform_hint()
        ctk.CTkFrame(inner, height=6, fg_color="transparent").pack()

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(fill="x")
        GhostButton(actions, text="Вставить", icon="paste", command=self._paste_clipboard, palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(actions, text="Уточнить данные", icon="info", command=self._fetch_info, palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(actions, text="Очистить", icon="close", command=self._clear_url, palette=self.palette).pack(side="left")
        self.hint_label = ctk.CTkLabel(
            actions, text="Ctrl+V — вставить, Ctrl+D — скачать", font=T.Fonts().tiny, text_color=T.FAINT
        )
        self.hint_label.pack(side="right")

        sites_card = Card(body, "Площадки")
        sites_card.pack(fill="x", pady=(0, 14))
        chips = ctk.CTkFrame(sites_card.inner, fg_color="transparent")
        chips.pack(fill="x")
        per_row = 6
        for column in range(per_row):
            chips.grid_columnconfigure(column, weight=1)
        for index, (name, *domains) in enumerate(PLATFORMS):
            site = f"https://{domains[0]}"
            chip = Chip(chips, name, palette=self.palette, command=lambda s=site: webbrowser.open(s))
            chip.grid(row=index // per_row, column=index % per_row, sticky="w", padx=(0, 6), pady=3)
            Tooltip(chip, f"открыть {site}")
        ctk.CTkFrame(sites_card.inner, height=10, fg_color="transparent").pack()
        self._wrap_note(ctk.CTkLabel(
            sites_card.inner,
            text="Клик по площадке открывает её сайт. Список не ограничивает: вставляйте ссылку с любого "
                 "из 1700+ сайтов, которые понимает yt-dlp, — неизвестная площадка берётся общим экстрактором.",
            font=T.Fonts().small, text_color=T.MUTED, anchor="w", justify="left", wraplength=700,
        )).pack(fill="x")
        ctk.CTkFrame(sites_card.inner, height=10, fg_color="transparent").pack()
        version_row = ctk.CTkFrame(sites_card.inner, fg_color="transparent")
        version_row.pack(fill="x")
        ctk.CTkLabel(version_row, text=f"движок: yt-dlp {YTDLP_VERSION}", font=T.Fonts().tiny,
                     text_color=T.FAINT).pack(side="left")
        self.ytdlp_state = ctk.CTkLabel(version_row, text="", font=T.Fonts().tiny, text_color=T.MUTED)
        self.ytdlp_state.pack(side="right", padx=(10, 0))
        GhostButton(version_row, text="Проверить обновление", icon="retry",
                    command=self._check_ytdlp, palette=self.palette).pack(side="right")

        self.preview = Card(body)
        self.preview_row = self.preview.inner
        self.thumb_holder = ctk.CTkFrame(
            self.preview_row, width=132, height=74, corner_radius=10, fg_color=T.CARD_SOFT
        )
        self.thumb_holder.pack(side="left", padx=(0, 14))
        self.thumb_holder.pack_propagate(False)
        # tk.Label, а не CTkLabel: у CTkLabel нет способа снять картинку (configure(image=None) её не убирает)
        self.thumb_label = tk.Label(
            self.thumb_holder, text=T.GLYPH["film"], font=T.FONTS.icon_big,
            fg=T.MUTED, bg=T.CARD_SOFT, bd=0, highlightthickness=0,
        )
        self.thumb_label.pack(fill="both", expand=True)
        preview_text = ctk.CTkFrame(self.preview_row, fg_color="transparent")
        preview_text.pack(side="left", fill="x", expand=True)
        self.preview_title = ctk.CTkLabel(preview_text, text="—", font=T.Fonts().h3, text_color=T.TEXT, anchor="w", wraplength=520, justify="left")
        self.preview_title.pack(anchor="w")
        self.preview_meta = ctk.CTkLabel(preview_text, text="", font=T.Fonts().small, text_color=T.MUTED, anchor="w")
        self.preview_meta.pack(anchor="w", pady=(3, 0))
        self.preview.pack_forget()

        fmt_card = Card(body, "Формат результата")
        fmt_card.pack(fill="x", pady=(0, 14))
        tiles = ctk.CTkFrame(fmt_card.inner, fg_color="transparent")
        tiles.pack(fill="x")
        tiles.grid_columnconfigure(tuple(range(3)), weight=1, uniform="tiles")
        tiles.grid_rowconfigure(tuple(range(2)), weight=1)
        self.tiles = {}
        tile_specs = [
            ("mp4", "film", "Видео MP4", "склейка + H.264"),
            ("src", "download", "Исходник", "без пережатия"),
            ("mp3", "music", "Аудио MP3", "только звук"),
            ("m4a", "music", "Аудио M4A", "AAC без пережатия"),
            ("opus", "music", "Аудио OPUS", "максимальное сжатие"),
        ]
        for i, (key, icon, title, subtitle) in enumerate(tile_specs):
            tile = Tile(
                tiles, icon, title, subtitle, self.palette,
                command=lambda k=key: self._choose_format(k),
                width=170, height=74,
            )
            tile.grid(row=i // 3, column=i % 3, sticky="nsew", padx=5, pady=5)
            self.tiles[key] = tile
        ctk.CTkFrame(fmt_card.inner, height=10, fg_color="transparent").pack()

        opts = ctk.CTkFrame(fmt_card.inner, fg_color="transparent")
        opts.pack(fill="x")
        opts.grid_columnconfigure(1, weight=1)

        def chip_row(index, caption_text, values, make_command, labels=None):
            Caption(opts, caption_text).grid(row=index, column=0, sticky="w", pady=6, padx=(0, 14))
            holder = ctk.CTkFrame(opts, fg_color="transparent")
            holder.grid(row=index, column=1, sticky="w")
            chips = {}
            for i, value in enumerate(values):
                label = (labels or {}).get(value, str(value))
                chip = Chip(holder, label, palette=self.palette, command=make_command(value))
                chip.grid(row=0, column=i, padx=(0, 6))
                chips[value] = chip
            return chips

        self.quality_chips = chip_row(
            0, "качество видео", [value for value, _ in QUALITIES],
            lambda value: (lambda: self._choose_quality(value)), dict(QUALITIES),
        )
        self.bitrate_chips = chip_row(
            1, "битрейт аудио", ("320", "192", "128"),
            lambda value: (lambda: self._choose_bitrate(value)),
            {value: value + " kbps" for value in ("320", "192", "128")},
        )

        third = ctk.CTkFrame(opts, fg_color="transparent")
        third.grid(row=2, column=1, sticky="w", pady=6)
        self.playlist_switch = Switch(third, "Весь плейлист", self.palette, command=self._save_choice)
        self.playlist_switch.pack(side="left", padx=(0, 18))
        ctk.CTkLabel(third, text="Субтитры", font=T.Fonts().small, text_color=T.MUTED).pack(side="left", padx=(0, 6))
        self.sub_option = Option(
            third, ["без субтитров", "русские", "английские", "все доступные"],
            command=lambda _v: self._save_choice(), palette=self.palette, width=170,
        )
        self.sub_option.pack(side="left")
        Caption(opts, "дополнительно").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 14))

        folder_card = Card(body, "Куда сохранять")
        folder_card.pack(fill="x", pady=(0, 14))
        row = ctk.CTkFrame(folder_card.inner, fg_color="transparent")
        row.pack(fill="x")
        self.folder_label = ctk.CTkLabel(
            row, text=self.settings.get("download_dir"), font=T.Fonts().mono, text_color=T.MUTED, anchor="w"
        )
        self.folder_label.pack(side="left", fill="x", expand=True, padx=(0, 12))
        GhostButton(row, text="Открыть", icon="folder", command=self._open_folder, palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(row, text="Изменить", icon="settings", command=self._choose_folder, palette=self.palette).pack(side="left")

        go_card = Card(body)
        go_card.pack(fill="x", pady=(0, 14))
        go = go_card.inner
        buttons = ctk.CTkFrame(go, fg_color="transparent")
        buttons.pack(fill="x")
        self.download_button = PrimaryButton(
            buttons, f"  {T.GLYPH['download']}   Скачать", self.palette,
            command=self.start_download, height=46, width=210, font=T.Fonts().cta,
        )
        self.download_button.pack(side="left")
        self.cancel_button = GhostButton(buttons, text="Отменить всё", icon="stop", command=self.engine.cancel_all, palette=self.palette)
        self.cancel_button.pack(side="left", padx=10)

        ctk.CTkFrame(go, height=14, fg_color="transparent").pack()
        metrics = ctk.CTkFrame(go, fg_color="transparent")
        metrics.pack(fill="x")
        self.percent_label = ctk.CTkLabel(metrics, text="0%", font=T.Fonts().metric, text_color=self.palette.main)
        self.percent_label.pack(side="left")
        self.progress_caption = ctk.CTkLabel(metrics, text="ожидание", font=T.Fonts().small, text_color=T.MUTED)
        self.progress_caption.place(relx=0.5, rely=0.5, anchor="center")
        self.detail_label = ctk.CTkLabel(metrics, text="—", font=T.Fonts().small, text_color=T.FAINT)
        self.detail_label.pack(side="right")
        ctk.CTkFrame(go, height=10, fg_color="transparent").pack()
        self.progress = ctk.CTkProgressBar(go, progress_color=self.palette.main, fg_color=T.BORDER, height=12, corner_radius=6)
        self.progress.set(0)
        self.progress.pack(fill="x")

        log_card = Card(body, "Журнал")
        log_card.pack(fill="x", pady=(0, 18))
        self.log_box = LogBox(log_card.inner, height=170)
        self.log_box.pack(fill="x")
        for line, color in self.log_lines[-80:]:
            self.log_box.write(line, color)
        GhostButton(
            log_card.inner, text="Очистить журнал", icon="trash", command=self._clear_log, palette=self.palette
        ).pack(anchor="e", pady=(8, 0))

        self._sync_controls()

    # --------------------------------------------------------------------- queue
    def _build_queue_page(self, page):
        self.header(page, "Очередь", "Каждая ссылка — отдельная задача")
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", padx=28, pady=(0, 8))
        self.queue_stats = ctk.CTkLabel(bar, text="нет активных задач", font=T.Fonts().body, text_color=T.MUTED)
        self.queue_stats.pack(side="left")
        GhostButton(bar, text="Отменить всё", icon="stop", command=self.engine.cancel_all, palette=self.palette).pack(side="right", padx=(8, 0))
        GhostButton(bar, text="Убрать завершённые", icon="close", command=self.engine.clear_finished, palette=self.palette).pack(side="right")
        self.queue_body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.queue_body.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    def _render_queue(self):
        for row in self.rows.values():
            row.destroy()
        self.rows = {}
        snapshots = list(reversed(self.engine.snapshots()))
        if not snapshots:
            empty = ctk.CTkLabel(self.queue_body, text="Пока пусто. Отправьте ссылку на странице «Скачивание».", font=T.Fonts().body, text_color=T.FAINT)
            empty.pack(pady=40)
            self.rows["__empty__"] = {"card": empty}
        for snap in snapshots:
            self._add_row(snap)
        self._update_queue_stats()

    def _add_row(self, snap):
        row = Card(self.queue_body, padding=14)
        row.pack(fill="x", pady=(0, 10))
        top = ctk.CTkFrame(row.inner, fg_color="transparent")
        top.pack(fill="x")
        title = ctk.CTkLabel(top, text=snap["title"] or snap["url"], font=T.Fonts().h3, text_color=T.TEXT, anchor="w")
        title.pack(side="left", fill="x", expand=True, padx=(0, 12))
        badge = ctk.CTkLabel(top, text="", font=T.Fonts().tiny, text_color=T.FAINT,
                             fg_color=T.CARD_SOFT, corner_radius=8, padx=9, pady=4)
        badge.pack(side="right")
        ctk.CTkFrame(row.inner, height=8, fg_color="transparent").pack()
        bar = ctk.CTkProgressBar(row.inner, progress_color=self.palette.main, fg_color=T.BORDER, height=8, corner_radius=4)
        bar.pack(fill="x")
        ctk.CTkFrame(row.inner, height=8, fg_color="transparent").pack()
        bottom = ctk.CTkFrame(row.inner, fg_color="transparent")
        bottom.pack(fill="x")
        meta = ctk.CTkLabel(bottom, text="", font=T.Fonts().tiny, text_color=T.MUTED, anchor="w")
        meta.pack(side="left", fill="x", expand=True)
        buttons = ctk.CTkFrame(bottom, fg_color="transparent")
        buttons.pack(side="right")

        widgets = {"card": row, "title": title, "badge": badge, "bar": bar, "meta": meta, "buttons": buttons}
        self.rows[snap["id"]] = widgets
        self._update_row(snap)
        return widgets

    def _row_meta(self, snap):
        bits = []
        if snap.get("platform"):
            bits.append(snap["platform"])
        bits += [snap["phase"], f"формат: {snap['format'].upper()}"]
        if snap["state"] == "running":
            bits += [f"скорость: {human_speed(snap['speed'])}", f"осталось: {human_time(snap['eta'])}",
                     f"{human_size(snap['downloaded'])} / {human_size(snap['total'])}"]
        if snap["error"]:
            bits.append(snap["error"][:120])
        return "   ·   ".join(bits)

    def _state_text(self, snap):
        return {"queued": "в очереди", "running": f"{snap['percent']:.0f}%", "done": "готово",
                "error": "ошибка", "cancelled": "отменено"}.get(snap["state"], snap["state"])

    def _update_row(self, snap):
        widgets = self.rows.get(snap["id"])
        if widgets is None:
            self._drop_empty_placeholder()
            self._add_row(snap)
            return
        state = snap["state"]
        color = {"done": T.OK, "error": T.ERROR, "cancelled": T.WARN}.get(state, self.palette.main)
        widgets["title"].configure(text=snap["title"] or snap["url"])
        widgets["badge"].configure(text=self._state_text(snap), text_color=color)
        widgets["bar"].set(min(1.0, snap["percent"] / 100))
        widgets["meta"].configure(text=self._row_meta(snap))
        for child in widgets["buttons"].winfo_children():
            child.destroy()
        buttons = widgets["buttons"]
        if state in ("queued", "running"):
            GhostButton(buttons, icon="stop", command=lambda i=snap["id"]: self.engine.cancel(i), width=38).pack(side="left", padx=(4, 0))
        else:
            GhostButton(buttons, icon="retry", command=lambda i=snap["id"]: self.engine.retry(i), width=38).pack(side="left", padx=(4, 0))
            if snap["filepath"]:
                GhostButton(buttons, icon="folder", command=lambda p=snap["filepath"]: reveal_in_explorer(p), width=38).pack(side="left", padx=(4, 0))
        GhostButton(buttons, icon="close", command=lambda i=snap["id"]: self._forget(i), width=38).pack(side="left", padx=(4, 0))

    def _drop_empty_placeholder(self):
        placeholder = self.rows.pop("__empty__", None)
        if placeholder:
            placeholder["card"].destroy()

    def _forget(self, job_id):
        if self.engine.forget(job_id):
            self._render_queue()

    def _update_queue_stats(self):
        snapshots = self.engine.snapshots()
        active = [s for s in snapshots if s["state"] in ("queued", "running")]
        done = [s for s in snapshots if s["state"] == "done"]
        failed = [s for s in snapshots if s["state"] in ("error", "cancelled")]
        self.queue_stats.configure(
            text=f"активных: {len(active)}   ·   готово: {len(done)}   ·   остановлено: {len(failed)}"
        )

    # ------------------------------------------------------------------- history
    def _build_history_page(self, page):
        self.header(page, "История", "Скачанное можно открыть или добавить снова")
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", padx=28, pady=(0, 8))
        self.history_stats = ctk.CTkLabel(bar, text="", font=T.Fonts().body, text_color=T.MUTED)
        self.history_stats.pack(side="left")
        GhostButton(bar, text="Очистить историю", icon="trash", command=self._clear_history, palette=self.palette).pack(side="right", padx=(8, 0))
        GhostButton(bar, text="Папка загрузок", icon="folder", command=self._open_folder, palette=self.palette).pack(side="right")
        self.history_body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self.history_body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._render_history()

    def _render_history(self):
        for child in self.history_body.winfo_children():
            child.destroy()
        history = self.settings.history
        self.history_stats.configure(text=f"записей: {len(history)}")
        if not history:
            ctk.CTkLabel(self.history_body, text="История пуста.", font=T.Fonts().body, text_color=T.FAINT).pack(pady=40)
            return
        for entry in history:
            row = Card(self.history_body, padding=12)
            row.pack(fill="x", pady=(0, 8))
            top = ctk.CTkFrame(row.inner, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=entry.get("title") or entry.get("url"), font=T.Fonts().h3,
                         text_color=T.TEXT, anchor="w").pack(side="left", fill="x", expand=True)
            buttons = ctk.CTkFrame(top, fg_color="transparent")
            buttons.pack(side="right")
            path = entry.get("filepath", "")
            if path:
                GhostButton(buttons, icon="folder", command=lambda p=path: reveal_in_explorer(p), width=38).pack(side="left", padx=4)
            GhostButton(buttons, icon="link", command=lambda u=entry.get("url", ""): self._reuse(u), width=38).pack(side="left", padx=4)
            GhostButton(buttons, icon="close", command=lambda u=entry.get("url"): self._drop_history(u), width=38).pack(side="left", padx=4)
            meta = time.strftime("%d.%m.%Y %H:%M", time.localtime(entry.get("added_at", 0)))
            platform = entry.get("platform") or platform_of(entry.get("url") or "")
            if platform:
                meta += f"   ·   {platform}"
            meta += f"   ·   {(entry.get('format') or '').upper()}"
            if path:
                size = Path(path).stat().st_size if Path(path).exists() else 0
                meta += f"   ·   {human_size(size) if size else 'файл перемещён'}"
            ctk.CTkLabel(row.inner, text=meta, font=T.Fonts().tiny, text_color=T.MUTED, anchor="w").pack(fill="x", pady=(6, 0))

    def _reuse(self, url):
        self.show_page("download")
        self._clear_url()
        self.url_box.set_text(url)
        self._update_platform_hint()

    def _drop_history(self, url):
        self.settings.remove_history(url)
        self._render_history()

    def _clear_history(self):
        self.settings.clear_history()
        self._render_history()

    # ------------------------------------------------------------------ settings
    def _build_settings_page(self, page):
        self.header(page, "Настройки", "Изменения сохраняются сразу")
        body = ctk.CTkScrollableFrame(page, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(2, 10))

        theme_card = Card(body, "Оформление")
        theme_card.pack(fill="x", pady=(0, 14))
        row = ctk.CTkFrame(theme_card.inner, fg_color="transparent")
        row.pack(fill="x")
        Caption(row, "тема").pack(side="left", padx=(0, 12))
        self.theme_chips = {}
        for value, label in (("system", "системная"), ("dark", "тёмная"), ("light", "светлая")):
            chip = Chip(row, label, palette=self.palette, command=lambda v=value: self._set_appearance(v))
            chip.pack(side="left", padx=(0, 6))
            self.theme_chips[value] = chip
        ctk.CTkFrame(row, height=12, fg_color="transparent").pack()
        accents = ctk.CTkFrame(row, fg_color="transparent")
        accents.pack(fill="x", pady=(4, 0))
        Caption(accents, "акцент").pack(side="left", padx=(0, 12))
        for name in T.ACCENTS:
            color = T.ACCENTS[name][0]
            swatch = ctk.CTkButton(
                accents, text="", width=30, height=30, corner_radius=15, fg_color=color,
                hover_color=color, command=lambda n=name: self._set_accent(n),
            )
            swatch.pack(side="left", padx=4)
            Tooltip(swatch, name)

        dl_card = Card(body, "Загрузки")
        dl_card.pack(fill="x", pady=(0, 14))
        grid = ctk.CTkFrame(dl_card.inner, fg_color="transparent")
        grid.pack(fill="x")
        for column in range(2):
            grid.grid_columnconfigure(column, weight=1)

        def field_row(caption, widget_factory, row_index):
            box = ctk.CTkFrame(grid, fg_color="transparent")
            box.grid(row=row_index, column=0, sticky="w", pady=8, padx=(0, 24))
            Caption(box, caption).pack(anchor="w")
            ctk.CTkFrame(box, height=6, fg_color="transparent").pack()
            widget = widget_factory(box)
            widget.pack(anchor="w")
            return widget

        self.dir_field = field_row("папка сохранения", lambda p: Field(p, width=330, height=36), 0)
        self.dir_field.insert("end", self.settings.get("download_dir"))
        self.dir_field.bind("<FocusOut>", lambda _e: self._save_dir_field())
        GhostButton(grid, text="Выбрать", icon="folder", command=self._choose_folder, width=110).grid(row=0, column=1, sticky="w", pady=22)

        self.template_field = field_row("имя файла", lambda p: Field(p, width=330, height=36), 1)
        self.template_field.insert("end", self.settings.get("filename_template"))
        self.template_field.bind("<FocusOut>", lambda _e: self._save_template_field())
        Tooltip(self.template_field, "%(title)s.%(ext)s — шаблон yt-dlp")

        self.parallel_option = field_row(
            "одновременно задач",
            lambda p: Option(p, [str(i) for i in range(1, 7)], command=lambda v: self.settings.set("parallel_jobs", int(v)), palette=self.palette, width=110),
            2,
        )
        self.parallel_option.set(str(self.settings.get("parallel_jobs")))
        self.engine.set_worker_count(self.settings.get("parallel_jobs"))

        self.fragments_option = field_row(
            "фрагментов на поток",
            lambda p: Option(p, [str(i) for i in (1, 2, 4, 8, 12, 16, 24)], command=lambda v: self.settings.set("fragments", int(v)), palette=self.palette, width=110),
            3,
        )
        self.fragments_option.set(str(self.settings.get("fragments")))

        self.limit_field = field_row("лимит скорости, МБ/с", lambda p: Field(p, width=110, height=36, placeholder_text="без лимита"), 4)
        self.limit_field.insert("end", self.settings.get("speed_limit") or "")
        self.limit_field.bind("<FocusOut>", lambda _e: self.settings.set("speed_limit", self.limit_field.get().strip()))

        self.cookies_option = field_row(
            "файлы cookie браузера",
            lambda p: Option(p, ["не использовать", "chrome", "edge", "firefox", "brave", "opera", "safari"], command=self._save_cookies, palette=self.palette, width=170),
            5,
        )
        current = self.settings.get("cookies_browser") or ""
        self.cookies_option.set(current if current in ("chrome", "edge", "firefox", "brave", "opera", "safari") else "не использовать")

        ff_card = Card(body, "FFmpeg")
        ff_card.pack(fill="x", pady=(0, 14))
        ff_row = ctk.CTkFrame(ff_card.inner, fg_color="transparent")
        ff_row.pack(fill="x")
        self.ffmpeg_field = Field(ff_row, width=420, height=36, placeholder_text="путь к ffmpeg.exe (пусто = искать автоматически)")
        self.ffmpeg_field.insert("end", self.settings.get("ffmpeg_path") or "")
        self.ffmpeg_field.bind("<FocusOut>", lambda _e: self.settings.set("ffmpeg_path", self.ffmpeg_field.get().strip()))
        self.ffmpeg_field.pack(side="left")
        GhostButton(ff_row, text="Обзор", icon="folder", command=self._choose_ffmpeg, width=110).pack(side="left", padx=10)
        self.ffmpeg_button = GhostButton(ff_row, text="Скачать", icon="download", command=self._download_ffmpeg, width=120)
        self.ffmpeg_button.pack(side="left")
        self.ffmpeg_state = ctk.CTkLabel(ff_card.inner, text="", font=T.Fonts().small, text_color=T.MUTED, anchor="w")
        self.ffmpeg_state.pack(fill="x", pady=(8, 0))
        self._wrap_note(ctk.CTkLabel(
            ff_card.inner,
            text="«Скачать» берёт официальную сборку с gyan.dev (~90 МБ) в %LOCALAPPDATA%\\DownloadBro — "
                 "нужна один раз, дальше приложение находит её само.",
            font=T.Fonts().tiny, text_color=T.FAINT, anchor="w", justify="left", wraplength=700,
        )).pack(fill="x")
        self._check_ffmpeg()

        about_card = Card(body, "Разное")
        about_card.pack(fill="x", pady=(0, 18))
        actions = ctk.CTkFrame(about_card.inner, fg_color="transparent")
        actions.pack(fill="x")
        self.confirm_switch = Switch(actions, "Спрашивать при закрытии с активными задачами", self.palette,
                                     command=lambda: self.settings.set("confirm_close", bool(self.confirm_switch.get())))
        if self.settings.get("confirm_close"):
            self.confirm_switch.select()
        self.confirm_switch.pack(anchor="w", pady=(0, 12))
        GhostButton(actions, text="Папка настроек", icon="settings", command=lambda: reveal_in_explorer(data_dir()), palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(actions, text="Как пользоваться", icon="info", command=lambda: webbrowser.open("https://github.com/yt-dlp/yt-dlp/wiki"), palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(actions, text="Список площадок", icon="link", command=lambda: webbrowser.open(
            "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"), palette=self.palette).pack(side="left", padx=(0, 8))
        GhostButton(actions, text="Сбросить всё", icon="trash", command=self._reset_settings, palette=self.palette).pack(side="left")
        ctk.CTkFrame(about_card.inner, height=12, fg_color="transparent").pack()
        self._wrap_note(ctk.CTkLabel(
            about_card.inner,
            text=f"Узнаваемые площадки: {SUPPORTED_HINT} и сотни других. "
                 "Приватное и возрастное видео берётся через cookie браузера выше.",
            font=T.Fonts().small, text_color=T.MUTED, anchor="w", justify="left", wraplength=700,
        )).pack(fill="x")

    # ----------------------------------------------------------------- behaviour
    def _choose_format(self, key):
        self.settings.set("format", key)
        self._sync_controls()

    def _choose_quality(self, value):
        self.settings.set("quality", value)
        self._sync_controls()

    def _choose_bitrate(self, value):
        self.settings.set("audio_bitrate", value)
        self._sync_controls()

    def _save_choice(self):
        self.settings.set("playlist", bool(self.playlist_switch.get()))
        value = self.sub_option.get()
        key = next((k for k, label in SUBTITLE_LABELS.items() if label == value), "none")
        self.settings.set("subtitles", key)
        self._sync_controls()

    def _sync_controls(self):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            self._sync_controls_body()
        finally:
            self._syncing = False

    def _sync_controls_body(self):
        fmt = self.settings.get("format")
        kind = FORMATS.get(fmt, FORMATS["mp4"])["kind"]
        for key, tile in self.tiles.items():
            tile.set_selected(key == fmt)
        for value, chip in self.quality_chips.items():
            chip.set_selected(value == self.settings.get("quality") and kind == "video")
            chip.configure(state="normal" if kind == "video" else "disabled")
        for value, chip in self.bitrate_chips.items():
            chip.set_selected(value == self.settings.get("audio_bitrate"))
            chip.configure(state="normal" if kind == "audio" else "disabled")
        if bool(self.settings.get("playlist")) != bool(self.playlist_switch.get()):
            self.playlist_switch.select() if self.settings.get("playlist") else self.playlist_switch.deselect()
        wanted = SUBTITLE_LABELS.get(self.settings.get("subtitles", "none"))
        if self.sub_option.get() != wanted:
            self.sub_option.set(wanted)

    def _clear_url(self):
        self.url_box.set_text("")
        self.url_box.show_hint(force=True)
        self.preview.pack_forget()
        self._info_data = None
        self._update_platform_hint()

    def _show_preview_card(self):
        if self.preview.winfo_manager():
            return
        try:
            self.preview.pack(fill="x", pady=(0, 14), after=self.url_card)
        except tk.TclError:
            self.preview.pack(fill="x", pady=(0, 14))

    def _update_platform_hint(self):
        label = getattr(self, "platform_label", None)
        if label is None:
            return
        urls = self._urls_from_input()
        if not urls:
            label.configure(
                text=f"поддерживаются {SUPPORTED_HINT} и сотни других сайтов", text_color=T.FAINT
            )
            return
        names = []
        for url in urls:
            name = platform_of(url) or "другая площадка"
            if name not in names:
                names.append(name)
        text = "площадка: " + ", ".join(names)
        if len(urls) > 1:
            text += f"   ·   ссылок: {len(urls)}"
        if "другая площадка" in names:
            text += "   ·   yt-dlp попробует общий extractor"
        label.configure(text=text, text_color=T.MUTED if names == ["другая площадка"] else T.OK)

    def _paste_clipboard(self, event=None):
        if event is not None and self._focus_is_text_input():
            return  # поле ввода само вставит из буфера
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        text = text.strip()
        if not text:
            return
        self.url_box.hide_hint()
        if self.url_box.get_text():
            text = "\n" + text
        self.url_box.insert("end", text)
        self.url_box.focus_text()
        self._set_status("Вставлено из буфера обмена", T.OK)
        self._update_platform_hint()

    def _focus_is_text_input(self):
        focus = self.focus_get()
        while focus is not None:
            if focus.winfo_class() in ("Text", "Entry", "TEntry", "TCombobox"):
                return True
            focus = getattr(focus, "master", None)
        return False

    def _focus_url(self):
        self.show_page("download")
        try:
            self.url_box.focus_text()
        except tk.TclError:
            pass

    def _urls_from_input(self):
        urls = []
        for token in re.split(r"[\s,]+", self.url_box.get_text()):
            token = token.strip("<>\"'()[]").rstrip("/;.")
            if not token or token in urls:
                continue
            if not re.match(r"^[a-z][a-z0-9+.-]*://", token, re.I):
                if not re.match(r"^(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?/\S+$", token, re.I):
                    continue
                token = f"https://{token}"
            urls.append(token)
        return urls

    def _current_spec(self):
        return {
            "format": self.settings.get("format"),
            "quality": self.settings.get("quality"),
            "audio_bitrate": self.settings.get("audio_bitrate"),
            "playlist": self.settings.get("playlist"),
            "subtitles": self.settings.get("subtitles"),
            "directory": self.settings.get("download_dir"),
            "filename_template": self.settings.get("filename_template"),
            "fragments": self.settings.get("fragments"),
            "speed_limit": self.settings.get("speed_limit"),
            "cookies_browser": self.settings.get("cookies_browser"),
            "ffmpeg_path": self.settings.get("ffmpeg_path"),
        }

    def start_download(self):
        urls = self._urls_from_input()
        if not urls:
            self._set_status("Нужно вставить хотя бы одну ссылку", T.WARN)
            self._focus_url()
            return
        spec = self._current_spec()
        self.engine.submit(urls, spec)
        self.show_page("queue")
        self._set_status(f"В очередь добавлено: {len(urls)}", self.palette.main)
        self._log(f"→ задача принята ({len(urls)}), формат {spec['format'].upper()}", T.MUTED)

    def _check_ytdlp(self):
        if hasattr(self, "ytdlp_state"):
            self.ytdlp_state.configure(text="проверяю PyPI...", text_color=T.MUTED)
        threading.Thread(target=self._ytdlp_update_task, daemon=True).start()

    def _ytdlp_update_task(self):
        self.events.put({"type": "ytdlp_update", "latest": latest_ytdlp_version()})

    def _fetch_info(self):
        urls = self._urls_from_input()
        if not urls:
            self._set_status("Сначала вставьте ссылку", T.WARN)
            return
        self._info_data = None
        self._show_preview_card()
        self.thumb_label.configure(image="", text=T.GLYPH["film"])
        self.preview_title.configure(text="Читаю метаданные...")
        self.preview_meta.configure(text=urls[0])
        self.engine.fetch_info(urls[0], self._current_spec())

    # ------------------------------------------------------------------- events
    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_event(event)
            except Exception as exc:
                self._set_status(f"Ошибка отрисовки: {exc}", T.ERROR)
        self.after(70, self._drain_events)

    def _handle_event(self, event):
        kind = event.get("type")
        if kind == "job":
            snap = event["job"]
            if snap["state"] == "running":
                self.progress.set(min(1.0, snap["percent"] / 100))
                self.percent_label.configure(text=f"{snap['percent']:.0f}%")
                self.progress_caption.configure(text=snap["phase"])
                self.detail_label.configure(
                    text=f"{human_size(snap['downloaded'])} / {human_size(snap['total'])}   ·   "
                         f"{human_speed(snap['speed'])}   ·   осталось {human_time(snap['eta'])}"
                )
                self._set_status(f"Загрузка: {snap['title'] or snap['url'][:60]}", self.palette.main)
            elif snap["state"] == "done":
                self.progress.set(1)
                self.percent_label.configure(text="100%")
                self.progress_caption.configure(text="готово")
                self._set_status("Файл сохранён", T.OK)
            elif snap["state"] in ("error", "cancelled"):
                self.progress_caption.configure(text=snap["phase"])
                self._set_status(snap["error"] or snap["phase"], T.ERROR if snap["state"] == "error" else T.WARN)
            self.status_right.configure(text=f"активных задач: {self.engine.active_count()}")
            if self.current == "queue":
                self._update_row(snap)
            self._update_queue_stats()
        elif kind == "log":
            text = event["text"]
            color = T.TEXT if text.startswith("✖") else T.WARN if text.startswith("⚠") else None
            self._log(text, color)
        elif kind == "completed":
            snap = event["job"]
            self.settings.add_history({
                "url": snap["url"],
                "title": snap["title"] or Path(snap["filepath"]).name,
                "filepath": snap["filepath"],
                "format": snap["format"],
                "platform": snap.get("platform") or platform_of(snap["url"]),
            })
            self._log(f"✔ сохранено: {snap['filepath']}", T.OK)
        elif kind == "job_removed":
            if self.current == "queue":
                self._render_queue()
        elif kind == "info":
            self._show_preview(event["data"])
        elif kind == "thumb":
            self._show_thumbnail(event["url"], event["data"])
        elif kind == "info_error":
            self.preview_title.configure(text="Не удалось прочитать ссылку")
            self.preview_meta.configure(text=event["error"][:180])
            self._log("✖ " + event["error"], T.ERROR)
        elif kind == "ytdlp_update":
            self._report_ytdlp(event["latest"])
        elif kind == "ffmpeg_progress":
            done, total = event["done"], event["total"]
            text = human_size(done) if not total else (
                f"{human_size(done)} / {human_size(total)} · {done / total * 100:.0f}%")
            self.ffmpeg_state.configure(text=text, text_color=T.MUTED)
        elif kind == "ffmpeg":
            self._ffmpeg_busy = False
            self.ffmpeg_button.configure(state="normal", text=f"{T.GLYPH['download']}  Скачать")
            if event.get("path"):
                self._ffmpeg_ready(event["path"])
                self._log("ffmpeg установлен", T.OK)
            else:
                reason = event.get("error", "")[:150]
                self.ffmpeg_state.configure(text=f"не вышло: {reason}", text_color=T.ERROR)
                self._log(f"✖ докачка ffmpeg: {reason}", T.ERROR)

    def _report_ytdlp(self, latest):
        label = getattr(self, "ytdlp_state", None)
        if not latest:
            if label is not None:
                label.configure(text="PyPI не отвечает", text_color=T.WARN)
            return
        if version_tuple(latest) <= version_tuple(YTDLP_VERSION):
            if label is not None:
                label.configure(text=f"{YTDLP_VERSION} — свежая", text_color=T.OK)
            return
        if label is not None:
            label.configure(text=f"вышла {latest}, встроена {YTDLP_VERSION}", text_color=T.WARN)
        self._log(
            f"⚠ вышел yt-dlp {latest}: обновите (pip install -U yt-dlp) и пересоберите exe, "
            "иначе закладки площадок устарели",
            T.WARN,
        )

    def _show_preview(self, data):
        self._info_data = data
        self._show_preview_card()
        self.preview_title.configure(text=data.get("title") or "—")
        meta = []
        if data.get("platform"):
            meta.append(f"площадка: {data['platform']}")
        if data.get("uploader"):
            meta.append(data["uploader"])
        if data.get("live"):
            meta.append("прямая трансляция")
        if data.get("count", 1) > 1:
            meta.append(f"элементов: {data['count']}")
        if data.get("duration"):
            meta.append(f"длительность: {human_time(data['duration'])}")
        if data.get("view_count"):
            meta.append(f"просмотров: {data['view_count']:,}".replace(",", " "))
        heights = [h for h in (data.get("heights") or []) if h]
        if heights:
            meta.append(f"максимум: {max(heights)}p")
        self.preview_meta.configure(text="   ·   ".join(meta) or "—")
        thumb = data.get("thumbnail")
        self._photo = None
        self.thumb_label.configure(image="", text=T.GLYPH["film"])
        if thumb and Image:
            self._fetch_thumbnail(thumb)

    def _fetch_thumbnail(self, url):
        def work():
            payload = b""
            try:
                import urllib.request

                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=6) as response:
                    payload = response.read()
            except Exception:
                payload = b""
            self.events.put({"type": "thumb", "url": url, "data": payload})

        # В главном потоке нельзя: обложка тянется секундами и окно замирает
        threading.Thread(target=work, daemon=True).start()

    def _show_thumbnail(self, url, payload):
        if url != (self._info_data or {}).get("thumbnail"):
            return
        if not payload or Image is None:
            self.thumb_label.configure(image="", text=T.GLYPH["film"])
            return
        try:
            image = Image.open(io.BytesIO(payload)).convert("RGB")
            image.thumbnail((132, 74))
            self._photo = ImageTk.PhotoImage(image)
            self.thumb_label.configure(image=self._photo, text="")
        except Exception:
            self.thumb_label.configure(image="", text=T.GLYPH["film"])

    # ------------------------------------------------------------------ settings
    def _set_appearance(self, value):
        self.settings.set("appearance", value)
        ctk.set_appearance_mode(value if value in ("dark", "light") else "system")
        T.apply(self._mode())
        self.palette.set_accent(self.settings.get("accent"))
        self._rebuild()

    def _set_accent(self, name):
        self.settings.set("accent", name)
        T.apply(self._mode())
        self.palette.set_accent(name)
        self._rebuild()

    def toggle_appearance(self):
        self._set_appearance("light" if self._mode() == "dark" else "dark")

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.settings.get("download_dir"))
        if not folder:
            return
        folder = folder.replace("/", os.sep)
        self.settings.set("download_dir", folder)
        self.folder_label.configure(text=folder)
        if hasattr(self, "dir_field"):
            self.dir_field.delete("1.0", "end")
            self.dir_field.insert("1.0", folder)

    def _save_dir_field(self):
        value = self.dir_field.get().strip()
        if value and Path(value).exists():
            self.settings.set("download_dir", value)
            self.folder_label.configure(text=value)

    def _save_template_field(self):
        value = self.template_field.get().strip()
        if value:
            self.settings.set("filename_template", value)

    def _save_cookies(self, value):
        self.settings.set("cookies_browser", "" if value == "не использовать" else value)

    def _choose_ffmpeg(self):
        path = filedialog.askopenfilename(title="ffmpeg.exe", filetypes=[("ffmpeg", "ffmpeg.exe"), ("all", "*.*")])
        if path:
            self.settings.set("ffmpeg_path", path)
            self.ffmpeg_field.delete("1.0", "end")
            self.ffmpeg_field.insert("end", path)
            self._check_ffmpeg()

    def _download_ffmpeg(self):
        if self._ffmpeg_busy:
            return
        self._ffmpeg_busy = True
        self.ffmpeg_button.configure(state="disabled", text="Скачиваю…")
        self.ffmpeg_state.configure(text="скачиваю ffmpeg (~90 МБ)…", text_color=T.MUTED)

        def work():
            last = [0.0]

            def report(done, total):
                # отчёт приходит на каждый чанк — в GUI отправляем не чаще, чем раз в четверть секунды
                now = time.time()
                if now - last[0] < 0.25 and done < total:
                    return
                last[0] = now
                self.events.put({"type": "ffmpeg_progress", "done": done, "total": total})

            try:
                self.events.put({"type": "ffmpeg", "path": download_ffmpeg(report)})
            except Exception as exc:
                self.events.put({"type": "ffmpeg", "error": str(exc)[:200]})

        threading.Thread(target=work, daemon=True).start()

    def _ffmpeg_ready(self, path):
        # Путь не сохраняем в ffmpeg_path: поиск рядом с exe и в профиле работает и без жёсткой привязки
        self._check_ffmpeg()
        self.ffmpeg_state.configure(text=f"установлен: {path}", text_color=T.OK)

    def _check_ffmpeg(self):
        path = self.settings.get("ffmpeg_path") or find_ffmpeg()
        if path and Path(path).exists():
            self.ffmpeg_state.configure(text=f"найден: {Path(path).name}", text_color=T.OK)
        else:
            self.ffmpeg_state.configure(text="не найден: без него MP3 и склейка MP4 недоступны — нажмите «Скачать»", text_color=T.ERROR)

    def _open_folder(self):
        folder = Path(self.settings.get("download_dir"))
        folder.mkdir(parents=True, exist_ok=True)
        reveal_in_explorer(folder)

    def _reset_settings(self):
        from .settings import DEFAULTS

        keep_dir = self.settings.get("download_dir")
        self.settings.update(dict(DEFAULTS))
        self.settings.set("download_dir", keep_dir)
        self._rebuild()
        self._set_status("Настройки сброшены", T.WARN)

    def _rebuild(self):
        self.configure(fg_color=T.BG)
        for widget in (getattr(self, "sidebar", None), getattr(self, "content", None)):
            if widget:
                widget.destroy()
        self.pages = {}
        self.rows = {}
        self._build_sidebar()
        self._build_content()
        self._build_statusbar()
        self._render_pages()
        self.show_page(self.current)
        if hasattr(self, "theme_button"):
            self.theme_button.configure(text="Тёмная" if self._mode() == "light" else "Светлая")

    # --------------------------------------------------------------------- misc
    def _log(self, text, color=None):
        self.log_lines.append((text, color))
        overflow = len(self.log_lines) - MAX_LOG_LINES
        if overflow > 0:
            del self.log_lines[:overflow]
        if hasattr(self, "log_box"):
            if overflow > 0:
                self.log_box.trim(overflow)
            self.log_box.write(text, color)

    def _clear_log(self):
        self.log_lines = []
        self.log_box.clear_log()

    def _set_status(self, text, color=None):
        if hasattr(self, "status_text"):
            self.status_text.configure(text=text, text_color=color or T.MUTED)

    def _on_close(self):
        if self.engine.active_count() and self.settings.get("confirm_close"):
            if not messagebox.askyesno(
                "Есть активные задачи",
                f"В очереди ещё {self.engine.active_count()} задач. Выйти и прервать загрузку?",
                icon="warning",
            ):
                return
            self.engine.cancel_all()
        self._save_geometry()
        self.destroy()

    def _save_geometry(self):
        try:
            scaling = self._scaling()
            state = self.state()
            x = int(self.winfo_rootx() / scaling)
            y = int(self.winfo_rooty() / scaling)
            window = self.settings.get("window")
            if state == "normal" and self._on_screen(x, y):
                window = {
                    "width": int(self.winfo_width() / scaling),
                    "height": int(self.winfo_height() / scaling),
                    "x": x,
                    "y": y,
                }
            self.settings.set("window", window)
        except tk.TclError:
            pass
