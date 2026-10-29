"""Create a compressed macOS disk image containing Buddy and Applications."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--background", type=Path)
    args = parser.parse_args()
    if not args.app.is_dir() or args.app.suffix != ".app":
        raise SystemExit(f"Not a macOS app bundle: {args.app}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="buddy-dmg-") as temporary:
        stage = Path(temporary) / "Buddy"
        writable = Path(temporary) / "Buddy-rw.dmg"
        mountpoint = Path(temporary) / "Mounted"
        stage.mkdir()
        # Preserve code-signature extended attributes, resource forks, and ACLs.
        run(["ditto", "--rsrc", "--extattr", "--acl", str(args.app), str(stage / args.app.name)])
        (stage / "Applications").symlink_to("/Applications")
        background_path = None
        if args.background and args.background.is_file():
            background = stage / ".background"
            background.mkdir()
            run(["ditto", str(args.background), str(background / "dmg_background@2x.png")])
            background_path = ".background/dmg_background@2x.png"
        run(["hdiutil", "create", "-volname", "Buddy", "-srcfolder", str(stage), "-ov", "-format", "UDRW", str(writable)])
        mountpoint.mkdir()
        run(["hdiutil", "attach", "-nobrowse", "-noverify", "-mountpoint", str(mountpoint), str(writable)])
        try:
            if background_path:
                script = '''
                on run argv
                  set mountPath to item 1 of argv
                  set backgroundPath to item 2 of argv
                  tell application "Finder"
                    open POSIX file mountPath
                    delay 2
                    tell front window
                      set current view to icon view
                      set toolbar visible to false
                      set statusbar visible to false
                      set bounds to {120, 120, 840, 570}
                      set icon size of icon view options to 96
                      set arrangement of icon view options to not arranged
                      set background picture of icon view options to POSIX file backgroundPath
                      set position of item "Buddy.app" to {230, 245}
                      set position of item "Applications" to {620, 245}
                    end tell
                    close front window
                  end tell
                end run
                '''
                subprocess.run(
                    ["osascript", "-", str(mountpoint), str(mountpoint / background_path)],
                    input=script,
                    text=True,
                    check=True,
                    capture_output=True,
                )
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"Could not set the Finder disk image layout; keeping a functional DMG ({error})")
        finally:
            subprocess.run(["hdiutil", "detach", str(mountpoint)], check=True, capture_output=True)
        args.output.unlink(missing_ok=True)
        run([
            "hdiutil", "convert", str(writable), "-ov", "-format", "UDZO",
            "-imagekey", "zlib-level=9", "-o", str(args.output),
        ])
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
