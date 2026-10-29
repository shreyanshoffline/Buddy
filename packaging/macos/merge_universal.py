"""Merge native arm64 and x86_64 Nuitka app bundles into a universal app."""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path


def is_macho(path: Path) -> bool:
    try:
        result = subprocess.run(["file", "-b", str(path)], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return "Mach-O" in result.stdout


def merge(arm: Path, intel: Path, output: Path) -> None:
    arm = arm.resolve()
    intel = intel.resolve()
    app_rel = Path("Contents")
    if arm.suffix != ".app" or intel.suffix != ".app":
        raise SystemExit("Both inputs must be .app bundles")
    shutil.rmtree(output, ignore_errors=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(arm, output, symlinks=True)

    for source in intel.rglob("*"):
        relative = source.relative_to(intel)
        target = output / relative
        if source.is_dir() or source.is_symlink():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and is_macho(source) and is_macho(target):
            with tempfile.NamedTemporaryFile(prefix="buddy-universal-") as temp:
                subprocess.run(
                    ["lipo", "-create", str(target), str(source), "-output", temp.name],
                    check=True,
                )
                shutil.copy2(temp.name, target)
        elif not target.exists():
            shutil.copy2(source, target)

    plist = output / app_rel / "Info.plist"
    with plist.open("rb") as handle:
        info = plistlib.load(handle)
    info["LSArchitecturePriority"] = ["arm64", "x86_64"]
    with plist.open("wb") as handle:
        plistlib.dump(info, handle)

    executable = info.get("CFBundleExecutable")
    if not executable:
        raise SystemExit(f"Missing CFBundleExecutable in {plist}")
    binary = output / app_rel / "MacOS" / executable
    result = subprocess.run(["lipo", "-archs", str(binary)], check=True, capture_output=True, text=True)
    architectures = set(result.stdout.split())
    if not {"arm64", "x86_64"}.issubset(architectures):
        raise SystemExit(f"Universal executable missing architectures: {result.stdout.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm64", required=True, type=Path)
    parser.add_argument("--x86-64", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    merge(args.arm64, args.x86_64, args.output)
    print(f"Created universal app at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
