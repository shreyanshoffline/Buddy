"""Three suggestion chips under the greeting on a new chat, learned from the user's own routine."""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from .chat_input import FlowLayout
from ..theme import PILL_BG, PILL_BORDER, PRIMARY_COLOR, ON_PRIMARY_TEXT, TEXT_COLOR_MUTED

_ICONS = {"routine": "▶", "repeat": "↻", "default": "✦"}


class SuggestionBar(QWidget):
    chosen = Signal(dict)
    opt_in_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # The available width can be narrow on a laptop or a packaged build.
        # Let the layout report its real height so chips never paint outside
        # the chat page when they wrap.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumWidth(0)
        self.setStyleSheet("background: transparent; border: none;")
        self._items = []
        self._buttons = []
        self._anims = []
        self._suggestion_generation = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(8)
        self._row = FlowLayout(margin=0, h_spacing=10, v_spacing=8)
        root.addLayout(self._row)
        self._note_row = QHBoxLayout()
        self._note_row.setContentsMargins(0, 0, 0, 0)
        self._note_row.setAlignment(Qt.AlignCenter)
        self._note = QLabel("Want suggestions based on your routine? Buddy can learn which apps and sites you use, and when. Only on this Mac.")
        self._note.setWordWrap(True)
        self._note.setMinimumWidth(0)
        self._note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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

    def _fit_note(self):
        if not self._note.isVisible() or self.width() <= 0:
            return
        available = max(1, self.width() - self._opt.sizeHint().width() - 4)
        height = max(13, self._note.heightForWidth(available))
        self._note.setMinimumHeight(height)
        self.updateGeometry()

    def _start_fade(self, animation, generation):
        if generation == self._suggestion_generation and animation.targetObject() is not None:
            animation.start()

    def _chip(self):
        # Keep a small reusable pool instead of deleting buttons on every
        # refresh.  This prevents an old chip from ever painting with Qt's
        # default 640x480 geometry while a new set is being built.
        btn = QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(0)
        btn.setFixedHeight(33)
        btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        btn.setStyleSheet(f"""
            QPushButton {{ background: {PILL_BG}; color: {PRIMARY_COLOR}; border: 1px solid {PILL_BORDER};
                           border-radius: 17px; padding: 8px 16px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border-color: {PRIMARY_COLOR}; }}
        """)
        btn.clicked.connect(lambda _=False, b=btn: self.chosen.emit(getattr(b, "_suggestion_item", {})))
        return btn

    def _configure_chip(self, button, item):
        button._suggestion_item = item
        button.setText("%s  %s" % (_ICONS.get(item.get("kind"), "✦"), item["label"]))
        button.setToolTip((item.get("reason") + "\n\n" if item.get("reason") else "") + item["prompt"])

    def set_suggestions(self, items, show_opt_in=False):
        self._suggestion_generation += 1
        generation = self._suggestion_generation
        for anim in self._anims:
            anim.stop()
        for b in self._buttons:
            self._row.removeWidget(b)
            b.hide()
            b.setGraphicsEffect(None)
        self._anims, self._items = [], list(items)
        for n, item in enumerate(self._items):
            btn = self._buttons[n] if n < len(self._buttons) else self._chip()
            if n >= len(self._buttons):
                self._buttons.append(btn)
            self._configure_chip(btn, item)
            self._row.addWidget(btn)
            btn.show()
            fx = QGraphicsOpacityEffect(btn)
            fx.setOpacity(0.0)
            btn.setGraphicsEffect(fx)
            anim = QPropertyAnimation(fx, b"opacity", self)  # staggered fade-in so the chips feel alive
            anim.setDuration(320)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            QTimer.singleShot(90 * n, lambda a=anim, g=generation: self._start_fade(a, g))
            self._anims.append(anim)
        self._row.invalidate()
        self._row.activate()
        self.layout().invalidate()
        self.layout().activate()
        self._note.setVisible(show_opt_in)
        self._opt.setVisible(show_opt_in)
        QTimer.singleShot(0, self._fit_note)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_note()

    def labels(self):
        # Report the logical current set, not Qt's transient visibility while
        # a chip is fading in.  The reusable pool can contain hidden extras.
        return [
            "%s  %s" % (_ICONS.get(item.get("kind"), "✦"), item["label"])
            for item in self._items
        ]
