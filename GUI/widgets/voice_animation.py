"""Small, calm waveform animation used by Buddy's voice page."""

import math
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


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
