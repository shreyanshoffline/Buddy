"""Buddy's single cross-platform entry point."""
import os
import sys

# A packaged app has no project folder, so also read settings from the per-user
# data folder (e.g. ~/Library/Application Support/Buddy/.env). Loaded before the
# other imports because several modules read environment variables on import.
try:
    from dotenv import load_dotenv
    from tools.paths import data_dir
    load_dotenv(data_dir("") / ".env")
except Exception:
    pass

from PySide6.QtWidgets import QApplication

try:
    from gui.main_window import BuddyWindow
except ImportError:
    from gui import BuddyWindow


def _smoke_out_path():
    """`--smoke-out=FILE` (or `--smoke-out FILE`). The Windows build has no console, so stdout is
    invisible there; the result is written to this file instead (and printed where possible)."""
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--smoke-out="):
            return arg.split("=", 1)[1]
        if arg == "--smoke-out" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _smoke_report(message: str) -> None:
    path = _smoke_out_path()
    if path:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError:
            pass
    try:
        print(message, file=sys.stderr if message.startswith("SMOKE FAIL") else sys.stdout, flush=True)
    except Exception:
        pass  # no console (Windows GUI build): the file above is the record


def smoke_test() -> int:
    """`Buddy --smoke-test [--smoke-out=FILE]`: CI launches the freshly built app with this flag. It
    proves the bundle starts, Qt plugins load, assets are present and the window builds, then
    exits 0 without starting the backend, tracking, or touching real user data."""
    try:
        import importlib
        for name in ("PySide6.QtMultimedia", "PySide6.QtTextToSpeech", "PySide6.QtSvg", "requests",
                     "openrouter", "openrouter.utils.url", "googleapiclient", "certifi"):
            try:
                importlib.import_module(name)
            except Exception as exc:  # a missing module/plugin is exactly what this test must catch
                _smoke_report(f"SMOKE FAIL: could not import {name}: {exc}")
                return 1
        from gui.icons import BUDDY_LOGO_PATH, MEMORY_BRAIN_ICON_PATH
        for asset in (BUDDY_LOGO_PATH, MEMORY_BRAIN_ICON_PATH):
            if not asset.exists():
                _smoke_report(f"SMOKE FAIL: missing asset {asset}")
                return 1
        from tools.paths import app_root
        if not (app_root() / "knowledge").exists():
            _smoke_report("SMOKE FAIL: knowledge/ folder is missing from the bundle")
            return 1
        app = QApplication(sys.argv[:1])
        window = BuddyWindow()
        window.show_window()
        import time
        for _ in range(20):                      # let the window paint; no long-running event loop
            app.processEvents()
            time.sleep(0.05)
    except Exception as exc:
        import traceback
        _smoke_report(f"SMOKE FAIL: {exc}\n{traceback.format_exc()}")
        return 1
    _smoke_report("SMOKE OK")
    # Skip Qt teardown: background threads still running at exit would abort the process.
    os._exit(0)


def main():
    if "--smoke-test" in sys.argv:
        sys.exit(smoke_test())
    # The local backend is a daemon thread, so users only need this command:
    # `python3 main.py`. Account setup and billing remain optional features.
    backend = None
    try:
        from backend.runtime import start_local_backend
        backend = start_local_backend()
        if backend and backend.server is None and backend.external:
            print(f"Buddy backend already running at {backend.url}")
        elif backend:
            print(f"Buddy backend running at {backend.url}")
    except Exception as exc:
        # A backend dependency or port must never prevent the desktop UI from
        # opening. Billing surfaces will explain how to reconnect later.
        print(f"Buddy backend unavailable: {exc}", file=sys.stderr)

    app = QApplication(sys.argv)
    app.setApplicationName("Buddy")
    try:
        from version import APP_VERSION
        app.setApplicationVersion(APP_VERSION)
    except Exception:
        pass
    app.setQuitOnLastWindowClosed(False)

    window = BuddyWindow()
    window.show_window()
    if backend and backend.server is not None:
        app.aboutToQuit.connect(backend.stop)
    try:  # local-only routine learning; Settings can turn it off and wipe it
        from core import activity
        activity.start_tracking()
        app.aboutToQuit.connect(activity.stop_tracking)
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
