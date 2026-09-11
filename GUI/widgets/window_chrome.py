"""Frameless window resize that tracks the visible card, not the shadow."""
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtWidgets import QWidget, QFrame


LEFT, RIGHT, TOP, BOTTOM = "left", "right", "top", "bottom"

CURSORS = {
    frozenset({LEFT}): Qt.SizeHorCursor,
    frozenset({RIGHT}): Qt.SizeHorCursor,
    frozenset({TOP}): Qt.SizeVerCursor,
    frozenset({BOTTOM}): Qt.SizeVerCursor,
    frozenset({LEFT, TOP}): Qt.SizeFDiagCursor,
    frozenset({RIGHT, BOTTOM}): Qt.SizeFDiagCursor,
    frozenset({RIGHT, TOP}): Qt.SizeBDiagCursor,
    frozenset({LEFT, BOTTOM}): Qt.SizeBDiagCursor,
}


class _EdgeStrip(QWidget):
    def __init__(self, window, controller, edges):
        super().__init__(window)
        self.controller = controller
        self.edges = set(edges)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(CURSORS.get(frozenset(self.edges), Qt.ArrowCursor))
        self.setAccessibleName("Resize window")
        self.setToolTip("Drag to resize")

    def enterEvent(self, event):
        self.controller.show_indicator(self.edges)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.controller.resizing:
            self.controller.hide_indicator()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.controller.begin_resize(self.edges, event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.controller.resizing and event.buttons() & Qt.LeftButton:
            self.controller.resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.controller.resizing:
            self.controller.end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class EdgeResizeController:
    def __init__(self, window, container, margin=18, band=16, min_size=None, accent="#0099e9"):
        self.window = window
        self.container = container
        self.margin = margin
        self.band = band
        self.min_size = min_size or window.minimumSize()
        self.accent = accent
        self.edge = set()
        self.resizing = False
        self._origin_global = QPoint()
        self._origin_geo = QRect()

        self.indicator = QFrame(window)
        self.indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.indicator.setStyleSheet(
            "QFrame { background: %s; border: none; border-radius: 3px; }" % accent
        )
        self.indicator.hide()

        self.strips = {
            LEFT: _EdgeStrip(window, self, {LEFT}),
            RIGHT: _EdgeStrip(window, self, {RIGHT}),
            TOP: _EdgeStrip(window, self, {TOP}),
            BOTTOM: _EdgeStrip(window, self, {BOTTOM}),
            "tl": _EdgeStrip(window, self, {LEFT, TOP}),
            "tr": _EdgeStrip(window, self, {RIGHT, TOP}),
            "bl": _EdgeStrip(window, self, {LEFT, BOTTOM}),
            "br": _EdgeStrip(window, self, {RIGHT, BOTTOM}),
        }
        original_resize = window.resizeEvent

        def _wrapped_resize(event):
            original_resize(event)
            self.relayout()

        window.resizeEvent = _wrapped_resize
        self.relayout()

    def relayout(self):
        rect = self.container.geometry()
        band = self.band
        corner = band + 4
        self.strips[LEFT].setGeometry(rect.left() - band // 2, rect.top() + corner, band, max(24, rect.height() - corner * 2))
        self.strips[RIGHT].setGeometry(rect.right() - band // 2, rect.top() + corner, band, max(24, rect.height() - corner * 2))
        self.strips[TOP].setGeometry(rect.left() + corner, rect.top() - band // 2, max(24, rect.width() - corner * 2), band)
        self.strips[BOTTOM].setGeometry(rect.left() + corner, rect.bottom() - band // 2, max(24, rect.width() - corner * 2), band)
        self.strips["tl"].setGeometry(rect.left() - band // 2, rect.top() - band // 2, corner, corner)
        self.strips["tr"].setGeometry(rect.right() - band // 2, rect.top() - band // 2, corner, corner)
        self.strips["bl"].setGeometry(rect.left() - band // 2, rect.bottom() - band // 2, corner, corner)
        self.strips["br"].setGeometry(rect.right() - band // 2, rect.bottom() - band // 2, corner, corner)
        for strip in self.strips.values():
            strip.raise_()
            strip.show()
        self.indicator.raise_()
        if self.edge:
            self.show_indicator(self.edge)

    def show_indicator(self, edges):
        self.edge = set(edges)
        rect = self.container.geometry()
        thickness = 4
        pad = 12
        if edges == {LEFT}:
            self.indicator.setGeometry(rect.left() - 1, rect.top() + pad, thickness, max(24, rect.height() - pad * 2))
        elif edges == {RIGHT}:
            self.indicator.setGeometry(rect.right() - thickness + 1, rect.top() + pad, thickness, max(24, rect.height() - pad * 2))
        elif edges == {TOP}:
            self.indicator.setGeometry(rect.left() + pad, rect.top() - 1, max(24, rect.width() - pad * 2), thickness)
        elif edges == {BOTTOM}:
            self.indicator.setGeometry(rect.left() + pad, rect.bottom() - thickness + 1, max(24, rect.width() - pad * 2), thickness)
        else:
            x = rect.left() - 1 if LEFT in edges else rect.right() - 19
            y = rect.top() - 1 if TOP in edges else rect.bottom() - 19
            self.indicator.setGeometry(x, y, 20, 20)
        self.indicator.show()
        self.indicator.raise_()

    def hide_indicator(self):
        if not self.resizing:
            self.edge = set()
            self.indicator.hide()

    def begin_resize(self, edges, global_pos):
        self.resizing = True
        self.edge = set(edges)
        self._origin_global = global_pos
        self._origin_geo = self.window.geometry()
        self.show_indicator(self.edge)

    def resize_to(self, global_pos):
        if not self.resizing:
            return
        delta = global_pos - self._origin_global
        geo = QRect(self._origin_geo)
        min_w = self.min_size.width()
        min_h = self.min_size.height()
        if LEFT in self.edge:
            new_w = geo.width() - delta.x()
            if new_w >= min_w:
                geo.moveLeft(geo.x() + delta.x())
                geo.setWidth(new_w)
        if RIGHT in self.edge:
            geo.setWidth(max(min_w, geo.width() + delta.x()))
        if TOP in self.edge:
            new_h = geo.height() - delta.y()
            if new_h >= min_h:
                geo.moveTop(geo.y() + delta.y())
                geo.setHeight(new_h)
        if BOTTOM in self.edge:
            geo.setHeight(max(min_h, geo.height() + delta.y()))
        self.window.setGeometry(geo)
        self.relayout()

    def end_resize(self):
        self.resizing = False
        self.hide_indicator()

    def _edge_at(self, pos):
        for strip in self.strips.values():
            if strip.geometry().contains(pos):
                return strip.edges
        return set()
