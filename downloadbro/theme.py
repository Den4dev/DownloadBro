FONT_UI = "Segoe UI"
FONT_HEADING = "Segoe UI Semibold"
FONT_MONO = "Consolas"
FONT_ICON = "Segoe MDL2 Assets"

DARK = {
    "bg": "#0D1016",
    "sidebar": "#11151E",
    "card": "#151B26",
    "card_soft": "#1B2331",
    "field": "#10151E",
    "border": "#242E3E",
    "text": "#E9EEF8",
    "muted": "#8996AB",
    "faint": "#5A6678",
    "ok": "#3DD68C",
    "warn": "#F0B429",
    "error": "#F2606A",
    "log_bg": "#0A0D12",
    "log_fg": "#9FB2CC",
    "switch": "#EDEFF5",
    "switch_hover": "#FFFFFF",
}
LIGHT = {
    "bg": "#F2F4F9",
    "sidebar": "#FFFFFF",
    "card": "#FFFFFF",
    "card_soft": "#EEF1F7",
    "field": "#F7F9FC",
    "border": "#DCE3EF",
    "text": "#12161E",
    "muted": "#5F6C80",
    "faint": "#98A3B4",
    "ok": "#0F9D58",
    "warn": "#B8760A",
    "error": "#D33240",
    "log_bg": "#FFFFFF",
    "log_fg": "#43506A",
    "switch": "#FFFFFF",
    "switch_hover": "#EDEFF5",
}

MODE = DARK

ACCENTS = {
    "индиго": ("#5B67F2", "#4550D8"),
    "фиолет": ("#9A5CE5", "#7E40C9"),
    "бирюза": ("#12B8A6", "#0C978A"),
    "розе": ("#F0497A", "#D0325F"),
    "янтарь": ("#F59E0B", "#D07F03"),
    "изумруд": ("#22C55E", "#159C46"),
}

GLYPH = {
    "download": "",
    "queue": "\uE8FD",
    "history": "",
    "settings": "",
    "folder": "\uF12B",
    "paste": "",
    "close": "",
    "play": "",
    "stop": "",
    "sun": "",
    "moon": '\ue708',
    "open": "\uE8DE",
    "retry": "",
    "trash": "",
    "link": "",
    "info": "",
    "check": "",
    "music": "",
    "film": "",
    "chevron": "",
}


def apply(mode):
    """Фиксирует палитру (customtkinter 6 по-своему трактует кортежи, поэтому цвета — плоские строки)."""
    global MODE, APPEARANCE, BG, SIDEBAR, CARD, CARD_SOFT, FIELD, BORDER, TEXT, MUTED, FAINT
    global OK, WARN, ERROR, LOG_BG, LOG_FG, SWITCH, SWITCH_HOVER
    MODE = DARK if mode == "dark" else LIGHT
    APPEARANCE = mode
    BG = MODE["bg"]
    SIDEBAR = MODE["sidebar"]
    CARD = MODE["card"]
    CARD_SOFT = MODE["card_soft"]
    FIELD = MODE["field"]
    BORDER = MODE["border"]
    TEXT = MODE["text"]
    MUTED = MODE["muted"]
    FAINT = MODE["faint"]
    OK = MODE["ok"]
    WARN = MODE["warn"]
    ERROR = MODE["error"]
    LOG_BG = MODE["log_bg"]
    LOG_FG = MODE["log_fg"]
    SWITCH = MODE["switch"]
    SWITCH_HOVER = MODE["switch_hover"]


def shade(hex_color, amount):
    hex_color = hex_color.lstrip("#")
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [min(1.0, max(0.0, c * (1 + amount))) for c in rgb]
    return "#" + "".join(f"{int(c * 255):02X}" for c in rgb)


def tint(hex_color, target, amount=0.14):
    base = [int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    to = [int(target.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [b + (t - b) * amount for b, t in zip(base, to)]
    return "#" + "".join(f"{int(c):02X}" for c in mixed)


class Palette:

    def __init__(self, accent_key="индиго"):
        self.set_accent(accent_key)

    def set_accent(self, key):
        main, dark = ACCENTS.get(key, ACCENTS["индиго"])
        self.name = key
        self.main = main
        self.hover = shade(main, -0.18)
        self.soft = shade(main, 0.18)
        self.on_main = "#FFFFFF"
        self.glow = tint(dark, MODE["card"], 0.16 if APPEARANCE == "dark" else 0.86)
        self.ring = tint(dark, MODE["card"], 0.34 if APPEARANCE == "dark" else 0.7)


apply("dark")


class Fonts:

    def __init__(self):
        self.h1 = (FONT_HEADING, 25, "bold")
        self.h2 = (FONT_HEADING, 16, "bold")
        self.h3 = (FONT_HEADING, 12, "bold")
        self.body = (FONT_UI, 13)
        self.small = (FONT_UI, 11)
        self.tiny = (FONT_UI, 10)
        self.mono = (FONT_MONO, 11)
        self.button = (FONT_HEADING, 12, "bold")
        self.cta = (FONT_HEADING, 15, "bold")
        self.metric = (FONT_HEADING, 21, "bold")
        self.icon = (FONT_ICON, 15)
        self.icon_big = (FONT_ICON, 24)
        self.nav = (FONT_UI, 13)


FONTS = Fonts()
