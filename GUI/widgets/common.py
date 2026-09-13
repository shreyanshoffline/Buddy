"""Small standalone widgets used across the GUI: the dislike-reason
popup, the sliding on/off switch, and the voice-activity waveform.
Combined here since none of these depend on each other or need to be
separately swappable."""

import math

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QVBoxLayout, QPushButton, QFrame, QLabel,
    QHBoxLayout, QDialog, QButtonGroup, QRadioButton, QWidget,
)


class FeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Provide Feedback")
        self.setFixedSize(300, 200)

        layout = QVBoxLayout(self)

        label = QLabel("What was wrong with this response?")
        label.setWordWrap(True)
        layout.addWidget(label)

        self.btn_group = QButtonGroup(self)
        reasons = ["Not helpful", "Inaccurate", "Too long", "Other"]
        for i, reason in enumerate(reasons):
            rb = QRadioButton(reason)
            self.btn_group.addButton(rb, i)
            layout.addWidget(rb)

        btn_layout = QHBoxLayout()
        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(submit_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)


class ToggleSwitch(QWidget):
    """A modern sliding toggle switch — used in place of a plain checkbox
    anywhere a setting is a clean on/off (e.g. dark mode)."""

    toggled = Signal(bool)

    def __init__(self, checked=False, accent="#338eda", track_off="#c9ccd1", parent=None):
        super().__init__(parent)
        self._checked = checked
        self._accent = accent
        self._track_off = track_off
        self._enabled = True
        self.setFixedSize(40, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName("Switch")

    def isChecked(self):
        return self._checked

    def setChecked(self, value):
        if value != self._checked:
            self._checked = bool(value)
            self.update()

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, value):
        self._enabled = bool(value)
        self.setCursor(Qt.PointingHandCursor if self._enabled else Qt.ForbiddenCursor)
        self.update()

    def mousePressEvent(self, event):
        if not self._enabled:
            return
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()

    def keyPressEvent(self, event):
        if not self._enabled:
            return
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        track_color = QColor(self._accent) if self._checked else QColor(self._track_off)
        if not self._enabled:
            track_color.setAlpha(110)
        painter.setBrush(track_color)
        h = self.height()
        painter.drawRoundedRect(QRectF(0, 0, self.width(), h), h / 2, h / 2)

        knob_d = h - 4
        knob_x = self.width() - knob_d - 2 if self._checked else 2
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(knob_x, 2, knob_d, knob_d))


class VoiceAnimation(QWidget):
    """A lightweight waveform that reflects idle, listening, and speaking states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 58)
        self._mode = "idle"
        self._phase = 0.0
        self._level = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(45)
        self.setAccessibleName("Buddy voice activity")

    def set_mode(self, mode):
        self._mode = mode or "idle"
        if self._mode in ("idle", "paused", "error"):
            self._level = 0.0
        self.update()

    def set_level(self, level):
        try:
            self._level = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            self._level = 0.0
        self.update()

    def _tick(self):
        speed = 0.05 if self._mode in ("idle", "paused") else 0.16
        self._phase = (self._phase + speed) % 6.283
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        if self._mode in ("listening", "recording"):
            color = QColor("#e44747")
            strength = 0.45 + 0.55 * self._level
        elif self._mode == "speaking":
            color = QColor("#0099e9")
            strength = 0.40 + 0.60 * max(self._level, 0.35)
        elif self._mode in ("thinking", "processing"):
            color = QColor("#f0aa2b")
            strength = 0.55
        elif self._mode == "paused":
            color = QColor("#8492a6")
            strength = 0.18
        elif self._mode == "error":
            color = QColor("#d83a32")
            strength = 0.45
        else:
            color = QColor("#0099e9")
            strength = 0.12

        center_y = self.height() / 2
        count = 19
        gap = 10.0
        start_x = (self.width() - (count - 1) * gap) / 2
        for index in range(count):
            wave = abs(math.sin(self._phase + index * 0.48))
            envelope = 0.35 + 0.65 * math.sin((index + 1) / count * math.pi)
            height = 5 + (22 * strength * wave * envelope)
            if self._mode in ("idle", "paused"):
                height = 4 + (3 * wave)
            color.setAlpha(105 + int(120 * strength))
            painter.setBrush(color)
            painter.drawRoundedRect(start_x + index * gap - 2, center_y - height / 2, 4, height, 2, 2)

        painter.setPen(QPen(color, 1))
        painter.setOpacity(0.25)
        painter.drawLine(14, center_y, self.width() - 14, center_y)
