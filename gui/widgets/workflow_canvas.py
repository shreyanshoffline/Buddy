"""A small Canva-like workflow canvas for Buddy's model map."""
import math

from PySide6.QtCore import QEvent, Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsPathItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.model_config import MODEL_OPTIONS, display_model_name
from ..theme import (
    ACTIVE_BG_COLOR,
    BORDER_COLOR,
    CARD_SUBTITLE_COLOR,
    CARD_TEXT_COLOR,
    INPUT_BG,
    PRIMARY_COLOR,
    SECTION_CARD_BG,
    TEXT_COLOR_DARK,
)


class WorkflowNodeWidget(QFrame):
    model_changed = Signal(str, str)
    selected = Signal(str)

    def __init__(self, node, model_id=None, parent=None):
        super().__init__(parent)
        self.node = node
        self.node_id = node["id"]
        self.model_field = node.get("model_field")
        self._selected = False
        self._drag_start_scene = None
        self._drag_proxy = None
        self.setObjectName("WorkflowNode")
        self.setMinimumWidth(290)
        self.setMinimumHeight(138 if self.model_field else 112)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._build(model_id)
        self._refresh_style()

    def _build(self, model_id):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        drag_handle = QLabel("⠿")
        drag_handle.setCursor(Qt.OpenHandCursor)
        drag_handle.setToolTip("Drag this handle to move the block")
        drag_handle.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 16px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        drag_handle.installEventFilter(self)
        header.addWidget(drag_handle)
        title = QLabel(self.node["title"])
        title.installEventFilter(self)
        title.setWordWrap(True)
        title.setMinimumWidth(145)
        title.setStyleSheet(
            f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        kind = QLabel(self.node["kind"].title())
        kind.installEventFilter(self)
        kind.setAlignment(Qt.AlignRight | Qt.AlignTop)
        kind.setMinimumWidth(52)
        kind.setStyleSheet(
            f"color: {PRIMARY_COLOR}; font-size: 9px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header.addWidget(kind)
        layout.addLayout(header)

        description = QLabel(self.node["description"])
        description.installEventFilter(self)
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(description)

        if self.model_field:
            model_label = QLabel("Model")
            model_label.installEventFilter(self)
            model_label.setStyleSheet(
                f"color: {CARD_SUBTITLE_COLOR}; font-size: 9px; font-weight: 700; "
                "background: transparent; border: none;"
            )
            layout.addWidget(model_label)
            self.combo = QComboBox()
            self.combo.setEditable(True)
            self.combo.setMinimumWidth(0)
            self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.combo.setCursor(Qt.PointingHandCursor)
            self.combo.setToolTip("Choose a model or type a model ID")
            self.combo.setStyleSheet(f"""
                QComboBox {{
                    background: {INPUT_BG}; color: {TEXT_COLOR_DARK};
                    border: 1px solid {BORDER_COLOR}; border-radius: 7px;
                    padding: 5px 7px; font-size: 9px;
                }}
                QComboBox:hover {{ border: 1px solid {PRIMARY_COLOR}; }}
                QComboBox QAbstractItemView {{
                    background: {INPUT_BG}; color: {TEXT_COLOR_DARK};
                    selection-background-color: {ACTIVE_BG_COLOR};
                }}
            """)
            options = list(dict.fromkeys(list(MODEL_OPTIONS) + [model_id or ""]))
            for value in options:
                if value:
                    self.combo.addItem(display_model_name(value), value)
            self.set_model(model_id)
            self.combo.activated.connect(self._save_combo)
            self.combo.lineEdit().editingFinished.connect(self._save_combo)
            layout.addWidget(self.combo)
        else:
            self.combo = None
        layout.activate()
        self.adjustSize()

    def _save_combo(self):
        if self.combo is None:
            return
        text = self.combo.currentText().strip()
        index = self.combo.currentIndex()
        value = (
            self.combo.itemData(index)
            if index >= 0 and self.combo.itemText(index) == text
            else text
        )
        if value:
            self.model_changed.emit(self.model_field, value.strip())

    def set_model(self, model_id):
        if self.combo is None or not model_id:
            return
        self.combo.blockSignals(True)
        if self.combo.findData(model_id) < 0:
            self.combo.addItem(display_model_name(model_id), model_id)
        self.combo.setCurrentIndex(self.combo.findData(model_id))
        self.combo.blockSignals(False)

    def set_selected(self, selected):
        self._selected = bool(selected)
        self._refresh_style()

    def _refresh_style(self):
        border = PRIMARY_COLOR if self._selected else BORDER_COLOR
        width = 2 if self._selected else 1
        kind_styles = {
            "tool": ("#fff3dd", 26),
            "image": ("#eaf8f2", 24),
            "manager": ("#f1ecff", 18),
            "output": ("#e8f6ff", 22),
        }
        background, radius = kind_styles.get(self.node["kind"], (SECTION_CARD_BG, 16))
        self.setStyleSheet(
            f"QFrame#WorkflowNode {{ background: {background}; "
            f"border: {width}px solid {border}; border-radius: {radius}px; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin_drag(event.position())
            event.accept()
            return
        self.selected.emit(self.node_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_proxy and self._drag_start_scene:
            self._move_drag(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_proxy:
            self._end_drag()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _begin_drag(self, local_pos):
        proxy = self.graphicsProxyWidget()
        if proxy is None:
            return
        self._drag_proxy = proxy
        self._drag_start_scene = proxy.mapToScene(QPointF(local_pos))
        self.selected.emit(self.node_id)

    def _move_drag(self, local_pos):
        local_scene = self._drag_proxy.mapToScene(QPointF(local_pos))
        delta = local_scene - self._drag_start_scene
        self._drag_proxy.setPos(self._drag_proxy.pos() + delta)
        self._drag_start_scene = local_scene

    def _end_drag(self):
        self._drag_proxy = None
        self._drag_start_scene = None

    def eventFilter(self, watched, event):
        if isinstance(watched, QLabel):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                local_pos = watched.mapTo(self, event.position().toPoint())
                watched.setCursor(Qt.ClosedHandCursor)
                self._begin_drag(QPointF(local_pos))
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_proxy and self._drag_start_scene:
                local_pos = watched.mapTo(self, event.position().toPoint())
                self._move_drag(QPointF(local_pos))
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
                watched.setCursor(Qt.OpenHandCursor)
                self._end_drag()
                return True
        return super().eventFilter(watched, event)


class WorkflowNodeItem(QGraphicsProxyWidget):
    def __init__(self, node, model_id, canvas, parent=None):
        super().__init__(parent)
        self.node_id = node["id"]
        self.canvas = canvas
        self.node_widget = WorkflowNodeWidget(node, model_id)
        self.setWidget(self.node_widget)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.node_widget.selected.connect(canvas.select_node)
        self.node_widget.model_changed.connect(canvas.model_changed.emit)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.canvas.update_edges()
            self.canvas.node_moved(self.node_id)
        return super().itemChange(change, value)


class WorkflowZoneItem(QGraphicsRectItem):
    """A soft group behind related draggable workflow pieces."""

    def __init__(self, zone, parent=None):
        rect = QRectF(*zone["rect"])
        super().__init__(rect, parent)
        color = QColor(zone.get("color", "#eef4fb"))
        color.setAlpha(185)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#d8e2ee"), 1.4, Qt.PenStyle.DashLine))
        self.setZValue(-4)

        title = QGraphicsSimpleTextItem(zone["title"], self)
        title.setBrush(QBrush(QColor(CARD_TEXT_COLOR)))
        title.setFont(title.font())
        title.setPos(rect.left() + 18, rect.top() + 14)
        title.setZValue(1)

        description = QGraphicsTextItem(zone.get("description", ""), self)
        description.setDefaultTextColor(QColor(CARD_SUBTITLE_COLOR))
        description.setTextWidth(max(120, rect.width() - 36))
        description.setPos(rect.left() + 18, rect.top() + 34)
        description.setZValue(1)


class WorkflowEdgeItem(QGraphicsPathItem):
    EDGE_STYLES = {
        "main": ("#6e82a8", 2.3, Qt.PenStyle.SolidLine),
        "context": ("#8c9bb0", 1.7, Qt.PenStyle.DashLine),
        "tool": ("#bd853c", 2.0, Qt.PenStyle.DashLine),
        "return": ("#7666bf", 2.3, Qt.PenStyle.DashLine),
    }

    def __init__(self, source, target, label="", kind="main", bidirectional=False, parent=None):
        super().__init__(parent)
        self.source = source
        self.target = target
        self.label = label
        self.kind = kind
        self.bidirectional = bidirectional
        color, width, style = self.EDGE_STYLES.get(kind, self.EDGE_STYLES["main"])
        self._color = color
        self.setZValue(-1)
        self.setPen(QPen(QColor(color), width, style))
        self.label_item = None
        if label and kind in {"return", "tool"}:
            self.label_item = QGraphicsSimpleTextItem(label, self)
            self.label_item.setBrush(QBrush(QColor(color)))
            font = self.label_item.font()
            font.setPointSizeF(8.5)
            self.label_item.setFont(font)
            self.label_item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True
            )
            self.label_item.setZValue(5)
        self.update_path()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.path().isEmpty():
            return
        painter.save()
        painter.setBrush(QBrush(QColor(self._color)))
        painter.setPen(Qt.NoPen)
        if self.bidirectional:
            self._draw_arrow(painter, 0.04, False)
        self._draw_arrow(painter, 0.96, True)
        painter.restore()

    def _draw_arrow(self, painter, percent, points_forward):
        point = self.path().pointAtPercent(percent)
        nearby_percent = percent + (0.015 if points_forward else -0.015)
        nearby = self.path().pointAtPercent(nearby_percent)
        direction = nearby - point
        if not points_forward:
            direction = point - nearby
        length = math.hypot(direction.x(), direction.y()) or 1.0
        unit = QPointF(direction.x() / length, direction.y() / length)
        side = QPointF(-unit.y(), unit.x())
        tip = point + unit * 7
        base = point - unit * 4
        painter.drawPolygon(QPolygonF([tip, base + side * 4, base - side * 4]))

    def update_path(self):
        source_rect = self.source.sceneBoundingRect()
        target_rect = self.target.sceneBoundingRect()
        source_center = source_rect.center()
        target_center = target_rect.center()
        horizontal = abs(target_center.x() - source_center.x()) > abs(target_center.y() - source_center.y())

        if horizontal:
            if target_center.x() >= source_center.x():
                start = QPointF(source_rect.right(), source_center.y())
                end = QPointF(target_rect.left(), target_center.y())
            else:
                start = QPointF(source_rect.left(), source_center.y())
                end = QPointF(target_rect.right(), target_center.y())
            bend = max(55.0, abs(end.x() - start.x()) * 0.45)
            control_one = QPointF(start.x() + (bend if end.x() >= start.x() else -bend), start.y())
            control_two = QPointF(end.x() - (bend if end.x() >= start.x() else -bend), end.y())
        else:
            going_down = target_center.y() >= source_center.y()
            start = QPointF(
                source_center.x(), source_rect.bottom() if going_down else source_rect.top()
            )
            end = QPointF(
                target_center.x(), target_rect.top() if going_down else target_rect.bottom()
            )
            bend = max(55.0, abs(end.y() - start.y()) * 0.45)
            direction = 1 if going_down else -1
            control_one = QPointF(start.x(), start.y() + bend * direction)
            control_two = QPointF(end.x(), end.y() - bend * direction)

        path = self._routed_path(start, end, control_one, control_two)
        self.setPath(path)
        if self.label_item is not None:
            point = path.pointAtPercent(0.5)
            self.label_item.setPos(point + QPointF(7, -12))

    def _routed_path(self, start, end, control_one, control_two):
        """Use the normal curve unless another node blocks it, then detour."""
        path = QPainterPath(start)
        path.cubicTo(control_one, control_two, end)
        obstacles = [
            item.sceneBoundingRect().adjusted(-18, -18, 18, 18)
            for item in self.source.canvas._nodes.values()
            if item not in (self.source, self.target)
        ]
        samples = [path.pointAtPercent(i / 24) for i in range(25)]
        if not any(any(rect.contains(point) for rect in obstacles) for point in samples):
            return path

        horizontal = abs(end.x() - start.x()) >= abs(end.y() - start.y())
        if horizontal:
            lanes = [
                min((rect.top() for rect in obstacles), default=min(start.y(), end.y())) - 35,
                max((rect.bottom() for rect in obstacles), default=max(start.y(), end.y())) + 35,
            ]
            for lane in lanes:
                candidate = QPainterPath(start)
                candidate.lineTo(QPointF((start.x() + end.x()) / 2, start.y()))
                candidate.lineTo(QPointF((start.x() + end.x()) / 2, lane))
                candidate.lineTo(QPointF((start.x() + end.x()) / 2, end.y()))
                candidate.lineTo(end)
                if not any(any(rect.contains(candidate.pointAtPercent(i / 24)) for rect in obstacles) for i in range(25)):
                    return candidate
        else:
            lanes = [
                min((rect.left() for rect in obstacles), default=min(start.x(), end.x())) - 35,
                max((rect.right() for rect in obstacles), default=max(start.x(), end.x())) + 35,
            ]
            for lane in lanes:
                candidate = QPainterPath(start)
                candidate.lineTo(QPointF(start.x(), (start.y() + end.y()) / 2))
                candidate.lineTo(QPointF(lane, (start.y() + end.y()) / 2))
                candidate.lineTo(QPointF(end.x(), (start.y() + end.y()) / 2))
                candidate.lineTo(end)
                if not any(any(rect.contains(candidate.pointAtPercent(i / 24)) for rect in obstacles) for i in range(25)):
                    return candidate
        return path


class WorkflowCanvas(QGraphicsView):
    """Zoomable, pannable canvas whose nodes are draggable and editable."""

    model_changed = Signal(str, str)
    layout_changed = Signal(dict)
    zoom_changed = Signal(float)

    def __init__(self, nodes, connections, zones=None, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(-900, -820, 1800, 2200)
        self.scene().setBackgroundBrush(QBrush(QColor("#f7fbff")))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._nodes = {}
        self._edges = []
        self._zoom = 1.0
        self._panning = False
        self._pan_start = QPoint()
        self._build(nodes, connections, zones or ())

    def _build(self, nodes, connections, zones):
        self.scene().clear()
        self._nodes.clear()
        self._edges.clear()
        for zone in zones:
            self.scene().addItem(WorkflowZoneItem(zone))
        for node in nodes:
            item = WorkflowNodeItem(node, node.get("model"), self)
            item.setPos(*node["position"])
            self.scene().addItem(item)
            self._nodes[node["id"]] = item
        for connection in connections:
            if isinstance(connection, dict):
                source_id = connection.get("source")
                target_id = connection.get("target")
                label = connection.get("label", "")
                kind = connection.get("kind", "main")
                bidirectional = bool(connection.get("bidirectional", False))
            else:
                source_id, target_id = connection
                label, kind, bidirectional = "", "main", False
            source = self._nodes.get(source_id)
            target = self._nodes.get(target_id)
            if source and target:
                edge = WorkflowEdgeItem(source, target, label, kind, bidirectional)
                self.scene().addItem(edge)
                self._edges.append(edge)
        self.update_edges()

    def update_edges(self):
        for edge in self._edges:
            edge.update_path()

    def node_moved(self, _node_id):
        self.layout_changed.emit(self.current_layout())

    def current_layout(self):
        return {
            node_id: [round(item.pos().x(), 1), round(item.pos().y(), 1)]
            for node_id, item in self._nodes.items()
        }

    def select_node(self, node_id):
        for key, item in self._nodes.items():
            item.node_widget.set_selected(key == node_id)

    def refresh_models(self, nodes):
        for node in nodes:
            item = self._nodes.get(node["id"])
            if item:
                item.node_widget.set_model(node.get("model"))

    def apply_layout(self, layout):
        for node_id, position in (layout or {}).items():
            item = self._nodes.get(node_id)
            if item and isinstance(position, (list, tuple)) and len(position) == 2:
                item.setPos(float(position[0]), float(position[1]))
        self.update_edges()

    def _set_zoom(self, value, viewport_position=None):
        value = max(0.55, min(1.8, value))
        factor = value / self._zoom
        anchor = (
            self.mapToScene(viewport_position)
            if viewport_position is not None else None
        )
        self.scale(factor, factor)
        if anchor is not None:
            # Keep the exact piece beneath the pointer in place.  This makes
            # wheel zoom feel like familiar document and design tools.
            moved_anchor = self.mapToScene(viewport_position)
            delta = moved_anchor - anchor
            self.translate(delta.x(), delta.y())
        self._zoom = value
        self.zoom_changed.emit(value)

    def zoom_in(self):
        self._set_zoom(self._zoom * 1.15)

    def zoom_out(self):
        self._set_zoom(self._zoom / 1.15)

    def fit_content(self):
        rect = self.scene().itemsBoundingRect().adjusted(-90, -90, 90, 90)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(0.55, min(1.8, self.transform().m11()))
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self._set_zoom(
                self._zoom * (1.12 if delta > 0 else 1 / 1.12),
                event.position().toPoint(),
            )
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            current = event.position().toPoint()
            delta = current - self._pan_start
            self._pan_start = current
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#f7fbff"))
        grid_pen = QPen(QColor("#e6eff8"), 1)
        painter.setPen(grid_pen)
        left = int(rect.left()) - (int(rect.left()) % 40)
        top = int(rect.top()) - (int(rect.top()) % 40)
        x = left
        while x <= rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += 40
        y = top
        while y <= rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += 40
