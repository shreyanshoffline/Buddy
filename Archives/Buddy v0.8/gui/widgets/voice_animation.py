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
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(45)

    def set_mode(self, mode):
        self._mode = mode
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.16) % 6.283
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        if self._mode == "recording":
            color = QColor("#e44747")
            strength = 1.0
        elif self._mode == "processing":
            color = QColor("#f0aa2b")
            strength = 0.72
        elif self._mode == "error":
            color = QColor("#d83a32")
            strength = 0.45
        else:
            color = QColor("#0099e9")
            strength = 0.25

        center_y = self.height() / 2
        count = 19
        gap = 10.0
        start_x = (self.width() - (count - 1) * gap) / 2
        for index in range(count):
            wave = abs(math.sin(self._phase + index * 0.48))
            envelope = 0.35 + 0.65 * math.sin((index + 1) / count * math.pi)
            height = 5 + (22 * strength * wave * envelope)
            if self._mode == "idle":
                height = 4 + (4 * wave)
            color.setAlpha(105 + int(120 * strength))
            painter.setBrush(color)
            painter.drawRoundedRect(start_x + index * gap - 2, center_y - height / 2, 4, height, 2, 2)

        painter.setPen(QPen(color, 1))
        painter.setOpacity(0.25)
        painter.drawLine(14, center_y, self.width() - 14, center_y)
