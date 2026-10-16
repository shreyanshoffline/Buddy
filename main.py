"""Buddy's single cross-platform entry point."""
import sys
from PySide6.QtWidgets import QApplication

try:
    from gui.main_window import BuddyWindow
except ImportError:
    from gui import BuddyWindow


def main():
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
