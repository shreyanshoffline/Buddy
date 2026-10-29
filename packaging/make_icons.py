"""Turn gui/assets/Buddy_Logo_Beta.png into every icon format the installers need.

  python packaging/make_icons.py --out build/icons

Creates: Buddy.ico (Windows), Buddy.icns (macOS, only where sips/iconutil exist),
and icons/<size>.png (Linux hicolor theme). Needs Pillow.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "gui" / "assets" / "Buddy_Logo_Beta.png"
LINUX_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]


def square(path: Path = LOGO) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def make_ico(out: Path) -> Path:
    square().save(out, format="ICO", sizes=ICO_SIZES)
    return out


def make_linux_pngs(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = square()
    paths = []
    for size in LINUX_SIZES:
        p = out_dir / f"{size}.png"
        base.resize((size, size), Image.LANCZOS).save(p)
        paths.append(p)
    return paths


def make_icns(out: Path) -> Path | None:
    """macOS only: needs `sips` and `iconutil`, which every Mac ships."""
    if not (shutil.which("sips") and shutil.which("iconutil")):
        return None
    iconset = out.with_suffix(".iconset")
    iconset.mkdir(parents=True, exist_ok=True)
    base = square()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            base.resize((px, px), Image.LANCZOS).save(iconset / name)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "build" / "icons"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print("ico :", make_ico(out / "Buddy.ico"))
    print("png :", len(make_linux_pngs(out / "icons")), "sizes")
    print("icns:", make_icns(out / "Buddy.icns") or "skipped (not on macOS)")


if __name__ == "__main__":
    main()
