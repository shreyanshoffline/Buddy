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


def smoke_test() -> int:
    """Construct the bundled UI, verify assets/imports, then exit cleanly for CI."""
    import importlib
    import time

    for name in ("PySide6.QtMultimedia", "PySide6.QtSvg", "requests", "openrouter",
                 "openrouter.utils.url", "googleapiclient", "certifi"):
        try:
            importlib.import_module(name)
        except Exception as exc:
            print(f"SMOKE FAIL: could not import {name}: {exc}", file=sys.stderr)
            return 1

    from gui.icons import BUDDY_LOGO_PATH, MEMORY_BRAIN_ICON_PATH
    from tools.paths import app_root
    for asset in (BUDDY_LOGO_PATH, MEMORY_BRAIN_ICON_PATH):
        if not asset.exists():
            print(f"SMOKE FAIL: missing asset {asset}", file=sys.stderr)
            return 1
    if not (app_root() / "knowledge").exists():
        print("SMOKE FAIL: knowledge folder is missing from the bundle", file=sys.stderr)
        return 1

    app = QApplication(sys.argv[:1])
    window = BuddyWindow()
    window.show()  # avoid first-run modal dialogs and exercise only the bundled UI
    for _ in range(6):
        app.processEvents()
        time.sleep(0.05)
    print("SMOKE OK", flush=True)
    # Avoid Qt teardown aborting while daemon workers are still winding down.
    os._exit(0)


if __name__ == "__main__":
    main()
