import tkinter as tk

import customtkinter as ctk

from . import theme as T

F = T.FONTS


class Card(ctk.CTkFrame):
    """Блок-карточка с необязательным заголовком; содержимое кладётся в .inner."""

    def __init__(self, master, title=None, subtitle=None, padding=16, **kwargs):
        super().__init__(
            master,
            fg_color=T.CARD,
            corner_radius=16,
            border_width=1,
            border_color=T.BORDER,
            **kwargs,
        )
        self.inner = ctk.CTkFrame(self, fg_color="transparent")
        self.inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        if title:
            box = ctk.CTkFrame(self.inner, fg_color="transparent")
            box.pack(fill="x")
            ctk.CTkLabel(box, text=title, font=F.h2, text_color=T.TEXT, anchor="w").pack(fill="x")
            if subtitle:
                ctk.CTkLabel(box, text=subtitle, font=F.small, text_color=T.MUTED, anchor="w").pack(
                    fill="x", pady=(2, 0)
                )
            ctk.CTkFrame(self.inner, height=12, fg_color="transparent").pack(fill="x")


class Caption(ctk.CTkLabel):

    def __init__(self, master, text, **kwargs):
        super().__init__(
            master, text=text.upper(), font=F.h3, text_color=T.FAINT, anchor="w", **kwargs
        )


class Field(ctk.CTkEntry):

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", T.FIELD)
        kwargs.setdefault("border_color", T.BORDER)
        kwargs.setdefault("text_color", T.TEXT)
        kwargs.setdefault("placeholder_text_color", T.FAINT)
        kwargs.setdefault("height", 42)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("font", F.body)
        super().__init__(master, **kwargs)


class UrlBox(ctk.CTkTextbox):
    """Многострочное поле ссылок (каждая ссылка с новой строки)."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            wrap="word",
            fg_color=T.FIELD,
            border_color=T.BORDER,
            border_width=1,
            corner_radius=12,
            text_color=T.TEXT,
            font=F.body,
            activate_scrollbars=True,
            **kwargs,
        )
        self._hint = (
            "вставьте ссылку · YouTube, Rutube, VK, OK и ещё сотни площадок\n"
            "несколько ссылок — с новой строки"
        )
        self._hint_shown = False
        # Реальные клики и клавиши приходят во внутренний tk.Text, а не в обёртку CTk:
        # без этих привязок подсказка остаётся жить в поле как обычный текст.
        for sequence in ("<Button-1>", "<Button-3>", "<Key>", "<<Paste>>", "<FocusIn>"):
            self._textbox.bind(sequence, self._on_user_input, add="+")
        self._textbox.bind("<FocusOut>", lambda _e: self.after(10, self.show_hint), add="+")
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Вставить", command=self.paste)
        self._menu.add_command(label="Выделить всё", command=lambda: self._textbox.tag_add("sel", "1.0", "end"))
        self._menu.add_separator()
        self._menu.add_command(label="Очистить", command=self.clear)
        self._textbox.bind("<Button-3>", self._popup_menu, add="+")
        self.show_hint()

    def _popup_menu(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _read(self):
        return self.get("1.0", "end-1c")

    def _on_user_input(self, _event=None):
        if self._hint_shown:
            self.hide_hint()

    def bind_text(self, sequence, func, add="+"):
        """Привязка к настоящему полю ввода (фрейм CTk фокус и клавиши не получает)."""
        self._textbox.bind(sequence, func, add=add)

    def focus_text(self):
        self._textbox.focus_set()
        self._textbox.mark_set("insert", "end-1c")

    def show_hint(self, force=False):
        if self._read().strip():
            return
        if not force and self._textbox.focus_get() is self._textbox:
            return
        self._hint_shown = True
        super().insert("1.0", self._hint)
        self.configure(text_color=T.FAINT)

    def hide_hint(self):
        if self._hint_shown:
            self._hint_shown = False
            self.delete("1.0", "end")
        self.configure(text_color=T.TEXT)

    def get_text(self):
        text = self._read().strip()
        if not text or self._hint_shown:
            return ""
        if self._hint in text:
            return text.replace(self._hint, "").strip()
        return text

    def set_text(self, value):
        self.hide_hint()
        self.delete("1.0", "end")
        if value:
            super().insert("1.0", value)

    def paste(self):
        self._textbox.focus_set()
        self._textbox.event_generate("<<Paste>>")

    def clear(self):
        self.set_text("")
        self.show_hint(force=True)


class GhostButton(ctk.CTkButton):

    def __init__(self, master, text="", icon=None, command=None, palette=None, **kwargs):
        kwargs.setdefault("fg_color", T.CARD_SOFT)
        kwargs.setdefault("hover_color", T.BORDER)
        kwargs.setdefault("text_color", T.TEXT)
        kwargs.setdefault("height", 34)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("font", F.button)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.BORDER)
        label = f"{T.GLYPH[icon]}  {text}" if icon else text
        width = kwargs.pop("width", None)
        if width is None:
            width = 40 if (icon and not text) else max(90, 34 + 9 * len(label))
        super().__init__(master, text=label, command=command, width=width, **kwargs)


class PrimaryButton(ctk.CTkButton):

    def __init__(self, master, text, palette, command=None, **kwargs):
        kwargs.setdefault("fg_color", palette.main)
        kwargs.setdefault("hover_color", palette.hover)
        kwargs.setdefault("text_color", palette.on_main)
        kwargs.setdefault("height", 42)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("font", F.button)
        super().__init__(master, text=text, command=command, **kwargs)


class Chip(ctk.CTkButton):

    def __init__(self, master, text, command=None, palette=None, **kwargs):
        self._palette = palette
        self._selected = False
        kwargs.setdefault("height", 30)
        kwargs.setdefault("corner_radius", 15)
        kwargs.setdefault("width", 30 + 8 * len(text))
        kwargs.setdefault("fg_color", T.CARD_SOFT)
        kwargs.setdefault("hover_color", T.BORDER)
        kwargs.setdefault("text_color", T.MUTED)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.BORDER)
        kwargs.setdefault("font", F.small)
        super().__init__(master, text=text, command=command, **kwargs)

    def set_selected(self, value):
        self._selected = value
        self._apply()

    def set_palette(self, palette):
        self._palette = palette
        self._apply()

    def _apply(self):
        if self._selected and self._palette:
            self.configure(
                fg_color=self._palette.main,
                hover_color=self._palette.hover,
                text_color=self._palette.on_main,
                border_color=self._palette.main,
            )
        else:
            self.configure(
                fg_color=T.CARD_SOFT,
                hover_color=T.BORDER,
                text_color=T.MUTED,
                border_color=T.BORDER,
            )


class Tile(ctk.CTkFrame):
    """Плитка выбора формата: иконка + заголовок + подпись."""

    def __init__(self, master, icon, title, subtitle, palette, command, width=190, height=76):
        super().__init__(
            master,
            fg_color=T.CARD_SOFT,
            corner_radius=14,
            border_width=1,
            border_color=T.BORDER,
            width=width,
            height=height,
        )
        self.palette = palette
        self.command = command
        self.selected = False
        self.pack_propagate(False)
        self.grid_propagate(False)

        self.icon_label = ctk.CTkLabel(self, text=T.GLYPH[icon], font=F.icon_big, text_color=T.MUTED)
        self.icon_label.place(relx=0.07, rely=0.5, anchor="w")
        self.title_label = ctk.CTkLabel(self, text=title, font=F.h3, text_color=T.TEXT, anchor="w")
        self.title_label.place(relx=0.24, rely=0.32, anchor="w")
        self.sub_label = ctk.CTkLabel(self, text=subtitle, font=F.tiny, text_color=T.FAINT, anchor="w")
        self.sub_label.place(relx=0.24, rely=0.66, anchor="w")
        self.mark = ctk.CTkLabel(self, text="", font=F.icon, width=18)
        self.mark.place(relx=0.95, rely=0.12, anchor="ne")

        for widget in (self, self.icon_label, self.title_label, self.sub_label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", lambda _e: self._on_hover(True))
            widget.bind("<Leave>", lambda _e: self._on_hover(False))

    def _on_click(self, _event=None):
        if self.command:
            self.command()

    def _on_hover(self, active):
        if self.selected:
            return
        self.configure(border_color=self.palette.soft if active else T.BORDER)

    def set_selected(self, value):
        self.selected = value
        if value:
            self.configure(fg_color=self.palette.glow, border_color=self.palette.main, border_width=2)
            self.icon_label.configure(text_color=self.palette.main)
            self.title_label.configure(text_color=T.TEXT)
            self.mark.configure(text=T.GLYPH["check"], text_color=self.palette.main)
        else:
            self.configure(fg_color=T.CARD_SOFT, border_color=T.BORDER, border_width=1)
            self.icon_label.configure(text_color=T.MUTED)
            self.title_label.configure(text_color=T.TEXT)
            self.mark.configure(text="")


class Switch(ctk.CTkSwitch):

    def __init__(self, master, text, palette, command=None, variable=None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            variable=variable,
            progress_color=palette.main,
            fg_color=T.BORDER,
            button_color=T.SWITCH,
            button_hover_color=T.SWITCH_HOVER,
            text_color=T.TEXT,
            font=F.body,
            switch_width=44,
            switch_height=22,
            **kwargs,
        )


class Option(ctk.CTkOptionMenu):

    def __init__(self, master, values, command=None, palette=None, width=160, **kwargs):
        kwargs.update(
            {
                "fg_color": T.CARD_SOFT,
                "button_color": palette.main if palette else T.BORDER,
                "button_hover_color": palette.hover if palette else T.BORDER,
                "text_color": T.TEXT,
                "dropdown_fg_color": T.CARD,
                "dropdown_hover_color": T.CARD_SOFT,
                "dropdown_text_color": T.TEXT,
                "dynamic_resizing": False,
            }
        )
        super().__init__(
            master,
            values=values,
            command=command,
            width=width,
            height=34,
            corner_radius=10,
            font=F.body,
            **kwargs,
        )


class LogBox(ctk.CTkTextbox):

    def __init__(self, master, **kwargs):
        self._tag_names = set()
        super().__init__(
            master,
            wrap="word",
            fg_color=T.LOG_BG,
            text_color=T.LOG_FG,
            font=F.mono,
            border_width=1,
            border_color=T.BORDER,
            corner_radius=12,
            **kwargs,
        )

    def write(self, text, color=None):
        self.insert("end", text + "\n")
        if color:
            line = int(self.index("end-2c").split(".")[0])
            tag = f"fg_{str(color).lstrip('#')}"
            if tag not in self._tag_names:
                self.tag_config(tag, foreground=color)
                self._tag_names.add(tag)
            self.tag_add(tag, f"{line}.0", f"{line}.end")
        self.see("end")

    def clear_log(self):
        self.delete("1.0", "end")

    def trim(self, count):
        self.delete("1.0", f"{count + 1}.0")


_TOOLTIPS = []


class Tooltip:
    """Подсказка по наведению. Окно появляется не мгновенно: иначе всплывает стопка
    подсказок, когда окно приложения разворачивается прямо под неподвижным курсором."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        self._job = None
        # Enter на сам фрейм не приходит, когда курсор попадает на его canvas:
        # в CTk-виджете область целиком перекрыта дочерними окнами.
        for target in self._targets():
            target.bind("<Enter>", self._schedule, add="+")
            target.bind("<Leave>", self._on_leave, add="+")

    def _targets(self):
        found, stack = [self.widget], [self.widget]
        while stack:
            for child in stack.pop().winfo_children():
                found.append(child)
                stack.append(child)
        return found

    def _on_leave(self, _event=None):
        if not self._under_cursor():
            self._hide()

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self._job = self.widget.after(400, self._show)
        except tk.TclError:
            pass

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _under_cursor(self):
        try:
            x, y = self.widget.winfo_pointerxy()
            left, top = self.widget.winfo_rootx(), self.widget.winfo_rooty()
            return left <= x < left + self.widget.winfo_width() and top <= y < top + self.widget.winfo_height()
        except tk.TclError:
            return False

    def _show(self):
        self._job = None
        if self.window or not self.text:
            return
        try:
            if not self.widget.winfo_exists():
                return
        except tk.TclError:
            return
        if not self._under_cursor():
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.window = ctk.CTkToplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        frame = ctk.CTkFrame(
            self.window, fg_color=T.CARD_SOFT, corner_radius=8, border_width=1, border_color=T.BORDER
        )
        frame.pack()
        ctk.CTkLabel(frame, text=self.text, font=F.tiny, text_color=T.TEXT, padx=9, pady=5).pack()
        _TOOLTIPS.append(self)

    def _hide(self, _event=None):
        self._cancel()
        if self.window:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
        if self in _TOOLTIPS:
            _TOOLTIPS.remove(self)


def hide_tooltips():
    """Сменить страницу, не пошевелив мышью — Leave не приходит, и подсказка остаётся висеть."""
    for tip in list(_TOOLTIPS):
        tip._hide()
