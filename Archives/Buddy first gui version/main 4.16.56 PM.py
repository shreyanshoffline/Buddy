"""Buddy entry point."""
import sys
from PySide6.QtWidgets import QApplication

from gui import BuddyWindow


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = BuddyWindow()
    window.show_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
