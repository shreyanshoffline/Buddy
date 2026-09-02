"""Base scrollable card layout shared by Settings and Library pages."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt

from ..theme import (
    CARD_TEXT_COLOR, CARD_TEXT_SIZE, CARD_TEXT_WEIGHT,
    CARD_SUBTITLE_COLOR, CARD_SUBTITLE_SIZE,
    CARD_BG_TOP, CARD_BG_MID, CARD_BG_BOTTOM,
)

class CardPage(QWidget):
    def __init__(self, title, subtitle="", parent=None, close_callback=None):
        super().__init__(parent)
        self.setObjectName("CardPage")
        
        # 1. Added QScrollArea and ScrollContent transparency to your existing stylesheet
        self.setStyleSheet(f"""
            QWidget#CardPage {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0.0 {CARD_BG_TOP},
                    stop:0.7 {CARD_BG_MID},
                    stop:1.0 {CARD_BG_BOTTOM}
                );
                border-radius: 14px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QWidget#ScrollContent {{
                background: transparent;
            }}
        """)
        
        # 2. Setup a base layout for the card itself
        self.base_layout = QVBoxLayout(self)
        self.base_layout.setContentsMargins(0, 0, 0, 0)
        
        # 3. Create the Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 4. Create the inner container that holds your actual widgets
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        
        # 5. Bind your existing self.main_layout to the inner scroll_content
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setContentsMargins(18, 18, 18, 18) # Reduced from 24
        self.main_layout.setSpacing(10)                     # Tightened spacing
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 6. Put the content into the scroll area, and the scroll area into the card
        self.scroll_area.setWidget(self.scroll_content)
        self.base_layout.addWidget(self.scroll_area)

        # --- YOUR EXISTING CODE STARTS HERE ---
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {CARD_TEXT_COLOR};
                font-size: {CARD_TEXT_SIZE}px;
                font-weight: {CARD_TEXT_WEIGHT};
                background: transparent;
                border: none;
            }}
        """)
        self.main_layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(f"""
                QLabel {{
                    color: {CARD_SUBTITLE_COLOR};
                    font-size: {CARD_SUBTITLE_SIZE}px;
                    background: transparent;
                    border: none;
                }}
            """)
            self.main_layout.addWidget(subtitle_label)