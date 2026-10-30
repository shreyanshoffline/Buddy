"""Offline checks for the shipping pipeline: universal merge, DMG art, installers, workflows,
platform-aware updater, first-run greeting, and the app's own --smoke-test."""
import os
import re
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packaging"))
sys.path.insert(0, str(ROOT / "packaging" / "macos"))

import merge_universal as mu  # noqa: E402

MACHO = struct.pack(">I", 0xCFFAEDFE)   # little-endian 64-bit Mach-O magic as stored on disk


def macho(tag: bytes) -> bytes:
    return MACHO + tag


def fake_archs(path: Path):
    data = path.read_bytes()
    out = set()
    if b"ARM" in data:
        out.add("arm64")
    if b"X86" in data:
        out.add("x86_64")
    return out


def fake_create(a: Path, b: Path, out: Path):
    out.write_bytes(macho(b"ARM" + b"X86"))


class MergeUniversalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.arm, self.intel, self.out = self.tmp / "arm", self.tmp / "intel", self.tmp / "out"

    def _write(self, root: Path, rel: str, data: bytes, mode=0o644):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.chmod(p, mode)

    def test_macho_detection(self):
        self._write(self.tmp, "a", macho(b"x"))
        self._write(self.tmp, "b", b"just text")
        self.assertTrue(mu.is_macho(self.tmp / "a"))
        self.assertFalse(mu.is_macho(self.tmp / "b"))

    def test_thin_binaries_are_merged_and_data_is_kept(self):
        for root, tag in ((self.arm, b"ARM"), (self.intel, b"X86")):
            self._write(root, "Contents/MacOS/Buddy", macho(tag), 0o755)
            self._write(root, "Contents/MacOS/libqt.dylib", macho(tag))
            self._write(root, "Contents/Resources/knowledge.md", b"same")
        self._write(self.intel, "Contents/Resources/intel_only.txt", b"extra")
        stats = mu.merge_trees(self.arm, self.intel, self.out, fake_archs, fake_create)
        self.assertEqual(stats["merged"], 2)
        self.assertEqual(stats["copied_from_intel"], 1)
        self.assertEqual(fake_archs(self.out / "Contents/MacOS/Buddy"), {"arm64", "x86_64"})
        if os.name != "nt":
            self.assertTrue(os.access(self.out / "Contents/MacOS/Buddy", os.X_OK))   # exec bit survives lipo
        self.assertTrue((self.out / "Contents/Resources/intel_only.txt").exists())

    def test_already_universal_binary_is_left_alone(self):
        for root in (self.arm, self.intel):
            self._write(root, "Contents/MacOS/fat.so", macho(b"ARMX86"))
        calls = []
        stats = mu.merge_trees(self.arm, self.intel, self.out, fake_archs, lambda *a: calls.append(a))
        self.assertEqual(stats["already_universal"], 1)
        self.assertEqual(calls, [])

    def test_binary_present_in_only_one_arch_is_a_hard_error(self):
        self._write(self.arm, "Contents/MacOS/Buddy", macho(b"ARM"))
        self._write(self.intel, "Contents/MacOS/Buddy", macho(b"X86"))
        self._write(self.arm, "Contents/MacOS/only_arm.so", macho(b"ARM"))
        with self.assertRaises(mu.MergeError) as ctx:
            mu.merge_trees(self.arm, self.intel, self.out, fake_archs, fake_create)
        self.assertIn("only_arm.so", str(ctx.exception))

    @unittest.skipIf(os.name == "nt", "symlinks need admin rights on Windows; the merge only runs on macOS")
    def test_symlinks_are_preserved_not_followed(self):
        for root, tag in ((self.arm, b"ARM"), (self.intel, b"X86")):
            self._write(root, "Fw/Versions/A/Qt", macho(tag))
            os.symlink("A", root / "Fw/Versions/Current")
        mu.merge_trees(self.arm, self.intel, self.out, fake_archs, fake_create)
        self.assertTrue((self.out / "Fw/Versions/Current").is_symlink())
        self.assertEqual(os.readlink(self.out / "Fw/Versions/Current"), "A")


class DmgTests(unittest.TestCase):
    def test_background_is_light_blue_and_correct_size(self):
        from PIL import Image, ImageStat
        one = Image.open(ROOT / "packaging/macos/dmg_background.png").convert("RGB")
        two = Image.open(ROOT / "packaging/macos/dmg_background@2x.png")
        self.assertEqual(one.size, (660, 400))
        self.assertEqual(two.size, (1320, 800))
        r, g, b = ImageStat.Stat(one).mean
        self.assertGreater(b, 200)           # bright
        self.assertGreater(b, r + 25)        # and clearly blue

    def test_settings_match_the_artwork(self):
        import dmg_background as art
        ns = {"defines": {"app": "/x/Buddy.app", "bg": "bg.png"}}
        exec((ROOT / "packaging/macos/dmg_settings.py").read_text(encoding="utf-8"), ns)
        self.assertEqual(ns["icon_locations"]["Buddy.app"], art.APP_XY)
        self.assertEqual(ns["icon_locations"]["Applications"], art.APPS_XY)
        self.assertEqual(ns["symlinks"], {"Applications": "/Applications"})
        self.assertEqual(ns["window_rect"][1], (art.W, art.H))


class DmgbuildAcceptsOurSettingsTests(unittest.TestCase):
    def test_real_dmgbuild_parses_the_settings(self):
        __import__("pytest").importorskip("dmgbuild.core") if sys.platform == "darwin" else None
        import platform
        with mock.patch.object(platform, "mac_ver", lambda *a, **k: ("14.0", ("", "", ""), "arm64")):
            try:
                from dmgbuild import core
            except ImportError:
                self.skipTest("dmgbuild not installed")
        settings = {"defines": {"app": "/x/Buddy.app", "bg": "bg.png", "icon": ""}}
        core.load_settings(str(ROOT / "packaging/macos/dmg_settings.py"), settings)
        self.assertEqual(settings["icon_locations"], {"Buddy.app": (165, 205), "Applications": (495, 205)})
        self.assertEqual(settings["files"], ["/x/Buddy.app"])
        self.assertEqual(settings["symlinks"], {"Applications": "/Applications"})


class IconTests(unittest.TestCase):
    def test_icons_are_generated(self):
        import make_icons
        from PIL import Image
        out = Path(tempfile.mkdtemp())
        ico = make_icons.make_ico(out / "Buddy.ico")
        sizes = Image.open(ico).info.get("sizes") or {(256, 256)}
        self.assertIn((256, 256), sizes)
        pngs = make_icons.make_linux_pngs(out / "icons")
        self.assertEqual({Image.open(p).size[0] for p in pngs}, set(make_icons.LINUX_SIZES))


class InstallerFileTests(unittest.TestCase):
    def test_inno_script(self):
        text = (ROOT / "packaging/windows/Buddy.iss").read_text(encoding="utf-8")
        for needle in ("AppId={{", "MinVersion=10.0", "x64compatible", "Buddy-Setup-{#AppVersion}-x64",
                       r"build\bundle\Buddy", "PrivilegesRequired=lowest", "[Icons]"):
            self.assertIn(needle, text)

    def test_desktop_file_and_launcher(self):
        desktop = (ROOT / "packaging/linux/buddy.desktop").read_text(encoding="utf-8")
        for key in ("Type=Application", "Name=Buddy", "Exec=buddy", "Icon=buddy", "Categories="):
            self.assertIn(key, desktop)
        self.assertIn("QT_QPA_PLATFORM=xcb", (ROOT / "packaging/linux/buddy-launcher.sh").read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt" or not __import__("shutil").which("bash"), "Unix shell unavailable")
    def test_shell_scripts_parse(self):
        for script in ("make_deb.sh", "make_appimage.sh", "buddy-launcher.sh"):
            result = subprocess.run(["bash", "-n", f"packaging/linux/{script}"], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_deb_depends_on_qt_runtime_libs(self):
        text = (ROOT / "packaging/linux/make_deb.sh").read_text(encoding="utf-8")
        for lib in ("libxcb-cursor0", "libegl1", "libxkbcommon-x11-0"):
            self.assertIn(lib, text)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        yaml = __import__("pytest").importorskip("yaml")
        self.text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.release = yaml.safe_load(self.text)
        self.jobs = self.release["jobs"]

    def test_jobs_cover_every_platform_and_a_final_gate(self):
        self.assertTrue({"mac", "windows", "linux", "final-check", "release"} <= set(self.jobs))
        self.assertNotIn("mac-universal", self.jobs)           # per-CPU DMGs; no fragile merge in the pipeline

    def test_each_mac_cpu_builds_its_own_finished_dmg(self):
        matrix = self.jobs["mac"]["strategy"]["matrix"]["include"]
        self.assertEqual({(m["runner"], m["cpu"], m["label"]) for m in matrix},
                         {("macos-15", "arm64", "apple-silicon"), ("macos-15-intel", "x86_64", "intel")})
        steps = "\n".join(str(st.get("run", "")) for st in self.jobs["mac"]["steps"])
        self.assertIn("packaging/macos/make_dmg.py", steps)
        self.assertIn("packaging/macos/verify_dmg.sh", steps)
        self.assertIn("-macos-${{ matrix.label }}.dmg", steps)

    def test_dmg_is_uploaded_not_the_raw_app(self):
        upload = [st for st in self.jobs["mac"]["steps"] if "upload-artifact" in str(st.get("uses", ""))][0]
        self.assertIn("dist/*.dmg", upload["with"]["path"])
        self.assertNotIn("Buddy.app", upload["with"]["path"])

    def test_release_builds_skip_tests_but_keep_the_smoke_test(self):
        invocations = [l for l in self.text.splitlines() if "packaging/build_nuitka.py" in l]
        self.assertEqual(len(invocations), 3)      # mac (x2 via matrix), windows, linux
        for line in invocations:
            self.assertIn("--skip-tests", line)
            self.assertIn("--smoke-test", line)

    def test_python_is_pinned_to_312_and_runners_are_pinned(self):
        self.assertEqual(self.release["env"]["PYTHON_VERSION"], "3.12")
        self.assertNotIn("ubuntu-latest", self.text)
        self.assertNotIn("actions/checkout@v4", self.text)
        self.assertNotIn("actions/setup-python@v5", self.text)

    def test_every_referenced_repo_file_exists(self):
        for rel in set(re.findall(r"(packaging/[\w./-]+\.(?:py|sh|iss|txt))", self.text)):
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_only_tags_publish_and_the_gate_checks_every_final_file(self):
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", self.jobs["release"]["if"])
        self.assertEqual(self.jobs["release"]["needs"], ["final-check"])
        for name in ("macos-apple-silicon.dmg", "macos-intel.dmg", "Setup-${VERSION}-x64.exe", "linux-x86_64.AppImage",
                     "linux-amd64.deb"):
            self.assertIn(name, self.text)

    def test_windows_installer_is_installed_launched_and_uninstalled_in_ci(self):
        steps = "\n".join(str(st.get("run", "")) for st in self.jobs["windows"]["steps"])
        for needle in ("/VERYSILENT", "Start Menu", "unins000.exe", "--smoke-out"):
            self.assertIn(needle, steps)

    def test_linux_packages_are_launched_in_ci(self):
        steps = "\n".join(str(st.get("run", "")) for st in self.jobs["linux"]["steps"])
        self.assertIn("--appimage-extract-and-run", steps)
        self.assertIn("apt-get install -y \"./$DEB\"", steps)
        self.assertIn("libegl1", steps)

    def test_no_linux_arm64_job_and_compiler_cache_is_persisted(self):
        self.assertNotIn("linux-arm64", self.jobs)             # its generated code overflows AArch64 branch range
        self.assertIn("NUITKA_CACHE_DIR", self.text)
        self.assertEqual(self.text.count("actions/cache/restore@v4"), 3)
        self.assertEqual(self.text.count("actions/cache/save@v4"), 3)

    def test_playwright_node_is_not_included_twice_on_macos_and_linux(self):
        import build_nuitka
        for system, expect in (("Darwin", True), ("Linux", True), ("Windows", False)):
            with mock.patch.object(build_nuitka.platform, "system", lambda s=system: s):
                cmd = build_nuitka.nuitka_command({"ico": Path("x.ico"), "icns": Path("x.icns")})
            self.assertEqual("--noinclude-data-files=playwright/driver/node" in cmd, expect, system)


class BuildScriptTests(unittest.TestCase):
    def setUp(self):
        import build_nuitka
        self.b = build_nuitka

    def test_python_and_pyqt_guards(self):
        with mock.patch.object(sys, "version_info", (3, 14, 0, "final", 0)):
            with self.assertRaises(SystemExit) as ctx:
                self.b.preflight(False, False)
            self.assertIn("3.12", str(ctx.exception))
        with mock.patch.object(self.b.importlib.util, "find_spec", lambda name: object() if name == "PyQt6" else None), \
                mock.patch.object(sys, "version_info", (3, 12, 3, "final", 0)):
            with self.assertRaises(SystemExit) as ctx:
                self.b.preflight(False, False)
            self.assertIn("PyQt6", str(ctx.exception))

    def test_command_contains_the_essentials(self):
        icons = {"ico": Path("Buddy.ico"), "icns": Path("Buddy.icns")}
        for system, expect in (("Darwin", "--macos-create-app-bundle"), ("Windows", "--windows-console-mode=disable")):
            with mock.patch.object(self.b.platform, "system", lambda s=system: s):
                cmd = self.b.nuitka_command(icons)
            self.assertIn(expect, cmd)
            self.assertIn("--standalone", cmd)
            self.assertIn("--enable-plugin=pyside6", cmd)
            self.assertIn("--include-package=openrouter", cmd)
            self.assertIn("--nofollow-import-to=PyQt6", cmd)
            self.assertNotIn("--onefile", cmd)
            self.assertTrue(any(c.startswith("--include-data-dir=") and c.endswith("=knowledge") for c in cmd))

    def test_info_plist_gets_version_microphone_text_and_icon(self):
        import plistlib
        bundle = Path(tempfile.mkdtemp()) / "Buddy.app"
        (bundle / "Contents").mkdir(parents=True)
        (bundle / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Buddy", "CFBundleName": "main"}))
        icons = Path(tempfile.mkdtemp())
        (icons / "Buddy.icns").write_bytes(b"icns")
        with mock.patch.object(self.b, "ICONS", icons):
            self.b.merge_plist(bundle)
        info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleShortVersionString"], self.b.APP_VERSION)
        self.assertEqual(info["CFBundleExecutable"], "Buddy")
        self.assertEqual(info["CFBundleIdentifier"], "com.hackclub.buddy")
        self.assertTrue(info["NSMicrophoneUsageDescription"])
        self.assertEqual(info["CFBundleIconFile"], "Buddy.icns")
        self.assertTrue((bundle / "Contents" / "Resources" / "Buddy.icns").exists())

    def test_tests_and_smoke_use_an_isolated_data_dir(self):
        env = self.b.isolated_env()
        self.assertTrue(Path(env["BUDDY_DATA_DIR"]).exists())


class UpdaterTests(unittest.TestCase):
    ASSETS = [{"name": "Buddy-Setup-0.9.8-x64.exe"}, {"name": "Buddy-0.9.8-linux-x86_64.AppImage"},
              {"name": "Buddy-0.9.8-macos-intel.dmg"}, {"name": "Buddy-0.9.8-macos-apple-silicon.dmg"},
              {"name": "Buddy-macos-arm64-0.9.8.zip"}, {"name": "Buddy-macos-x86_64-0.9.8.zip"},
              {"name": "Buddy-macos-x86_64-0.9.8.zip.sha256"}]

    def test_only_macos_gets_the_auto_updatable_zip(self):
        from core import updater
        self.assertEqual(updater.pick_asset(self.ASSETS, "macos", machine="arm64")["name"], "Buddy-macos-arm64-0.9.8.zip")
        self.assertEqual(updater.pick_asset(self.ASSETS, "macos", machine="x86_64")["name"], "Buddy-macos-x86_64-0.9.8.zip")
        self.assertIsNone(updater.pick_asset(self.ASSETS, "windows"))
        self.assertIsNone(updater.pick_asset(self.ASSETS, "linux"))


class GreetingTests(unittest.TestCase):
    def _greet(self, profile):
        from gui.main_window import BuddyWindow
        with mock.patch("gui.main_window.core.get_profile", lambda: profile):
            return BuddyWindow._random_greeting(types.SimpleNamespace())

    def test_first_run_welcomes_by_first_name(self):
        self.assertEqual(self._greet({"name": "Shreyansh Patra"}), "Welcome to Buddy, Shreyansh! 👋 What should we do first?")
        self.assertIn("Welcome to Buddy!", self._greet({}))

    def test_returning_user_is_greeted_by_name(self):
        seen = {self._greet({"name": "Shrey", "has_seen_intro_tip": True}) for _ in range(60)}
        self.assertTrue(all("Shrey" in g for g in seen))
        self.assertFalse(any("Welcome to Buddy" in g for g in seen))


class DmgVerifyScriptTests(unittest.TestCase):
    def test_script_checks_what_users_experience(self):
        text = (ROOT / "packaging/macos/verify_dmg.sh").read_text(encoding="utf-8")
        for needle in ("Applications shortcut", "NSMicrophoneUsageDescription", "lipo -archs", "codesign --verify",
                       "--smoke-out", "ditto", ".background"):
            self.assertIn(needle, text)

    @unittest.skipIf(os.name == "nt" or not __import__("shutil").which("bash"), "Unix shell unavailable")
    def test_script_parses(self):
        self.assertEqual(subprocess.run(["bash", "-n", "packaging/macos/verify_dmg.sh"], cwd=ROOT).returncode, 0)


class SmokeTestFlagTests(unittest.TestCase):
    def test_result_is_written_to_a_file_for_the_console_less_windows_build(self):
        out = Path(tempfile.mkdtemp()) / "result.txt"
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", BUDDY_DATA_DIR=tempfile.mkdtemp(), BUDDY_SMOKE_TEST="1")
        subprocess.run([sys.executable, str(ROOT / "main.py"), "--smoke-test", f"--smoke-out={out}"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
        self.assertIn("SMOKE OK", out.read_text(encoding="utf-8"))

    def test_app_starts_and_exits_cleanly(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", BUDDY_DATA_DIR=tempfile.mkdtemp())
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--smoke-test"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SMOKE OK", result.stdout)


class WindowsCompatTests(unittest.TestCase):
    """Windows bugs that CI on Linux can still catch, because they are logic, not OS calls."""

    def test_unix_system_paths_cannot_sneak_through_a_windows_drive(self):
        from tools import code_agent as c
        # "/etc/hosts" resolves to "D:/etc/hosts" on Windows: must still be refused
        for raw, resolved in (("/etc/hosts", "D:/etc/hosts"), (r"\etc\hosts", "D:/etc/hosts"),
                              ("/usr/bin/python", "C:/usr/bin/python"), (r"C:\Windows\System32\x.dll", "C:/Windows/System32/x.dll"),
                              (r"C:\Program Files\App\a.exe", "C:/Program Files/App/a.exe"),
                              ("~/.ssh/id_rsa", "C:/Users/me/.ssh/id_rsa")):
            self.assertTrue(c._is_denied(raw, resolved), raw)
        for raw, resolved in (("proj/app.py", "C:/Users/me/proj/app.py"), ("/home/me/proj", "/home/me/proj"),
                              (r"D:\work\buddy", "D:/work/buddy")):
            self.assertFalse(c._is_denied(raw, resolved), raw)

    def test_python_path_is_quoted_for_cmd_exe_not_posix_shell(self):
        from tools import code_agent as c
        win = c._quote_arg(r"C:\Program Files\Python312\python.exe", windows=True)
        self.assertEqual(win, '"C:\\Program Files\\Python312\\python.exe"')   # double quotes; cmd.exe cannot read '...'
        self.assertNotIn("'", win)
        self.assertEqual(c._quote_arg("/usr/bin/python3", windows=False), "/usr/bin/python3")

    def test_windows_paths_are_shown_as_typed(self):
        from core.call_format import format_call
        shown = format_call("code_write", {"path": r"C:\Users\me\game.py", "content": "x"})
        self.assertIn(r'path="C:\Users\me\game.py"', shown)      # not C:\\Users\\...

    def test_no_posix_only_strftime_flags_anywhere(self):
        bad = []
        for folder in ("core", "tools", "gui", "storage", "backend"):
            for f in (ROOT / folder).rglob("*.py"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"strftime\([^)]*%-[a-zA-Z]", text):
                    bad.append(str(f.relative_to(ROOT)))
        self.assertEqual(bad, [], "%-d / %-I crash on Windows; use .lstrip('0') or .day")

    def test_calendar_confirmation_has_no_leading_zeros(self):
        from tools import apple_tools
        with mock.patch.object(apple_tools, "_run_applescript", lambda s, timeout=15: "Home"):
            out = apple_tools.apple_calendar_create_event("X", "2026-11-14T07:00:00", "2026-11-14T20:00:00")
        self.assertIn("Sat Nov 14, 7:00 AM to 8:00 PM", out)

    def test_code_agent_has_no_posix_only_calls_outside_helpers(self):
        text = (ROOT / "tools/code_agent.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("killpg"), 1)               # only inside _kill_tree
        self.assertNotIn('"bin" / "pip"', text)


if __name__ == "__main__":
    unittest.main()
