"""Canva-like visual editor for Buddy's model workflow."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)

from core.model_config import DEFAULT_MODEL_CONFIG, load_model_config, save_model_config
from core.model_workflow import (
    DEFAULT_WORKFLOW_LAYOUT,
    WORKFLOW_CONNECTIONS,
    WORKFLOW_ZONES,
    load_workflow_layout,
    save_workflow_layout,
    workflow_snapshot,
)
from .card_page import CardPage
from ..theme import (
    BORDER_COLOR,
    CARD_SUBTITLE_COLOR,
    CARD_TEXT_COLOR,
    HOVER_BG_COLOR,
    PRIMARY_COLOR,
    PRIMARY_COLOR_DARK,
    TEXT_COLOR_DARK,
    TEXT_COLOR_MUTED,
)
from ..widgets.workflow_canvas import WorkflowCanvas


class ModelConfigurationPage(CardPage):
    """An editable, zoomable workflow map backed by the real model router."""

    def __init__(self, parent=None, close_callback=None, on_saved=None):
        super().__init__(
            "Model workflow",
            "Arrange Buddy's model pieces and choose what each piece uses.",
            parent,
            close_callback,
        )
        self.on_saved = on_saved
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(500)
        self._autosave_timer.timeout.connect(self._save_draft)
        self._pending_layout = None
        self._build_page()
        self.reload_from_db()
        QTimer.singleShot(0, self.canvas.fit_content)

    def _label(self, text, color=CARD_SUBTITLE_COLOR, size=11, weight=400):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {color}; font-size: {size}px; font-weight: {weight}; "
            "background: transparent; border: none;"
        )
        return label

    def _button(self, text, tooltip):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setFixedHeight(28)
        button.setStyleSheet(
            f"QPushButton {{ background: {HOVER_BG_COLOR}; color: {TEXT_COLOR_DARK}; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 4px 10px; "
            "font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ border: 1px solid {PRIMARY_COLOR}; "
            f"background: {HOVER_BG_COLOR}; }}"
            f"QPushButton:pressed {{ background: {PRIMARY_COLOR_DARK}; color: white; }}"
        )
        return button

    def _build_page(self):
        self.main_layout.addWidget(self._label(
            "This is the map Buddy follows. Drag a box to arrange it, choose a "
            "model inside a box, or use the zoom controls to explore the whole workflow.",
            CARD_SUBTITLE_COLOR,
            12,
            400,
        ))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(self._label("Model pieces", CARD_TEXT_COLOR, 12, 700))
        toolbar.addStretch()
        self.zoom_out_button = self._button("−", "Zoom out")
        self.zoom_in_button = self._button("+", "Zoom in")
        self.fit_button = self._button("Fit", "Fit the whole workflow on screen")
        self.save_button = self._button("Save draft", "Save the workflow layout and model choices now")
        self.save_button.clicked.connect(self._save_draft)
        self.zoom_label = self._label("100%", TEXT_COLOR_MUTED, 10, 700)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setMinimumWidth(42)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.fit_button)
        toolbar.addWidget(self.save_button)
        self.main_layout.addLayout(toolbar)

        self.canvas = WorkflowCanvas(
            workflow_snapshot(),
            WORKFLOW_CONNECTIONS,
            WORKFLOW_ZONES,
        )
        self.canvas.setMinimumHeight(390)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.model_changed.connect(self._on_model_changed)
        self.canvas.layout_changed.connect(self._on_layout_changed)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        self.zoom_out_button.clicked.connect(self.canvas.zoom_out)
        self.zoom_in_button.clicked.connect(self.canvas.zoom_in)
        self.fit_button.clicked.connect(self.canvas.fit_content)
        self.main_layout.addWidget(self.canvas, 1)

        footer = QHBoxLayout()
        self.save_status = self._label(
            "Draft saved. Drag boxes, pan with the middle button, and scroll over any spot to zoom there.",
            TEXT_COLOR_MUTED,
            10,
            400,
        )
        footer.addWidget(self.save_status)
        footer.addStretch()
        reset = self._button("Reset layout", "Restore the default model choices")
        reset.clicked.connect(self._reset_defaults)
        footer.addWidget(reset)
        self.main_layout.addLayout(footer)

    def _on_zoom_changed(self, value):
        self.zoom_label.setText(f"{round(value * 100)}%")

    def _on_model_changed(self, field, model_id):
        config = load_model_config()
        config[field] = model_id
        save_model_config(config)
        self.canvas.refresh_models(workflow_snapshot())
        self._mark_draft_dirty()
        if callable(self.on_saved):
            self.on_saved()

    def _reset_defaults(self):
        save_model_config(DEFAULT_MODEL_CONFIG)
        save_workflow_layout(DEFAULT_WORKFLOW_LAYOUT)
        self.reload_from_db()
        self._set_save_status("Draft reset to defaults.")
        if callable(self.on_saved):
            self.on_saved()

    def reload_from_db(self):
        if hasattr(self, "canvas"):
            self.canvas.refresh_models(workflow_snapshot())
            self.canvas.apply_layout(load_workflow_layout())

    def _on_layout_changed(self, layout):
        self._pending_layout = layout
        self._mark_draft_dirty()

    def _mark_draft_dirty(self):
        self._set_save_status("Autosaving draft...")
        self._autosave_timer.start()

    def _save_draft(self):
        """Persist the complete workflow draft after edits settle or on click."""
        if self._pending_layout is not None:
            save_workflow_layout(self._pending_layout)
            self._pending_layout = None
        else:
            save_workflow_layout(self.canvas.current_layout())
        self._set_save_status("Draft saved.")

    def _set_save_status(self, text):
        if hasattr(self, "save_status"):
            self.save_status.setText(text)
