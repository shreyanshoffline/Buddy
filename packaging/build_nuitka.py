"""Build Buddy's cross-platform Nuitka standalone bundle.

The release build intentionally uses ``--standalone`` instead of ``--onefile``:
the app starts faster, updates are easier to replace, and the bundle remains a
normal folder that users can inspect and back up. PyInstaller scripts remain
available as the fallback path.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_ROOT = ROOT / "build" / "nuitka"
DIST = ROOT / "dist"

sys.path.insert(0, str(ROOT))
from version import APP_VERSION  # noqa: E402


def run(command: list[str]) -> None:
    print("==>", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=ROOT, check=True)


def target_name() -> str:
    system = platform.system()
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(system, system.lower())


def _bundle_candidates(output_dir: Path, macos: bool) -> list[Path]:
    if macos:
        return [output_dir / "Buddy.app", output_dir / "main.app"]
    return [output_dir / "Buddy.dist", output_dir / "main.dist"]


def _find_bundle(output_dir: Path, macos: bool) -> Path:
    for candidate in _bundle_candidates(output_dir, macos):
        if candidate.exists():
            return candidate
    candidates = sorted(path for path in output_dir.glob("*.dist" if not macos else "*.app"))
    if len(candidates) == 1:
        return candidates[0]
    found = ", ".join(str(path) for path in candidates) or "nothing"
    raise SystemExit(f"Nuitka did not create the expected standalone bundle; found {found}")


def _checksum(path: Path) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest.hexdigest()}  {path.name}\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Buddy as a Nuitka standalone bundle.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the offline test suite.")
    args = parser.parse_args()

    if platform.system() not in {"Darwin", "Windows", "Linux"}:
        raise SystemExit("Nuitka packaging is supported on macOS, Windows, and Linux hosts.")
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "tests"])

    macos = platform.system() == "Darwin"
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    DIST.mkdir(exist_ok=True)
    for old in DIST.glob("Buddy-*"):
        if old.is_file():
            old.unlink()
        elif old.is_dir():
            shutil.rmtree(old)

    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--output-dir=" + str(BUILD_ROOT),
        "--output-filename=Buddy",
        "--include-package=backend",
        "--include-package=core",
        "--include-package=gui",
        "--include-package=storage",
        "--include-package=tools",
        "--include-data-dir=" + str(ROOT / "knowledge") + "=knowledge",
        "--include-data-dir=" + str(ROOT / "gui" / "assets") + "=gui/assets",
    ]
    if macos:
        command += [
            "--macos-create-app-bundle",
            "--macos-app-name=Buddy",
            f"--macos-app-version={APP_VERSION}",
        ]
    command.append(str(ROOT / "main.py"))
    run(command)

    bundle = _find_bundle(BUILD_ROOT, macos)
    archive_base = DIST / f"Buddy-{target_name()}-{APP_VERSION}"
    archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=bundle.parent, base_dir=bundle.name))
    _checksum(archive)
    print(f"==> Created {archive.relative_to(ROOT)}")
    print(f"==> Created {archive.with_suffix(archive.suffix + '.sha256').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
