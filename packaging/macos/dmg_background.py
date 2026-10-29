"""Draws the light-blue DMG window background (660x400, plus a 2x retina copy).

  python packaging/macos/dmg_background.py

The icon positions here MUST match packaging/macos/dmg_settings.py.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 660, 400                 # Finder window content size (points)
APP_XY, APPS_XY = (165, 205), (495, 205)   # icon centres
S = 4                           # draw at 4x, then shrink for smooth edges

NAVY, BLUE, MID = (11, 42, 91), (37, 99, 235), (47, 93, 155)
FONTS_BOLD = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"]
FONTS_REG = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]


def font(candidates, size):
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(w, h):
    top, bottom = (232, 245, 255), (168, 212, 255)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = min(1.0, (y / h) * 0.8 + (x / w) * 0.2)   # mostly vertical, slightly diagonal
            px[x, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return img


def white(size, mask, opacity=1.0):
    """A white layer shaped by `mask` (mode L). Avoids the grey halos you get when blurring RGBA."""
    layer = Image.new("RGBA", size, (255, 255, 255, 0))
    layer.putalpha(mask.point(lambda v: int(v * opacity)))
    return layer


def glow(base, cx, cy, r, alpha):
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(r * 0.45))
    return Image.alpha_composite(base, white(base.size, mask, alpha / 255))


def centred(draw, text, y, fnt, fill):
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((W * S - (box[2] - box[0])) / 2, y), text, font=fnt, fill=fill)


def render(scale: int) -> Image.Image:
    img = gradient(W * S // 4, H * S // 4).resize((W * S, H * S), Image.BICUBIC).convert("RGBA")
    for cx, cy, r, a in [(110, 50, 140, 150), (570, 350, 170, 120)]:
        img = glow(img, cx * S, cy * S, r * S, a)

    # soft bubbles for a playful, clean look
    bubbles = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bubbles)
    for cx, cy, r in [(40, 330, 26), (88, 366, 12), (620, 52, 22), (585, 92, 9), (330, 372, 8), (28, 120, 10)]:
        bd.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=(255, 255, 255, 170), width=2 * S)
    img = Image.alpha_composite(img, bubbles)

    # frosted pads behind the two icons
    for cx, cy in (APP_XY, APPS_XY):
        box = [(cx - 88) * S, (cy - 88) * S, (cx + 88) * S, (cy + 92) * S]
        edge = Image.new("L", img.size, 0)
        ImageDraw.Draw(edge).rounded_rectangle(box, radius=34 * S, fill=255)
        inner = Image.new("L", img.size, 0)
        ImageDraw.Draw(inner).rounded_rectangle([box[0] + 3 * S, box[1] + 3 * S, box[2] - 3 * S, box[3] - 3 * S],
                                                radius=31 * S, fill=255)
        img = Image.alpha_composite(img, white(img.size, edge, 0.85))     # bright rim
        img = Image.alpha_composite(img, white(img.size, inner, 0.0))
        fill = Image.new("L", img.size, 0)
        ImageDraw.Draw(fill).rounded_rectangle([box[0] + 3 * S, box[1] + 3 * S, box[2] - 3 * S, box[3] - 3 * S],
                                               radius=31 * S, fill=255)
        tint = Image.new("RGBA", img.size, (205, 230, 255, 0))
        tint.putalpha(fill.point(lambda v: int(v * 0.55)))
        img = Image.alpha_composite(img, tint)

    d = ImageDraw.Draw(img)
    # title + subtitle
    centred(d, "Install Buddy", 26 * S, font(FONTS_BOLD, 34 * S), NAVY)
    centred(d, "Drag Buddy into your Applications folder", 72 * S, font(FONTS_REG, 15 * S), MID)

    # chunky arrow between the pads
    y = APP_XY[1] - 8
    x0, x1 = APP_XY[0] + 104, APPS_XY[0] - 112
    d.line([(x0 * S, y * S), ((x1 - 10) * S, y * S)], fill=BLUE, width=9 * S)
    d.polygon([(x1 * S, y * S), ((x1 - 30) * S, (y - 24) * S), ((x1 - 30) * S, (y + 24) * S)], fill=BLUE)

    centred(d, "Made by Shrey Industries for Hack Club", 372 * S, font(FONTS_REG, 11 * S), MID)
    return img.convert("RGB").resize((W * scale, H * scale), Image.LANCZOS)


def main() -> None:
    render(1).save(HERE / "dmg_background.png", optimize=True, dpi=(72, 72))
    render(2).save(HERE / "dmg_background@2x.png", optimize=True, dpi=(144, 144))
    print("wrote", HERE / "dmg_background.png", "and @2x")


if __name__ == "__main__":
    main()
