"""Click-through glow around the screen edges that shows what Buddy is doing.

- thinking: slow, calm blue breathing
- working: brighter, faster breathing plus a light that travels around the edge;
  the colour follows the tier of the current step (easy teal, medium blue, heavy violet)
- finish(True/False): a quick green / red flash, then it fades away
- pulse(): a tiny, short edge shimmer for ordinary button interactions
"""
import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

TIER_COLORS = {"easy": (20, 184, 166), "medium": (59, 130, 246), "heavy": (168, 85, 247)}
THINKING = (0, 153, 233)
INTERACTION = (100, 181, 246)
SUCCESS = (52, 199, 89)
ERROR = (255, 69, 58)
THICKNESS = 48
INTERACTION_THICKNESS = 10


class ScreenEdgeGlow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._mode = "idle"
        self._color = list(THINKING)
        self._target = THINKING
        self._t0 = time.monotonic()
        self._flash = None  # (rgb, start, duration)
        self._interaction = None  # (rgb, start, duration)
        self._fading = False
        self._intensity = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.hide()

    # ---- public API (kept compatible with the old start/stop) ----
    def start(self, mode="thinking", tier=None):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        # Cover the complete virtual desktop so the glow is not clipped when
        # a user has a second monitor or a display positioned left of the
        # primary screen (negative virtual coordinates are valid here).
        self.setGeometry(screen.virtualGeometry())
        self._fading = False
        self.set_mode(mode, tier)
        if not self._timer.isActive():
            self._timer.start()
        self.show()
        self.raise_()

    def set_mode(self, mode, tier=None):
        self._mode = mode
        self._target = TIER_COLORS.get(tier) if (mode == "working" and tier in TIER_COLORS) else THINKING

    def flash(self, ok=True):
        self._flash = (SUCCESS if ok else ERROR, time.monotonic(), 0.8 if ok else 1.0)

    def pulse(self, color=None, duration=0.18):
        """Show a very small, click-through shimmer for a normal interaction.

        This deliberately does not change the task glow's mode or intensity.
        It is just enough feedback to make a click feel acknowledged without
        turning every button press into a full-screen animation.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        self.setGeometry(screen.virtualGeometry())
        self._interaction = (tuple(color or INTERACTION), time.monotonic(), max(0.08, float(duration)))
        if not self._timer.isActive():
            self._timer.start()
        self.show()
        self.raise_()

    def finish(self, ok=True):
        """End of a task: flash, then fade out and hide."""
        if not self.isVisible():
            return
        self.flash(ok)
        self._fading = True
        self._mode = "idle"

    def stop(self):
        self._timer.stop()
        self._flash, self._interaction, self._fading, self._intensity = None, None, False, 0.0
        self.hide()

    # ---- animation ----
    def _tick(self):
        now = time.monotonic()
        for i in range(3):  # ease the colour toward its target
            self._color[i] += (self._target[i] - self._color[i]) * 0.12
        goal = 1.0 if self._mode != "idle" else 0.0
        self._intensity += (goal - self._intensity) * 0.15
        if self._interaction and now - self._interaction[1] >= self._interaction[2]:
            self._interaction = None
        if self._fading and self._flash is None and self._intensity < 0.02:
            self.stop()
            return
        if self._mode == "idle" and self._flash is None and self._interaction is None and self._intensity < 0.02:
            self.stop()
            return
        if self._flash and now - self._flash[1] > self._flash[2]:
            self._flash = None
        self.update()

    def _perimeter_point(self, t):
        w, h = self.width(), self.height()
        per = 2 * (w + h)
        d = (t % 1.0) * per
        if d < w:
            return QPointF(d, 0)
        d -= w
        if d < h:
            return QPointF(w, d)
        d -= h
        if d < w:
            return QPointF(w - d, h)
        return QPointF(0, h - (d - w))

    def _edges(self, painter, rgb, alpha, thickness=THICKNESS):
        w, h, t = self.width(), self.height(), thickness
        for rect, p0, p1 in (
            (QRectF(0, 0, w, t), QPointF(0, 0), QPointF(0, t)),
            (QRectF(0, h - t, w, t), QPointF(0, h), QPointF(0, h - t)),
            (QRectF(0, 0, t, h), QPointF(0, 0), QPointF(t, 0)),
            (QRectF(w - t, 0, t, h), QPointF(w, 0), QPointF(w - t, 0)),
        ):
            g = QLinearGradient(p0, p1)
            g.setColorAt(0.0, QColor(rgb[0], rgb[1], rgb[2], int(max(0, min(255, alpha)))))
            g.setColorAt(0.35, QColor(rgb[0], rgb[1], rgb[2], int(max(0, min(255, alpha * 0.35)))))
            g.setColorAt(1.0, QColor(rgb[0], rgb[1], rgb[2], 0))
            painter.fillRect(rect, g)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        now = time.monotonic() - self._t0
        working = self._mode == "working"
        period = 1.3 if working else 2.6
        breath = 0.5 + 0.5 * math.sin(now * 2 * math.pi / period)
        strength = (0.55 + 0.45 * breath) * (1.0 if working else 0.72)
        rgb = tuple(int(c) for c in self._color)
        self._edges(p, rgb, 150 * strength * self._intensity)
        if working and self._intensity > 0.3:
            for i, (lag, alpha, radius) in enumerate(((0.0, 190, 170), (0.012, 120, 130), (0.026, 70, 95), (0.042, 35, 70))):
                c = self._perimeter_point(now * 0.16 - lag)
                g = QRadialGradient(c, radius)
                g.setColorAt(0.0, QColor(255, 255, 255, int(alpha * 0.55)))
                g.setColorAt(0.25, QColor(rgb[0], rgb[1], rgb[2], alpha))
                g.setColorAt(1.0, QColor(rgb[0], rgb[1], rgb[2], 0))
                p.setBrush(g)
                p.setPen(Qt.NoPen)
                p.drawEllipse(c, radius, radius)
        if self._flash:
            frgb, start, dur = self._flash
            k = 1 - (time.monotonic() - start) / dur
            self._edges(p, frgb, 230 * max(0.0, k) ** 1.4)
        if self._interaction:
            irgb, start, dur = self._interaction
            k = 1 - (time.monotonic() - start) / dur
            self._edges(
                p, irgb, 42 * max(0.0, k) ** 1.8,
                thickness=INTERACTION_THICKNESS,
            )
