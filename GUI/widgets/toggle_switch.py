"""A modern sliding toggle switch — used in place of a plain checkbox
anywhere a setting is a clean on/off (e.g. dark mode)."""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor


class ToggleSwitch(QWidget):
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
