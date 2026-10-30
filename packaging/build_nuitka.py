"""Build Buddy with Nuitka (--standalone) for the current OS and CPU.

    python packaging/build_nuitka.py --smoke-test

Output, always in the same place so every installer script can find it:
    build/bundle/Buddy.app      (macOS)
    build/bundle/Buddy/         (Windows, Linux: folder with Buddy.exe / Buddy inside)

Installers are made from that bundle by:
    packaging/macos/make_dmg.py                       -> one DMG per Mac CPU
    packaging/windows/Buddy.iss (Inno Setup)           -> Buddy-Setup-<ver>-x64.exe
    packaging/linux/make_appimage.sh / make_deb.sh     -> .AppImage and .deb

--standalone (not --onefile) is deliberate: it starts fast, never unpacks to a temp folder,
and is what the installers wrap. Users never see the folder; they get a real installer.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_ROOT = ROOT / "build" / "nuitka"
STAGE = ROOT / "build" / "bundle"
ICONS = ROOT / "build" / "icons"
DIST = ROOT / "dist"
LOGO = ROOT / "gui" / "assets" / "Buddy_Logo_Beta.png"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))
from version import APP_VERSION  # noqa: E402

COMPANY = "Shrey Industries"
BUNDLE_ID = "com.hackclub.buddy"


def run(command: list, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print("==>", " ".join(str(item) for item in command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=check, env=env)


def target_name() -> str:
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system(), platform.system().lower())


def cpu_name() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)


def preflight(allow_any_python: bool, allow_pyqt: bool) -> None:
    """Catch the two environment problems that waste an hour of compiling."""
    if sys.version_info[:2] != (3, 12) and not allow_any_python:
        raise SystemExit(
            f"Python {sys.version_info[0]}.{sys.version_info[1]} detected. Build with Python 3.12 "
            "(what CI uses; Nuitka treats 3.14 as experimental and compiles for ages).\n"
            "  python3.12 -m venv .venv-build && . .venv-build/bin/activate\n"
            "Pass --allow-any-python to override.")
    conflicts = [name for name in ("PyQt5", "PyQt6") if importlib.util.find_spec(name)]
    if conflicts and not allow_pyqt:
        raise SystemExit(
            f"{', '.join(conflicts)} is installed next to PySide6; Nuitka warns this can break the app at runtime.\n"
            "Build in a clean venv: python3.12 -m venv .venv-build && pip install -r requirements.txt "
            "-r packaging/requirements-build.txt\nPass --allow-pyqt to override.")
    if importlib.util.find_spec("nuitka") is None:
        raise SystemExit("Nuitka is not installed: pip install -r packaging/requirements-build.txt")


def isolated_env() -> dict:
    """Tests and the smoke test must never touch (or need write access to) the real user data folder."""
    env = dict(os.environ)
    env["BUDDY_DATA_DIR"] = tempfile.mkdtemp(prefix="buddy-build-data-")
    env["BUDDY_SMOKE_TEST"] = "1"      # never touch the real Keychain / user data from a build
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def make_icons() -> dict:
    import make_icons as icons
    ICONS.mkdir(parents=True, exist_ok=True)
    found = {"ico": icons.make_ico(ICONS / "Buddy.ico")}
    found["png"] = icons.make_linux_pngs(ICONS / "icons")
    if target_name() == "macos":
        found["icns"] = icons.make_icns(ICONS / "Buddy.icns")
    return found


def _find_bundle(output_dir: Path, macos: bool) -> Path:
    for name in (["Buddy.app", "main.app"] if macos else ["Buddy.dist", "main.dist"]):
        if (output_dir / name).exists():
            return output_dir / name
    found = sorted(output_dir.glob("*.app" if macos else "*.dist"))
    if len(found) == 1:
        return found[0]
    raise SystemExit(f"Nuitka did not create the expected bundle in {output_dir}; found {found or 'nothing'}")


def nuitka_command(icons: dict, jobs: int | None = None) -> list:
    macos, windows = target_name() == "macos", target_name() == "windows"
    command = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--remove-output",
        "--assume-yes-for-downloads",
        f"--jobs={jobs or os.cpu_count() or 2}",
        "--output-dir=" + str(BUILD_ROOT),
        "--output-filename=Buddy",
        # the app's own code
        "--include-package=backend", "--include-package=core", "--include-package=gui",
        "--include-package=openrouter", "--include-package=storage", "--include-package=tools",
        # never compile test tooling or a second Qt binding into the app
        "--nofollow-import-to=tests", "--nofollow-import-to=pytest", "--nofollow-import-to=setuptools",
        "--nofollow-import-to=tkinter", "--nofollow-import-to=PyQt5", "--nofollow-import-to=PyQt6",
        # packages that load data files at runtime and fail silently when missing
        "--include-package-data=googleapiclient",
        "--include-package-data=certifi",
        "--include-package-data=playwright",
        "--include-data-dir=" + str(ROOT / "knowledge") + "=knowledge",
        "--include-data-dir=" + str(ROOT / "gui" / "assets") + "=gui/assets",
    ]
    if not windows:
        # macOS/Linux: the driver's extensionless `node` binary was added twice, once as a data file by
        # --include-package-data=playwright and once as an executable by Nuitka's playwright plugin:
        #   FATAL: data file ... 'playwright/driver/node' conflicts with exe 'playwright/driver/node'
        # (Windows skips it because node.exe is recognised as a binary). Keep only the plugin's copy.
        command.append("--noinclude-data-files=playwright/driver/node")
    if macos:
        command += ["--macos-create-app-bundle", "--macos-app-name=Buddy", f"--macos-app-version={APP_VERSION}",
                    f"--macos-signed-app-name={BUNDLE_ID}"]
        if icons.get("icns"):
            command.append(f"--macos-app-icon={icons['icns']}")
    if windows:
        command += ["--windows-console-mode=disable", f"--windows-icon-from-ico={icons['ico']}",
                    f"--company-name={COMPANY}", "--product-name=Buddy", "--file-description=Buddy AI assistant",
                    f"--file-version={APP_VERSION}.0", f"--product-version={APP_VERSION}.0"]
    command.append(str(ROOT / "main.py"))
    return command


def merge_plist(bundle: Path) -> None:
    """Merge our permission strings + version into Nuitka's Info.plist and guarantee the Dock/Finder icon."""
    plist_path = bundle / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    with (ROOT / "packaging" / "Info.plist").open("rb") as handle:
        ours = plistlib.load(handle)
    info.update({key: value for key, value in ours.items() if key != "CFBundleExecutable"})
    info["CFBundleVersion"] = info["CFBundleShortVersionString"] = APP_VERSION
    resources = bundle / "Contents" / "Resources"
    resources.mkdir(parents=True, exist_ok=True)
    icon = resources / "Buddy.icns"
    if not icon.exists() and (ICONS / "Buddy.icns").exists():
        shutil.copy2(ICONS / "Buddy.icns", icon)
    existing = info.get("CFBundleIconFile")
    if icon.exists() and not (existing and ((resources / existing).exists() or (resources / (existing + ".icns")).exists())):
        info["CFBundleIconFile"] = "Buddy.icns"
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)


def finish_macos_bundle(bundle: Path) -> None:
    """Fix Info.plist, then sign (ad-hoc unless SIGN_IDENTITY is set)."""
    merge_plist(bundle)
    identity = os.environ.get("SIGN_IDENTITY", "-")
    sign = ["codesign", "--force", "--deep", "--entitlements", str(ROOT / "packaging" / "Buddy.entitlements"),
            "--sign", identity]
    if identity != "-":
        sign += ["--options", "runtime", "--timestamp"]
    run(sign + [str(bundle)])
    run(["codesign", "--verify", "--deep", "--strict", str(bundle)])


def bundle_executable(bundle: Path) -> Path:
    if target_name() == "macos":
        return bundle / "Contents" / "MacOS" / "Buddy"
    return bundle / ("Buddy.exe" if target_name() == "windows" else "Buddy")


def smoke_test(bundle: Path) -> None:
    """Launch the BUILT app with --smoke-test. Catches missing Qt plugins/assets before users do.
    The result is read from a file because the Windows build has no console to print to.
    On headless Linux run this under xvfb-run."""
    exe = bundle_executable(bundle)
    out_file = Path(tempfile.mkdtemp(prefix="buddy-smoke-")) / "result.txt"
    print(f"==> smoke test: {exe}", flush=True)
    result = subprocess.run([str(exe), "--smoke-test", f"--smoke-out={out_file}"], cwd=bundle.parent,
                            env=isolated_env(), capture_output=True, text=True, timeout=240)
    verdict = (out_file.read_text(encoding="utf-8") if out_file.exists() else
               "(no result file written: the app exited before the smoke test ran. Read the output above; "
               "this is almost always an import-time crash or a library calling sys.exit())")
    print(result.stdout, result.stderr, verdict, sep="\n")
    if result.returncode != 0 or "SMOKE OK" not in verdict:
        raise SystemExit(f"Smoke test FAILED (exit code {result.returncode}): {verdict.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Buddy as a Nuitka standalone bundle.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the offline test suite.")
    parser.add_argument("--smoke-test", action="store_true", help="Launch the finished app once to prove it starts.")
    parser.add_argument("--zip", action="store_true", help="Also write dist/parts/Buddy-<os>-<cpu>-<ver>.zip (macOS CI uses this).")
    parser.add_argument("--jobs", type=int, default=0, help="Compiler parallelism (default: all CPUs).")
    parser.add_argument("--allow-any-python", action="store_true")
    parser.add_argument("--allow-pyqt", action="store_true")
    args = parser.parse_args()

    if target_name() not in {"macos", "windows", "linux"}:
        raise SystemExit("Nuitka packaging is supported on macOS, Windows, and Linux hosts.")
    preflight(args.allow_any_python, args.allow_pyqt)
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q", "tests"], env=isolated_env())

    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(exist_ok=True)

    icons = make_icons()
    run(nuitka_command(icons, args.jobs or None))

    macos = target_name() == "macos"
    built = _find_bundle(BUILD_ROOT, macos)
    final = STAGE / ("Buddy.app" if macos else "Buddy")
    shutil.copytree(built, final, symlinks=True)
    if macos:
        finish_macos_bundle(final)
    if args.smoke_test:
        smoke_test(final)

    if args.zip:
        parts = DIST / "parts"
        parts.mkdir(exist_ok=True)
        base = parts / f"Buddy-{target_name()}-{cpu_name()}-{APP_VERSION}"
        if macos:  # ditto keeps symlinks, permissions and signatures intact
            run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(final), str(base) + ".zip"])
        else:
            shutil.make_archive(str(base), "zip", root_dir=final.parent, base_dir=final.name)
        print(f"==> Created {base}.zip")
    print(f"==> Bundle ready: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
