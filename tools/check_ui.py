import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# в консоль Windows cp866/cp1251 юникодные точки и стрелки не пролезут
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import customtkinter as ctk

from downloadbro.widgets import Chip, Tooltip, UrlBox, _TOOLTIPS, hide_tooltips

URL = "https://youtu.be/dQw4w9WgXcQ?si=abc"
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (" | " + extra if extra else ""))
    if not ok:
        fails.append(name)


def test_urlbox():
    root = ctk.CTk()
    root.geometry("500x200+1600+800")
    box = UrlBox(root, height=80)
    box.pack(fill="x", padx=10, pady=10)
    root.update()

    check("подсказка показана на старте", box._hint_shown and not box.get_text())
    raw = box.get("1.0", "end-1c")
    check("подсказка лежит текстом", "вставьте ссылку" in raw, repr(raw[:40]))
    check("get_text не стирает подсказку", box._hint_shown and "вставьте" in box.get("1.0", "end-1c"))

    root.clipboard_clear()
    root.clipboard_append(URL)
    root.update()

    # имитация Ctrl+V в поле: фокус на внутреннем Text, затем клавиша
    box._textbox.focus_force()
    root.update()
    check("фокус в поле снимает подсказку", not box._hint_shown, repr(box.get("1.0", "end-1c"))[:40])

    box._textbox.event_generate("<<Paste>>")
    root.update()
    got = box.get_text()
    check("Ctrl+V вставляет ссылку", got == URL, repr(got) + " | clipboard=" + repr(root.clipboard_get()))
    raw = box.get("1.0", "end-1c")
    check("в поле нет остатков подсказки", "вставьте" not in raw, repr(raw))

    box.set_text("")
    box.show_hint()
    root.update()
    box._textbox.event_generate("<Button-1>", x=20, y=20)
    root.update()
    check("клик мышью снимает подсказку", not box._hint_shown and box.get_text() == "")

    box.set_text(URL + "\nhttps://rutube.ru/video/abc/")
    check("две ссылки читаются", box.get_text().count("http") == 2)

    # вставка через контекстное меню (правая кнопка) идёт тем же путём
    box.clear()
    root.update()
    check("clear() возвращает подсказку", box._hint_shown)
    box.paste()
    root.update()
    check("вставка из меню работает", box.get_text() == URL, repr(box.get_text()))

    box.set_text("")
    box.show_hint()
    box.get_text()
    root.update()
    check("после get_text подсказка не возвращается", "вставьте" not in box.get("1.0", "end-1c"))

    root.destroy()


def test_app():
    from downloadbro.app import App
    from downloadbro.settings import Settings

    app = App(Settings())
    app.geometry("1060x700+120+120")
    app.update()

    app.url_box.set_text("")
    app.url_box.show_hint()
    app.update()

    app.clipboard_clear()
    app.clipboard_append(URL + "\nhttps://rutube.ru/video/abc/")
    app.clipboard_get()
    app._paste_clipboard(None)
    app.update()
    urls = app._urls_from_input()
    check("кнопка «Вставить» даёт 2 ссылки", len(urls) == 2, str(urls))
    check("после вставки подсказки нет", "вставьте" not in app.url_box.get("1.0", "end-1c"))
    check("площадка определяется", "YouTube" in app.platform_label.cget("text"), app.platform_label.cget("text"))

    # Ctrl+V при фокусе в поле не должен дублировать текст
    app.url_box._textbox.focus_force()
    app.update()
    before = app.url_box.get_text()
    app._paste_clipboard(type("E", (), {})())  # с event -> должен выйти сразу
    app.update()
    check("Ctrl+V в поле не дублирует", app.url_box.get_text() == before)

    # повторная вставка кнопкой добавляет ссылку с новой строки, ничего не затирая
    app._paste_clipboard(None)
    app.update()
    check("вторая вставка добавлена отдельной строкой",
          app.url_box.get_text().count("http") == 4, repr(app.url_box.get_text()))

    # превью должно оказаться сразу под карточкой ссылки, а не в конце страницы
    app._show_preview({"title": "Тест", "platform": "YouTube", "thumbnail": ""})
    app.update()
    slaves = [str(w) for w in app.preview.master.pack_slaves()]
    idx_card = slaves.index(str(app.url_card))
    idx_prev = slaves.index(str(app.preview))
    check("превью вставлено под полем ссылки", idx_prev == idx_card + 1, f"{idx_prev} vs {idx_card}")

    # обложка не должна вешать интерфейс
    t0 = time.time()
    app._show_preview({
        "title": "Обложка",
        "platform": "YouTube",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    })
    app.update()
    elapsed = time.time() - t0
    check("превью не блокирует окно", elapsed < 0.5, f"{elapsed:.2f}s")

    deadline = time.time() + 12
    loaded = False
    while time.time() < deadline:
        app.update()
        if app.thumb_label.cget("image"):
            loaded = True
            break
        time.sleep(0.05)
    check("обложка догрузилась в фоне", loaded, "" if loaded else "нет картинки за 12с")

    app._clear_url()
    app.update()
    check("очистка возвращает подсказку", app.url_box._hint_shown)
    check("превью скрыто после очистки", not app.preview.winfo_manager())

    app.destroy()


def test_ffmpeg():
    import downloadbro.app as app_module
    from downloadbro.app import App
    from downloadbro.settings import Settings

    app = App(Settings())
    app.update()

    def wait_idle(limit=10):
        deadline = time.time() + limit
        while time.time() < deadline and app._ffmpeg_busy:
            app.update()
            time.sleep(0.05)
        app.update()

    calls = []

    def fake_download(report=None):
        calls.append(1)
        if report:
            report(1024, 0)
        return "C:\\Users\\test\\ffmpeg\\bin\\ffmpeg.exe"

    original = app_module.download_ffmpeg
    app_module.download_ffmpeg = fake_download
    try:
        app._download_ffmpeg()
        app._download_ffmpeg()
        check("докачка ffmpeg запущена и не двойная", app._ffmpeg_busy)
        wait_idle()
        check("докачка завершилась одним вызовом", (not app._ffmpeg_busy) and len(calls) == 1, f"вызовов {len(calls)}")
        state = str(app.ffmpeg_button.cget("state"))
        check("кнопка снова активна", state == "normal", state)
        text = app.ffmpeg_state.cget("text")
        check("путь показан в статусе", "ffmpeg.exe" in text, repr(text))

        def boom(report=None):
            raise RuntimeError("нет связи")

        app_module.download_ffmpeg = boom
        app._download_ffmpeg()
        wait_idle(5)
        text = app.ffmpeg_state.cget("text")
        check("сбой докачки объяснён", "не вышло" in text, repr(text))
        check("после сбоя кнопка живая", str(app.ffmpeg_button.cget("state")) == "normal" and not app._ffmpeg_busy)
    finally:
        app_module.download_ffmpeg = original
        app.destroy()


def test_tooltips():
    from downloadbro import theme as T

    root = ctk.CTk()
    root.geometry("420x220+1500+700")
    palette = T.Palette()
    chip = Chip(root, "YouTube", palette=palette)
    chip.pack(padx=20, pady=20)
    tip = Tooltip(chip, "открыть https://youtube.com")
    tip._under_cursor = lambda: True
    root.update()

    # указатель попадает на canvas внутри кнопки, а не на фрейм CTk
    chip._canvas.event_generate("<Enter>")
    root.update()
    check("подсказка не выпрыгивает мгновенно", tip.window is None)

    deadline = time.time() + 1.5
    while time.time() < deadline and tip.window is None:
        root.update()
        time.sleep(0.05)
    check("подсказка появилась после паузы", tip.window is not None and tip in _TOOLTIPS)

    chip._canvas.event_generate("<Enter>")
    chip._canvas.event_generate("<Enter>")
    root.update()
    time.sleep(0.6)
    root.update()
    check("двойной Enter не множит окна", tip.window is not None and _TOOLTIPS.count(tip) == 1,
          f"в списке {len(_TOOLTIPS)}")

    # уход мыши, если курсор ещё внутри виджета, подсказку не прячет
    chip._canvas.event_generate("<Leave>")
    root.update()
    check("Leave под курсором игнорируется", tip.window is not None)

    hide_tooltips()
    root.update()
    check("смена страницы прячет подсказки", tip.window is None and not _TOOLTIPS)

    tip._under_cursor = lambda: False
    chip._canvas.event_generate("<Enter>")
    root.update()
    time.sleep(0.6)
    root.update()
    check("без курсора на виджете подсказка не всплывает", tip.window is None)

    tip._under_cursor = lambda: True
    chip._canvas.event_generate("<Enter>")
    deadline = time.time() + 1.5
    while time.time() < deadline and tip.window is None:
        root.update()
        time.sleep(0.05)
    tip._under_cursor = lambda: False
    chip._canvas.event_generate("<Leave>")
    root.update()
    check("уход мыши за пределы гасит подсказку", tip.window is None and not _TOOLTIPS)

    root.destroy()


try:
    test_urlbox()
except Exception:
    traceback.print_exc()
    fails.append("urlbox crashed")
try:
    test_app()
except Exception:
    traceback.print_exc()
    fails.append("app crashed")
try:
    test_ffmpeg()
except Exception:
    traceback.print_exc()
    fails.append("ffmpeg crashed")
try:
    test_tooltips()
except Exception:
    traceback.print_exc()
    fails.append("tooltips crashed")

print("\nИТОГ:", "все проверки прошли" if not fails else f"провалено {len(fails)}: {fails}")
