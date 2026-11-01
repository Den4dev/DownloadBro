"""Генерация assets/icon.png и assets/icon.ico (запускать один раз или при смене стиля)."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
OUT = Path(__file__).resolve().parent

TOP = (91, 103, 242)
BOTTOM = (154, 92, 229)


def gradient(size):
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
        draw.line([(0, y), (size, y)], fill=color + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([8, 8, size - 9, size - 9], radius=int(size * 0.22), fill=255)
    img.putalpha(mask)
    return img


def arrow(img):
    size = img.size[0]
    draw = ImageDraw.Draw(img)
    cx = size // 2
    stroke = max(10, int(size * 0.055))
    half = int(size * 0.17)
    top = int(size * 0.27)
    shaft = int(size * 0.47)
    white = (255, 255, 255, 245)
    draw.line([(cx, top), (cx, shaft)], fill=white, width=stroke)
    draw.polygon(
        [(cx - half, shaft - half), (cx + half, shaft - half), (cx, shaft + int(half * 0.95))],
        fill=white,
    )
    tray_top = int(size * 0.68)
    draw.rounded_rectangle(
        [int(size * 0.24), tray_top, int(size * 0.76), int(size * 0.80)],
        radius=int(size * 0.035),
        outline=white,
        width=stroke,
    )
    return img


def main():
    base = arrow(gradient(SIZE))
    base.save(OUT / "icon.png")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    icons = []
    for w, h in sizes:
        copy = base.copy().resize((w, h), Image.LANCZOS)
        icons.append(copy.convert("RGBA"))
    icons[0].save(OUT / "icon.ico", sizes=tuple(sizes) + ((256, 256),), append_images=icons[1:])
    print("icon ready:", OUT / "icon.ico")


if __name__ == "__main__":
    main()
