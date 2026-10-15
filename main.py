"""Buddy entry point."""
import sys
from PySide6.QtWidgets import QApplication

try:
    from gui.main_window import BuddyWindow
except ImportError:
    from gui import BuddyWindow


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = BuddyWindow()
    window.show_window()
    try:  # local-only routine learning; Settings can turn it off and wipe it
        from core import activity
        activity.start_tracking()
        app.aboutToQuit.connect(activity.stop_tracking)
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
