"""Billing page — real Stripe Checkout, not a mock popup."""
from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal

import core
import billing_client
from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK, ON_PRIMARY_TEXT,
    BORDER_COLOR, SECTION_CARD_BG, HOVER_BG_COLOR, PRESSED_BG_COLOR,
    ACTIVE_BG_COLOR, TEXT_COLOR_DARK,
)

TIER_LABELS = {"free": "Free Plan", "pro": "Buddy Pro", "max": "Buddy MAX"}


class _StatusWorker(QThread):
    """Fetches subscription status off the main thread so Refresh never
    freezes the UI while waiting on the network."""
    done = Signal(str)

    def __init__(self, buddy_user_id):
        super().__init__()
        self.buddy_user_id = buddy_user_id

    def run(self):
        tier = billing_client.fetch_subscription_tier(self.buddy_user_id)
        self.done.emit(tier)


class BillingPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Billing", "Choose the Buddy plan that matches your workflow.", parent, close_callback)
        self.buddy_user_id = core.get_or_create_buddy_user_id()
        self._worker = None

        self._build_status_card()
        self._build_plan_grid()
        self.main_layout.addStretch()
        self.refresh_status()

    # --- Current plan / status card ---
    def _build_status_card(self):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background: {SECTION_CARD_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)

        text_col = QVBoxLayout()
        title = QLabel("Current plan")
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        text_col.addWidget(title)

        self.status_label = QLabel("Checking...")
        self.status_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        text_col.addWidget(self.status_label)
        layout.addLayout(text_col)
        layout.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(8)

        manage_btn = QPushButton("Manage billing")
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setToolTip("Open Stripe to manage your subscription and payment method")
        manage_btn.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: 600; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
        """)
        manage_btn.clicked.connect(self._open_billing_portal)
        actions.addWidget(manage_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setToolTip("Check for a subscription update after paying")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_COLOR}; border-radius: 8px;
                padding: 6px 12px; font-size: 11px; color: {TEXT_COLOR_DARK}; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        refresh_btn.clicked.connect(self.refresh_status)
        actions.addWidget(refresh_btn)
        layout.addLayout(actions)

        self.main_layout.addWidget(card)

    def refresh_status(self):
        self.status_label.setText("Checking...")
        self._worker = _StatusWorker(self.buddy_user_id)
        self._worker.done.connect(self._on_status_loaded)
        self._worker.start()

    def _on_status_loaded(self, tier):
        core.update_profile(subscription_tier=tier)
        self.status_label.setText(TIER_LABELS.get(tier, "Free Plan"))

    # --- Plan grid ---
    def _build_plan_grid(self):
        plans = [
            {
                "title": "Free Plan", "price": "Free", "price_key": None,
                "subtitle": "Everyday AI access with daily resets",
                "details": "Access to good AI models but degrades down to free tier ones after usage limit runs out. It resets every day.",
                "highlight": False, "badge": None,
            },
            {
                "title": "Hacky Buddy Plan", "price": "Free for Hack Club", "price_key": None,
                "subtitle": "Teen-approved community access",
                "details": "If you're 13-18 and part of Hack Club, plug in your free Hack Club AI API key in Settings for free Buddy credits, fully customizable, with limited SuperBuddy access.",
                "highlight": False, "badge": "Hack Club",
            },
            {
                "title": "Buddy Pro", "price": "$7.99/mo", "price_key": "pro_monthly",
                "subtitle": "More usage, better access, steady updates",
                "details": "Access to SuperBuddy and 3x more usage credits than the Free Plan, plus Buddy updates (a bit later than MAX).",
                "highlight": True, "badge": "Popular",
            },
            {
                "title": "Buddy MAX", "price": "$11.99/mo", "price_key": "max_monthly",
                "subtitle": "Everything in Pro, plus beta access",
                "details": "Twice everything in Pro, plus beta versions of new Buddy releases on the day they launch.",
                "highlight": True, "badge": "Best Value",
            },
        ]

        row = QHBoxLayout()
        row.setSpacing(12)
        for index, plan in enumerate(plans):
            card = self._build_plan_card(plan)
            row.addWidget(card)
            if index % 2 == 1:
                self._flush_row(row)
                row = QHBoxLayout()
                row.setSpacing(12)
        if row.count():
            self._flush_row(row)

    def _flush_row(self, row):
        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addLayout(row)
        self.main_layout.addWidget(container)

    def _build_plan_card(self, plan):
        frame = QFrame()
        frame.setFixedHeight(210)
        frame.setStyleSheet(self._plan_frame_style(plan["highlight"]))

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        if plan["badge"]:
            badge = QLabel(plan["badge"])
            badge.setStyleSheet(f"padding: 4px 8px; border-radius: 999px; background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; font-size: 10px; font-weight: 700;")
            layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel(plan["title"])
        title_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 16px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(title_label)

        price_label = QLabel(plan["price"])
        price_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        layout.addWidget(price_label)

        subtitle_label = QLabel(plan["subtitle"])
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(subtitle_label)

        details_label = QLabel(plan["details"])
        details_label.setWordWrap(True)
        details_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(details_label)
        layout.addStretch()

        if plan["price_key"]:
            btn = QPushButton("Subscribe")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Opens Stripe Checkout in your browser for {plan['title']}")
            btn.setStyleSheet(f"""
                QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                    border-radius: 8px; padding: 8px; font-size: 12px; font-weight: 600; }}
            """)
            btn.clicked.connect(lambda _, k=plan["price_key"], t=plan["title"]: self._subscribe(k, t))
            layout.addWidget(btn)
        else:
            note = QLabel("No payment needed")
            note.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; font-style: italic; background: transparent; border: none;")
            layout.addWidget(note)

        return frame

    def _plan_frame_style(self, highlighted):
        border = f"2px solid {PRIMARY_COLOR}" if highlighted else f"1px solid {BORDER_COLOR}"
        bg = ACTIVE_BG_COLOR if highlighted else "rgba(255,255,255,0.04)"
        return f"QFrame {{ background: {bg}; border: {border}; border-radius: 12px; }}"

    def _subscribe(self, price_key, plan_title):
        try:
            billing_client.start_checkout(self.buddy_user_id, price_key)
            QMessageBox.information(
                self, "Redirecting to checkout",
                f"Opening secure Stripe checkout for {plan_title} in your browser.\n\n"
                "After paying, come back here and click 'Refresh status'."
            )
        except billing_client.BillingNotConfigured as e:
            QMessageBox.warning(self, "Billing not set up", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Checkout failed", f"Couldn't start checkout: {e}")

    def _open_billing_portal(self):
        try:
            billing_client.open_billing_portal(self.buddy_user_id)
        except billing_client.BillingNotConfigured as e:
            QMessageBox.warning(self, "Billing unavailable", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Billing portal failed", f"Couldn't open billing management: {e}")