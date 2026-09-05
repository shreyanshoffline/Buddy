"""Base scrollable card layout shared by Settings and Library pages."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton, QHBoxLayout, QFrame
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
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
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

        self.account_chip = QFrame()
        self.account_chip.setStyleSheet("QFrame { background: rgba(51, 142, 218, 0.10); border: 1px solid rgba(51, 142, 218, 0.24); border-radius: 10px; }")
        account_layout = QVBoxLayout(self.account_chip)
        account_layout.setContentsMargins(10, 7, 10, 7)
        account_layout.setSpacing(1)
        self.account_name_label = QLabel("")
        self.account_name_label.setStyleSheet("color: #1f2937; font-size: 12px; font-weight: 700; background: transparent; border: none;")
        account_layout.addWidget(self.account_name_label)
        self.account_status_label = QLabel("Logged in")
        self.account_status_label.setStyleSheet("color: #338eda; font-size: 10px; background: transparent; border: none;")
        account_layout.addWidget(self.account_status_label)
        self.main_layout.addWidget(self.account_chip, alignment=Qt.AlignmentFlag.AlignRight)

        self.account_button = QPushButton("Sign in / create account")
        self.account_button.setCursor(Qt.PointingHandCursor)
        self.account_button.setStyleSheet("QPushButton { background: transparent; border: none; color: #338eda; font-size: 11px; font-weight: 600; }")
        self.account_button.clicked.connect(self._open_account_page)
        self.main_layout.addWidget(self.account_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.refresh_account_header()

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

    @staticmethod
    def _account_profile():
        try:
            import core
            return core.get_profile()
        except Exception:
            return {}

    def refresh_account_header(self):
        profile = self._account_profile()
        name = (profile.get("name") or "").strip()
        signed_in = bool(profile.get("auth_provider") or name)
        if signed_in and name:
            self.account_name_label.setText(name)
            status = profile.get("hackclub_verification_status") or profile.get("auth_provider") or "Logged in"
            self.account_status_label.setText(str(status).replace("_", " ").title() if status != "email" else "Local profile")
            self.account_chip.setVisible(True)
            self.account_button.setVisible(False)
        else:
            self.account_chip.setVisible(False)
            self.account_button.setVisible(True)

    def _open_account_page(self):
        window = self.window()
        if hasattr(window, "show_onboarding_view"):
            window.show_onboarding_view()