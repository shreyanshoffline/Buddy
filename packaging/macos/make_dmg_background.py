"""Render a clean drag-to-install background for the macOS disk image."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1440, 900), "#f4f7fc")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 60, 1370, 840), radius=42, fill="#ffffff", outline="#dce5f2", width=3)
    try:
        title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 48)
        label = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 23)
    except OSError:
        title = label = small = ImageFont.load_default()
    draw.text((120, 115), "Install Buddy", font=title, fill="#172b4d")
    draw.text((122, 183), "Drag Buddy into Applications to install", font=small, fill="#62738a")
    draw.rounded_rectangle((180, 300, 1260, 620), radius=28, fill="#f7faff", outline="#e1e9f4", width=2)
    draw.ellipse((292, 360, 492, 560), fill="#e8f2ff")
    with Image.open(ROOT / "gui" / "assets" / "Buddy_Logo_Beta.png") as logo:
        logo = logo.convert("RGBA")
        logo.thumbnail((156, 156), Image.Resampling.LANCZOS)
        image.alpha_composite(logo, (314, 382)) if image.mode == "RGBA" else image.paste(logo, (314, 382), logo)
    draw.text((548, 397), "Buddy", font=label, fill="#233b60")
    draw.text((548, 449), "Your local-first AI assistant", font=small, fill="#62738a")
    draw.line((710, 500, 940, 500), fill="#4c88d8", width=6)
    draw.polygon([(940, 500), (910, 482), (910, 518)], fill="#4c88d8")
    draw.rounded_rectangle((1020, 350, 1180, 540), radius=18, fill="#edf3fb", outline="#ccd9eb", width=2)
    draw.text((1050, 411), "A", font=title, fill="#7189a8")
    draw.text((1040, 557), "Applications", font=small, fill="#62738a")
    # The app icon itself is inserted by Finder as the branded .app icon.
    image.save(args.output, format="PNG", optimize=True)
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
