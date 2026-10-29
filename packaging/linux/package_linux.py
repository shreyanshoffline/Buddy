"""Assemble an AppImage and Debian package from Buddy's Nuitka bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def make_appdir(bundle: Path, icons: Path, appdir: Path) -> None:
    shutil.rmtree(appdir, ignore_errors=True)
    (appdir / "usr" / "bin").mkdir(parents=True)
    shutil.copytree(bundle, appdir / "usr" / "bin" / bundle.name, symlinks=True)
    shutil.copy2(ROOT / "packaging" / "linux" / "buddy.desktop", appdir / "buddy.desktop")
    icon = icons / "hicolor" / "256x256" / "apps" / "buddy.png"
    shutil.copy2(icon, appdir / "buddy.png")
    (appdir / ".DirIcon").symlink_to("buddy.png")
    app_run = appdir / "AppRun"
    app_run.write_text(
        '#!/bin/sh\n'
        'HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'exec "$HERE/usr/bin/Buddy.dist/Buddy" "$@"\n',
        encoding="utf-8",
    )
    app_run.chmod(0o755)


def make_deb(bundle: Path, icons: Path, outdir: Path, version: str, architecture: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="buddy-deb-") as temporary:
        root = Path(temporary) / "root"
        app = root / "opt" / "buddy"
        shutil.copytree(bundle, app / bundle.name, symlinks=True)
        (root / "usr" / "bin").mkdir(parents=True)
        launcher = root / "usr" / "bin" / "buddy"
        launcher.write_text('#!/bin/sh\nexec /opt/buddy/Buddy.dist/Buddy "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
        desktop = root / "usr" / "share" / "applications" / "buddy.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "packaging" / "linux" / "buddy.desktop", desktop)
        desktop.write_text(desktop.read_text(encoding="utf-8").replace("Exec=buddy", "Exec=/usr/bin/buddy"), encoding="utf-8")
        icon = root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "buddy.png"
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icons / "hicolor" / "256x256" / "apps" / "buddy.png", icon)
        control = root / "DEBIAN" / "control"
        control.parent.mkdir(parents=True)
        control.write_text(
            f"Package: buddy\nVersion: {version}\nArchitecture: {architecture}\n"
            "Maintainer: Buddy Project\n"
            "Depends: libc6, libstdc++6, libgcc-s1, libx11-6, libxext6, libxrender1, "
            "libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, "
            "libxcb-render-util0, libxcb-xinerama0, libxkbcommon-x11-0, libgl1, libegl1, libdbus-1-3\n"
            "Description: Local-first desktop AI assistant\n",
            encoding="utf-8",
        )
        output = outdir / f"Buddy-{version}-linux-{architecture}.deb"
        run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(output)])
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--icons", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--outdir", type=Path, default=ROOT / "dist")
    parser.add_argument("--appimagetool", type=Path, required=True)
    parser.add_argument("--architecture", default=None)
    args = parser.parse_args()
    if not args.bundle.is_dir():
        raise SystemExit(f"Nuitka bundle not found: {args.bundle}")
    args.outdir.mkdir(parents=True, exist_ok=True)
    deb_arch = args.architecture or subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    appimage_arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(deb_arch, deb_arch)

    with tempfile.TemporaryDirectory(prefix="buddy-appimage-") as temporary:
        appdir = Path(temporary) / "Buddy.AppDir"
        make_appdir(args.bundle, args.icons, appdir)
        appimage = args.outdir / f"Buddy-{args.version}-linux-{appimage_arch}.AppImage"
        env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
        run([str(args.appimagetool), str(appdir), str(appimage)], env=env)

    deb = make_deb(args.bundle, args.icons, args.outdir, args.version, deb_arch)
    print(f"Created {appimage} and {deb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
