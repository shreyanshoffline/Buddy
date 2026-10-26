"""Stable prompt suggestions for the new-chat screen."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .chat_input import FlowLayout
from ..theme import PILL_BG, PILL_BORDER, PRIMARY_COLOR, ON_PRIMARY_TEXT, TEXT_COLOR_MUTED

_ICONS = {"routine": "▶", "repeat": "↻", "default": "✦"}


class SuggestionBar(QWidget):
    """Render up to three prompt chips without layout-changing effects."""

    chosen = Signal(dict)
    opt_in_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumWidth(0)
        self.setStyleSheet("background: transparent; border: none;")
        self._items, self._buttons = [], []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(8)
        self._row = FlowLayout(margin=0, h_spacing=10, v_spacing=8)
        root.addLayout(self._row)

        note_row = QHBoxLayout()
        note_row.setContentsMargins(0, 0, 0, 0)
        note_row.setAlignment(Qt.AlignCenter)
        self._note = QLabel("Want suggestions based on your routine? Buddy can learn which apps and sites you use, and when. Only on this Mac.")
        self._note.setWordWrap(True)
        self._note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._note.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; background: transparent; border: none;")
        self._opt = QPushButton("Turn on")
        self._opt.setCursor(Qt.PointingHandCursor)
        self._opt.setStyleSheet(f"QPushButton {{ color: {PRIMARY_COLOR}; background: transparent; border: none; font-size: 11px; font-weight: 700; }} QPushButton:hover {{ text-decoration: underline; }}")
        self._opt.clicked.connect(self.opt_in_requested.emit)
        note_row.addWidget(self._note, 1)
        note_row.addWidget(self._opt)
        root.addLayout(note_row)
        self._note.hide()
        self._opt.hide()

    def _new_chip(self):
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumWidth(0)
        button.setFixedHeight(33)
        button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        button.setStyleSheet(f"QPushButton {{ background: {PILL_BG}; color: {PRIMARY_COLOR}; border: 1px solid {PILL_BORDER}; border-radius: 17px; padding: 8px 16px; font-size: 12px; font-weight: 600; }} QPushButton:hover {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border-color: {PRIMARY_COLOR}; }} QPushButton:pressed {{ background: {PILL_BG}; color: {PRIMARY_COLOR}; }}")
        button.clicked.connect(lambda _=False, b=button: self.chosen.emit(b._suggestion_item))
        return button

    def set_suggestions(self, items, show_opt_in=False):
        """Replace the visible set in one layout pass."""
        for button in self._buttons:
            self._row.removeWidget(button)
            button.hide()
            button.deleteLater()
        self._buttons = []
        self._items = list(items)[:3]
        for item in self._items:
            button = self._new_chip()
            button._suggestion_item = item
            button.setText(f"{_ICONS.get(item.get('kind'), '✦')}  {item['label']}")
            reason = item.get("reason") or ""
            button.setToolTip(f"{reason}\n\n{item['prompt']}" if reason else item["prompt"])
            self._buttons.append(button)
            self._row.addWidget(button)
        self._note.setVisible(bool(show_opt_in))
        self._opt.setVisible(bool(show_opt_in))
        self._row.invalidate()
        self.updateGeometry()

    def labels(self):
        return [f"{_ICONS.get(item.get('kind'), '✦')}  {item['label']}" for item in self._items]
