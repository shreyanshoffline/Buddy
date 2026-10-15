"""Three suggestion chips under the greeting on a new chat, learned from the user's own routine."""
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import PILL_BG, PILL_BORDER, PRIMARY_COLOR, ON_PRIMARY_TEXT, TEXT_COLOR_MUTED

_ICONS = {"routine": "▶", "repeat": "↻", "default": "✦"}


class SuggestionBar(QWidget):
    chosen = Signal(dict)
    opt_in_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._buttons = []
        self._anims = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(8)
        self._row = QBoxLayout(QBoxLayout.LeftToRight)
        self._row.setSpacing(10)
        self._row.setAlignment(Qt.AlignCenter)
        root.addLayout(self._row)
        self._note_row = QHBoxLayout()
        self._note_row.setAlignment(Qt.AlignCenter)
        self._note = QLabel("Want suggestions based on your routine? Buddy can learn which apps and sites you use, and when. Only on this Mac.")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; background: transparent; border: none;")
        self._opt = QPushButton("Turn on")
        self._opt.setCursor(Qt.PointingHandCursor)
        self._opt.setStyleSheet(f"QPushButton {{ color: {PRIMARY_COLOR}; background: transparent; border: none; font-size: 11px; font-weight: 700; }}"
                                f"QPushButton:hover {{ text-decoration: underline; }}")
        self._opt.clicked.connect(self.opt_in_requested.emit)
        self._note_row.addWidget(self._note, 1)
        self._note_row.addWidget(self._opt)
        root.addLayout(self._note_row)
        self._note.setVisible(False)
        self._opt.setVisible(False)

    def _chip(self, item):
        btn = QPushButton("%s  %s" % (_ICONS.get(item.get("kind"), "✦"), item["label"]))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip((item.get("reason") + "\n\n" if item.get("reason") else "") + item["prompt"])
        btn.setStyleSheet(f"""
            QPushButton {{ background: {PILL_BG}; color: {PRIMARY_COLOR}; border: 1px solid {PILL_BORDER};
                           border-radius: 17px; padding: 8px 16px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border-color: {PRIMARY_COLOR}; }}
        """)
        btn.clicked.connect(lambda _=False, i=item: self.chosen.emit(i))
        return btn

    def set_suggestions(self, items, show_opt_in=False):
        for b in self._buttons:
            self._row.removeWidget(b)
            b.deleteLater()
        self._buttons, self._anims, self._items = [], [], list(items)
        for n, item in enumerate(self._items):
            btn = self._chip(item)
            self._row.addWidget(btn)
            self._buttons.append(btn)
            fx = QGraphicsOpacityEffect(btn)
            fx.setOpacity(0.0)
            btn.setGraphicsEffect(fx)
            anim = QPropertyAnimation(fx, b"opacity", self)  # staggered fade-in so the chips feel alive
            anim.setDuration(320)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            QTimer.singleShot(90 * n, anim.start)
            self._anims.append(anim)
        self._note.setVisible(show_opt_in)
        self._opt.setVisible(show_opt_in)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._row.setDirection(QBoxLayout.LeftToRight if self.width() >= 640 else QBoxLayout.TopToBottom)

    def labels(self):
        return [b.text() for b in self._buttons]
