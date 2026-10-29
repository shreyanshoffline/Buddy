"""Generate the platform icon formats from Buddy's source logo."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "gui" / "assets" / "Buddy_Logo_Beta.png"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "icons")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with Image.open(SOURCE) as source:
        image = source.convert("RGBA")
        image.save(args.out / "Buddy.ico", format="ICO", sizes=[(s, s) for s in SIZES])
        image.save(args.out / "Buddy.icns", format="ICNS", sizes=[(s, s) for s in SIZES if s >= 16])
        for size in SIZES:
            icon = image.resize((size, size), Image.Resampling.LANCZOS)
            for theme in ("hicolor",):
                target = args.out / theme / f"{size}x{size}" / "apps" / "buddy.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                icon.save(target, format="PNG", optimize=True)
    print(f"Created Buddy.ico, Buddy.icns, and Linux hicolor icons in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
