"""Build a portable Buddy bundle on Windows or Linux.

macOS keeps its dedicated shell wrapper because signing, entitlements and
notarization are Apple-specific. This script uses the same source entry point
on every other desktop OS and writes one ZIP into ``dist/``.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Running ``python packaging/build.py`` puts ``packaging/`` on sys.path, not
# the repository root. Add the root explicitly so the documented command
# works from any current directory.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import APP_VERSION


DIST = ROOT / "dist"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def target_name() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return system or "portable"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a portable Buddy bundle.")
    parser.add_argument("--skip-tests", action="store_true", help="Do not run the offline test suite first.")
    args = parser.parse_args()

    if platform.system() == "Darwin":
        raise SystemExit("Use bash packaging/build_mac.sh on macOS so signing remains explicit.")

    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "tests"])

    DIST.mkdir(exist_ok=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(DIST / "Buddy", ignore_errors=True)
    if sys.platform == "win32":
        shutil.rmtree(DIST / "Buddy.exe", ignore_errors=True)
    spec = ROOT / "Buddy.spec"
    if spec.exists():
        spec.unlink()

    data_separator = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Buddy",
        "--add-data",
        f"knowledge{data_separator}knowledge",
        "--add-data",
        f"gui/assets{data_separator}gui/assets",
        "main.py",
    ]
    for package in ("googleapiclient", "google_auth_oauthlib", "msal", "playwright"):
        if importlib.util.find_spec(package):
            command[-1:-1] = ["--collect-all", package]
    run(command)

    artifact = DIST / "Buddy.exe" if sys.platform == "win32" else DIST / "Buddy"
    if not artifact.exists():
        raise SystemExit(f"PyInstaller did not create the expected bundle: {artifact}")
    archive_base = DIST / f"Buddy-{target_name()}-{APP_VERSION}"
    archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=DIST, base_dir=artifact.name))
    print(f"Created {archive.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
