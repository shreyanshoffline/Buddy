"""Merge an arm64 Buddy.app and an x86_64 Buddy.app into ONE universal Buddy.app.

Why not `nuitka --macos-target-arch=universal`? That needs every compiled dependency to ship a
universal2 wheel, and several (pydantic-core, for one) do not. Instead CI builds each
architecture natively (macos-15 = Apple Silicon, macos-15-intel = Intel) and this script glues
them with `lipo`, file by file:

  * Mach-O in both apps      -> lipo -create (thin + thin = universal)
  * already-universal Mach-O -> kept as is
  * Mach-O in only ONE app   -> hard error (the other CPU would crash on it)
  * anything else            -> taken from the arm64 app (Intel-only extras are copied in)

    python packaging/macos/merge_universal.py --arm A/Buddy.app --intel B/Buddy.app --out dist/Buddy.app [--sign "-"]
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
ENTITLEMENTS = ROOT / "packaging" / "Buddy.entitlements"
MACHO_MAGICS = {0xFEEDFACE, 0xFEEDFACF, 0xCEFAEDFE, 0xCFFAEDFE, 0xCAFEBABE, 0xBEBAFECA, 0xCAFEBABF, 0xBFBAFECA}


class MergeError(RuntimeError):
    pass


def is_macho(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            head = handle.read(4)
    except OSError:
        return False
    return len(head) == 4 and struct.unpack(">I", head)[0] in MACHO_MAGICS


def lipo_archs(path: Path) -> set[str]:
    result = subprocess.run(["lipo", "-archs", str(path)], capture_output=True, text=True)
    return set(result.stdout.split()) if result.returncode == 0 else set()


def lipo_create(arm: Path, intel: Path, out: Path) -> None:
    subprocess.run(["lipo", "-create", str(arm), str(intel), "-output", str(out)], check=True)


def _files(root: Path) -> Iterable[Path]:
    for dirpath, _dirs, names in os.walk(root):          # os.walk does not follow symlinked dirs
        for name in names:
            yield (Path(dirpath) / name).relative_to(root)


def merge_trees(arm: Path, intel: Path, out: Path,
                get_archs: Callable[[Path], set[str]] = lipo_archs,
                create: Callable[[Path, Path, Path], None] = lipo_create) -> dict:
    """Build `out` from the two app trees. Returns counts for the log; raises MergeError on mismatches."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(arm, out, symlinks=True)              # arm64 app is the base (keeps symlinks/perms)

    stats = {"merged": 0, "already_universal": 0, "copied_from_intel": 0, "differing_data": 0}
    problems: list[str] = []
    arm_files, intel_files = set(_files(arm)), set(_files(intel))

    for rel in sorted(arm_files):
        a, i, o = arm / rel, intel / rel, out / rel
        if a.is_symlink():
            continue
        if is_macho(a):
            if i.is_symlink() or not i.exists() or not is_macho(i):
                problems.append(f"only in arm64 app: {rel}")
                continue
            a_arch, i_arch = get_archs(a), get_archs(i)
            if {"arm64", "x86_64"} <= a_arch and {"arm64", "x86_64"} <= i_arch:
                stats["already_universal"] += 1
                continue
            mode = a.stat().st_mode
            create(a, i, o)
            os.chmod(o, mode)
            stats["merged"] += 1
        elif i.exists() and not i.is_symlink() and a.read_bytes() != i.read_bytes():
            stats["differing_data"] += 1                   # e.g. build ids; arm64 copy wins

    for rel in sorted(intel_files - arm_files):
        i, o = intel / rel, out / rel
        if i.is_symlink():
            o.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.readlink(i), o)
            continue
        if is_macho(i):
            problems.append(f"only in Intel app: {rel}")
            continue
        o.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(i, o)
        stats["copied_from_intel"] += 1

    if problems:
        shown = "\n  ".join(problems[:25])
        raise MergeError(f"{len(problems)} binaries exist in only one architecture:\n  {shown}")
    return stats


def sign(app: Path, identity: str = "-") -> None:
    """lipo invalidates signatures, so sign the finished bundle again (ad-hoc by default)."""
    cmd = ["codesign", "--force", "--deep", "--sign", identity, "--entitlements", str(ENTITLEMENTS)]
    if identity != "-":
        cmd += ["--options", "runtime", "--timestamp"]
    subprocess.run(cmd + [str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arm", required=True, type=Path)
    parser.add_argument("--intel", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sign", default=os.environ.get("SIGN_IDENTITY", "-"),
                        help='codesign identity ("-" = ad-hoc, the default)')
    args = parser.parse_args(argv)

    try:
        stats = merge_trees(args.arm, args.intel, args.out)
    except MergeError as exc:
        print(f"MERGE FAILED: {exc}", file=sys.stderr)
        return 1
    print("merged:", stats)

    exe = next((args.out / "Contents" / "MacOS").glob("Buddy"), None)
    if exe is not None:
        archs = lipo_archs(exe)
        print("main executable architectures:", sorted(archs))
        if not {"arm64", "x86_64"} <= archs:
            print("MERGE FAILED: main executable is not universal", file=sys.stderr)
            return 1
    sign(args.out, args.sign)
    print(f"universal app ready: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
