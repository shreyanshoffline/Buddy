"""Build Buddy's cross-platform Nuitka standalone bundle.

The release build intentionally uses ``--standalone`` instead of ``--onefile``:
the app starts faster, updates are easier to replace, and the bundle remains a
normal folder that users can inspect and back up.

On macOS this also merges the permission strings from ``packaging/Info.plist``
into the bundle and re-signs it (ad-hoc unless SIGN_IDENTITY is set), because
macOS terminates an app that touches the microphone without a usage string.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import plistlib
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


def finish_macos_bundle(bundle: Path) -> None:
    """Add permission strings + version to Info.plist, then re-sign the bundle."""
    plist_path = bundle / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    with (ROOT / "packaging" / "Info.plist").open("rb") as handle:
        ours = plistlib.load(handle)
    info.update({key: value for key, value in ours.items() if key != "CFBundleExecutable"})
    info["CFBundleVersion"] = info["CFBundleShortVersionString"] = APP_VERSION
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)

    identity = os.environ.get("SIGN_IDENTITY", "-")
    sign = ["codesign", "--force", "--deep", "--entitlements", str(ROOT / "packaging" / "Buddy.entitlements"),
            "--sign", identity]
    if identity != "-":
        sign += ["--options", "runtime"]
    run(sign + [str(bundle)])
    run(["codesign", "--verify", "--deep", "--strict", str(bundle)])


def make_archive(bundle: Path, archive_base: Path, macos: bool) -> Path:
    if macos:  # ditto keeps symlinks, permissions and signatures intact
        archive = Path(str(archive_base) + ".zip")
        archive.unlink(missing_ok=True)
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(bundle), str(archive)])
        return archive
    Path(str(archive_base) + ".zip").unlink(missing_ok=True)
    return Path(shutil.make_archive(str(archive_base), "zip", root_dir=bundle.parent, base_dir=bundle.name))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Buddy as a Nuitka standalone bundle.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the offline test suite.")
    parser.add_argument("--jobs", type=int, default=None, help="Parallel Nuitka C compiler jobs (default: Nuitka's CPU count).")
    args = parser.parse_args()
    if args.jobs is not None and args.jobs < 1:
        parser.error("--jobs must be a positive integer")

    if platform.system() not in {"Darwin", "Windows", "Linux"}:
        raise SystemExit("Nuitka packaging is supported on macOS, Windows, and Linux hosts.")
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "tests"])

    macos = platform.system() == "Darwin"
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    DIST.mkdir(exist_ok=True)
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
        # Packages that load data files at runtime and fail silently when missing.
        "--include-package-data=googleapiclient",  # Google API discovery documents
        "--include-package-data=certifi",          # HTTPS certificates for requests
        "--include-data-dir=" + str(ROOT / "knowledge") + "=knowledge",
        "--include-data-dir=" + str(ROOT / "gui" / "assets") + "=gui/assets",
    ]
    if args.jobs is not None:
        command.append(f"--jobs={args.jobs}")
    if macos:
        command += [
            "--macos-create-app-bundle",
            "--macos-app-name=Buddy",
            f"--macos-app-version={APP_VERSION}",
            "--macos-signed-app-name=com.hackclub.buddy",
        ]
        icons_dir = BUILD_ROOT.parent / "icons"
        run([sys.executable, str(ROOT / "packaging" / "make_icons.py"), "--out", str(icons_dir)])
        icns = icons_dir / "Buddy.icns"
        if icns:
            command.append(f"--macos-app-icon={icns}")
    command.append(str(ROOT / "main.py"))
    run(command)

    bundle = _find_bundle(BUILD_ROOT, macos)
    if not bundle.exists():
        raise SystemExit(f"Nuitka output bundle does not exist: {bundle}")
    if macos:
        expected_bundle = BUILD_ROOT / "Buddy.app"
        if bundle != expected_bundle:
            if expected_bundle.exists():
                shutil.rmtree(expected_bundle)
            bundle.rename(expected_bundle)
            bundle = expected_bundle
        finish_macos_bundle(bundle)
    archive_base = DIST / f"Buddy-{target_name()}-{APP_VERSION}"
    archive = make_archive(bundle, archive_base, macos)
    _checksum(archive)
    print(f"==> Created {archive.relative_to(ROOT)}")
    print(f"==> Created {archive.with_suffix(archive.suffix + '.sha256').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
