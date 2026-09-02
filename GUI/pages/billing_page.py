"""Billing page with plan cards for Buddy subscriptions."""
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QMessageBox
from PySide6.QtCore import Qt

from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, ON_PRIMARY_TEXT,
    BORDER_COLOR, SECTION_CARD_BG, HOVER_BG_COLOR, PRESSED_BG_COLOR,
    ACTIVE_BG_COLOR, TEXT_COLOR_DARK,
)


class BillingPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Billing", "Choose the Buddy plan that matches your workflow.", parent, close_callback)
        self._build_summary_card()
        self._build_plan_grid()
        self.main_layout.addStretch()

    def _build_summary_card(self):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {SECTION_CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)

        title = QLabel("Usage & perks")
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(title)

        summary = QLabel(
            "Free credits reset daily. Pro unlocks SuperBuddy access and extra usage. MAX adds early access to new Buddy builds and the highest limits."
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; line-height: 1.5; background: transparent; border: none;")
        layout.addWidget(summary)
        self.main_layout.addWidget(card)

    def _build_plan_grid(self):
        plans = [
            {
                "title": "Free Plan",
                "price": "Free",
                "subtitle": "Everyday AI access with daily resets",
                "details": (
                    "Access to good AI models but degrades down to free tier ones after usage limit runs out. "
                    "It resets every day."
                ),
                "highlight": False,
                "badge": None,
            },
            {
                "title": "Hacky Buddy Plan",
                "price": "Free for Hack Club",
                "subtitle": "Teen-approved community access",
                "details": (
                    "If you are a teenager (13-18) and are part of the nonprofit Hack Club, you can plug in your free API key from Hack Club AI and get free Buddy credits. "
                    "It is completely customizable to your interests and includes limited SuperBuddy access."
                ),
                "highlight": False,
                "badge": "Hack Club",
            },
            {
                "title": "Buddy Pro",
                "price": "$7.99/mo or $59.99/yr",
                "subtitle": "More usage, better access, steady updates",
                "details": (
                    "Access to SuperBuddy and 3x more usage credits than the Free Plan. Includes Buddy updates, though they arrive a bit later."
                ),
                "highlight": True,
                "badge": "Popular",
            },
            {
                "title": "Buddy MAX",
                "price": "$11.99/mo or $99.99/yr",
                "subtitle": "Everything in Pro, plus beta access",
                "details": (
                    "Twice everything in Pro, plus beta versions of new Buddy releases on the day they launch."
                ),
                "highlight": True,
                "badge": "Best Value",
            },
        ]

        row = QHBoxLayout()
        row.setSpacing(12)
        for index, plan in enumerate(plans):
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(190)
            btn.setStyleSheet(self._plan_button_style(plan["highlight"]))
            btn.clicked.connect(lambda _, plan_name=plan["title"], plan_details=plan["details"]: QMessageBox.information(
                self,
                plan_name,
                plan_details,
            ))

            card_layout = QVBoxLayout(btn)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            if plan["badge"]:
                badge = QLabel(plan["badge"])
                badge.setAlignment(Qt.AlignmentFlag.AlignLeft)
                badge.setStyleSheet(f"padding: 4px 8px; border-radius: 999px; background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; font-size: 10px; font-weight: 700; margin-bottom: 2px;")
                card_layout.addWidget(badge)

            title_label = QLabel(plan["title"])
            title_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 16px; font-weight: 700; background: transparent; border: none;")
            card_layout.addWidget(title_label)

            price_label = QLabel(plan["price"])
            price_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
            card_layout.addWidget(price_label)

            subtitle_label = QLabel(plan["subtitle"])
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; background: transparent; border: none;")
            card_layout.addWidget(subtitle_label)

            details_label = QLabel(plan["details"])
            details_label.setWordWrap(True)
            details_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 11px; background: transparent; border: none;")
            card_layout.addWidget(details_label)
            card_layout.addStretch()

            row.addWidget(btn)
            if index % 2 == 1:
                container = QFrame()
                container.setStyleSheet("background: transparent; border: none;")
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                container_layout.addLayout(row)
                self.main_layout.addWidget(container)
                row = QHBoxLayout()
                row.setSpacing(12)

        if row.count():
            container = QFrame()
            container.setStyleSheet("background: transparent; border: none;")
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)
            container_layout.addLayout(row)
            self.main_layout.addWidget(container)

    def _plan_button_style(self, highlighted):
        border = f"2px solid {PRIMARY_COLOR}" if highlighted else f"1px solid {BORDER_COLOR}"
        bg = ACTIVE_BG_COLOR if highlighted else "rgba(255,255,255,0.04)"
        return f"""
            QPushButton {{
                background: {bg};
                border: {border};
                border-radius: 12px;
                padding: 0;
                text-align: left;
                color: {TEXT_COLOR_DARK};
                font-size: 12px;
                font-weight: 500;
                min-height: 190px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG_COLOR};
                border: 2px solid {PRIMARY_COLOR};
            }}
            QPushButton:pressed {{
                background: {PRESSED_BG_COLOR};
            }}
        """
