"""Saved creations made by Buddy."""
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import base64

import core
from .card_page import CardPage
from ..theme import CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, BORDER_COLOR, INPUT_BG, TEXT_COLOR_DARK


class ArtifactsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Artifacts", "Images and other things Buddy has made for you.", parent, close_callback)
        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(10)
        self.main_layout.addLayout(self.items_layout)
        self.refresh_artifacts()

    def refresh_artifacts(self):
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        artifacts = core.list_artifacts()
        if not artifacts:
            empty = QLabel("Your creations will appear here.")
            empty.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; background: transparent; border: none;")
            self.items_layout.addWidget(empty)
            return
        for artifact in artifacts:
            self.items_layout.addWidget(self._artifact_card(artifact))

    def _artifact_card(self, artifact):
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 10px; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        title_row = QHBoxLayout()
        title = QLabel(artifact.get("title", "Untitled artifact"))
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 14px; font-weight: 700; background: transparent; border: none;")
        title_row.addWidget(title)
        title_row.addStretch()
        delete = QPushButton("Delete")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda: self._delete(artifact["id"]))
        delete.setStyleSheet(f"QPushButton {{ color: {PRIMARY_COLOR}; border: none; background: transparent; font-size: 11px; }}")
        title_row.addWidget(delete)
        layout.addLayout(title_row)

        image = QPixmap()
        content = artifact.get("content", "")
        if content.startswith("data:"):
            image.loadFromData(base64.b64decode(content.split(",", 1)[1]))
        elif content.startswith("/"):
            image.load(content)
        if not image.isNull():
            preview = QLabel()
            preview.setPixmap(image.scaled(360, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            preview.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(preview)
        else:
            link = QLabel(content)
            link.setWordWrap(True)
            link.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            link.setStyleSheet(f"color: {TEXT_COLOR_DARK}; background: transparent; border: none;")
            layout.addWidget(link)
        return card

    def _delete(self, artifact_id):
        core.delete_artifact(artifact_id)
        self.refresh_artifacts()
