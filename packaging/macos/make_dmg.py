"""Build the polished drag-to-Applications DMG (light-blue background, app + Applications link).

  python packaging/macos/make_dmg.py --app dist/Buddy.app --out dist/Buddy-macos-0.9.8.dmg [--icon Buddy.icns]

Uses `dmgbuild` (pure Python, no Finder scripting, so it works on headless CI).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def retina_background(workdir: Path) -> Path:
    """Combine 1x + 2x PNGs into one multi-resolution TIFF so the art is crisp on Retina Macs."""
    one, two = HERE / "dmg_background.png", HERE / "dmg_background@2x.png"
    if shutil.which("tiffutil"):
        out = workdir / "dmg_background.tiff"
        for flag in ("-cathidpicheck", "-cat"):      # strict check first, then the lenient join
            result = subprocess.run(["tiffutil", flag, str(one), str(two), "-out", str(out)], capture_output=True)
            if result.returncode == 0 and out.exists():
                return out
    return one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--icon", type=Path)
    parser.add_argument("--volname", default="Buddy")
    args = parser.parse_args()
    if not args.app.exists():
        raise SystemExit(f"{args.app} not found")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        bg = retina_background(Path(tmp))
        cmd = [sys.executable, "-m", "dmgbuild", "-s", str(HERE / "dmg_settings.py"),
               "-D", f"app={args.app}", "-D", f"bg={bg}"]
        if args.icon:
            cmd += ["-D", f"icon={args.icon}"]
        result = subprocess.run(cmd + [args.volname, str(args.out)])
        if result.returncode != 0 or not args.out.exists():
            raise SystemExit("dmgbuild failed; refusing to publish a DMG without the designed background")
    print("created", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
