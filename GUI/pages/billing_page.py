"""Billing page — real Stripe Checkout, not a mock popup."""
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QMessageBox, QStackedWidget, QWidget, QTableWidget, QTableWidgetItem,
    QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices

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
        super().__init__("Pricing", "Choose the Buddy plan that matches your workflow.", parent, close_callback)
        self.buddy_user_id = core.get_or_create_buddy_user_id()
        self._worker = None
        self.selected_plan = (core.get_profile().get("subscription_tier") or "free").lower()

        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        self.overview_page = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_page)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_layout.setSpacing(12)
        self.stack.addWidget(self.overview_page)

        self.plan_pages = {}
        self._build_status_card()
        self._build_plan_grid()
        self._build_plan_detail_pages()
        self.main_layout.addStretch()
        self.refresh_status()

    def _get_plan_meta(self):
        return {
            "free": {
                "title": "Free Plan",
                "subtitle": "Everyday AI access with daily resets",
                "tag": None,
                "details": "Good daily access with a free reset and lighter feature usage.",
                "price": "Free",
                "features": [
                    "Daily free usage resets",
                    "Basic Buddy chat access",
                    "Lightweight everyday AI support",
                    "Simple onboarding and quick use",
                ],
                "type": "free",
            },
            "hacky": {
                "title": "Hacky Buddy Plan",
                "subtitle": "Free community access for Hack Club members",
                "tag": "Hack Club",
                "details": "Sign in with Hack Club and use your verified API key to activate Buddy access without paying.",
                "price": "Free with Hack Club",
                "features": [
                    "Hack Club verification required",
                    "Use your verified Hack Club AI key",
                    "Buddy access with optional community perks",
                    "Works for eligible students and club members",
                ],
                "type": "hacky",
            },
            "pro": {
                "title": "Buddy Pro",
                "subtitle": "More usage, better access, steady updates",
                "tag": "Popular",
                "details": "Access to more generous usage and the stronger Buddy features without the full MAX tier.",
                "price": "$7.99/mo",
                "features": [
                    "Higher usage than Free",
                    "Strong custom Buddy assistant access",
                    "Priority updates and reliability",
                    "Great for regular personal use",
                ],
                "type": "pro",
            },
            "max": {
                "title": "Buddy MAX",
                "subtitle": "Everything in Pro, plus beta access",
                "tag": "Best Value",
                "details": "Maximum usage, beta access, and the most complete Buddy experience available.",
                "price": "$11.99/mo",
                "features": [
                    "Everything in Buddy Pro",
                    "More generous credits and usage",
                    "Early beta access to new features",
                    "Best for power users",
                ],
                "type": "max",
            },
        }

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

        self.overview_layout.addWidget(card)

    def refresh_status(self):
        self.status_label.setText("Checking...")
        self._worker = _StatusWorker(self.buddy_user_id)
        self._worker.done.connect(self._on_status_loaded)
        self._worker.start()

    def _on_status_loaded(self, tier):
        core.update_profile(subscription_tier=tier)
        self.selected_plan = (tier or "free").lower()
        self.status_label.setText(TIER_LABELS.get(self.selected_plan, "Free Plan"))

    def _build_plan_grid(self):
        plans = [
            {"key": "free", "title": "Free Plan", "price": "Free", "price_key": None,
             "subtitle": "Everyday AI access with daily resets",
             "details": "Access to good AI models but degrades down to free tier ones after usage limit runs out. It resets every day.",
             "highlight": False, "badge": None},
            {"key": "hacky", "title": "Hacky Buddy Plan", "price": "Free with Hack Club", "price_key": None,
             "subtitle": "Teen-approved community access",
             "details": "If you're 13-18 and part of Hack Club, plug in your verified Hack Club AI API key in Settings for Buddy access.",
             "highlight": False, "badge": "Hack Club"},
            {"key": "pro", "title": "Buddy Pro", "price": "$7.99/mo", "price_key": "pro_monthly",
             "subtitle": "More usage, better access, steady updates",
             "details": "Access to SuperBuddy and 3x more usage credits than the Free Plan, plus Buddy updates (a bit later than MAX).",
             "highlight": True, "badge": "Popular"},
            {"key": "max", "title": "Buddy MAX", "price": "$11.99/mo", "price_key": "max_monthly",
             "subtitle": "Everything in Pro, plus beta access",
             "details": "Twice everything in Pro, plus beta versions of new Buddy releases on the day they launch.",
             "highlight": True, "badge": "Best Value"},
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
        self.overview_layout.addWidget(container)

    def _build_plan_card(self, plan):
        frame = QFrame()
        frame.setFixedHeight(240)
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

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        view_btn = QPushButton("View details")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_COLOR}; color: {TEXT_COLOR_DARK};
                border-radius: 8px; padding: 8px; font-size: 11px; font-weight: 600; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        view_btn.clicked.connect(lambda _, key=plan["key"]: self._open_plan_detail(key))
        button_row.addWidget(view_btn)

        if plan["price_key"]:
            subscribe_btn = QPushButton("Subscribe")
            subscribe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            subscribe_btn.setStyleSheet(f"""
                QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                    border-radius: 8px; padding: 8px; font-size: 11px; font-weight: 600; }}
                QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            """)
            subscribe_btn.clicked.connect(lambda _, k=plan["price_key"], t=plan["title"]: self._subscribe(k, t))
            button_row.addWidget(subscribe_btn)
        else:
            status_text = "Selected" if self.selected_plan == plan["key"] else "Select plan"
            action_btn = QPushButton(status_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if self.selected_plan == plan["key"]:
                action_btn.setStyleSheet(f"""
                    QPushButton {{ background: {ACTIVE_BG_COLOR}; color: {PRIMARY_COLOR}; border: 1px solid {PRIMARY_COLOR};
                        border-radius: 8px; padding: 8px; font-size: 11px; font-weight: 700; }}
                    QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                """)
                action_btn.clicked.connect(lambda _, key=plan["key"]: self._selected_plan_click(key))
            else:
                action_btn.setStyleSheet(f"""
                    QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                        border-radius: 8px; padding: 8px; font-size: 11px; font-weight: 600; }}
                    QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
                """)
                action_btn.clicked.connect(lambda _, key=plan["key"]: self._select_plan(key))
            button_row.addWidget(action_btn)

        layout.addLayout(button_row)
        return frame

    def _plan_frame_style(self, highlighted):
        border = f"2px solid {PRIMARY_COLOR}" if highlighted else f"1px solid {BORDER_COLOR}"
        bg = ACTIVE_BG_COLOR if highlighted else "rgba(255,255,255,0.04)"
        return f"QFrame {{ background: {bg}; border: {border}; border-radius: 12px; }}"

    def _build_plan_detail_pages(self):
        for key, meta in self._get_plan_meta().items():
            page = self._create_plan_detail_page(key, meta)
            self.stack.addWidget(page)
            self.plan_pages[key] = page

        compare_page = self._create_compare_page()
        self.stack.addWidget(compare_page)
        self.plan_pages["compare"] = compare_page

    def _open_plan_detail(self, key):
        if key in ("pro", "max"):
            self.stack.setCurrentWidget(self.plan_pages["compare"])
            return
        self.stack.setCurrentWidget(self.plan_pages[key])

    def _create_plan_detail_page(self, key, meta):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(18, 18, 18, 18)
        page_layout.setSpacing(12)

        top_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_COLOR}; color: {TEXT_COLOR_DARK};
                border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
        """)
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.overview_page))
        top_row.addWidget(back_btn)
        top_row.addStretch()
        page_layout.addLayout(top_row)

        title = QLabel(meta["title"])
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 26px; font-weight: 700; background: transparent; border: none;")
        page_layout.addWidget(title)

        if meta["tag"]:
            badge = QLabel(meta["tag"])
            badge.setStyleSheet(f"padding: 5px 10px; border-radius: 999px; background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; font-size: 10px; font-weight: 700;")
            page_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)

        price = QLabel(meta["price"])
        price.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 18px; font-weight: 700; background: transparent; border: none;")
        page_layout.addWidget(price)

        subtitle = QLabel(meta["subtitle"])
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        page_layout.addWidget(subtitle)

        desc = QLabel(meta["details"])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; background: transparent; border: none;")
        page_layout.addWidget(desc)

        features_box = QFrame()
        features_box.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}")
        features_layout = QVBoxLayout(features_box)
        features_layout.setContentsMargins(12, 12, 12, 12)
        features_layout.setSpacing(8)
        features_label = QLabel("Included features")
        features_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
        features_layout.addWidget(features_label)
        for item in meta["features"]:
            row = QLabel(f"•  {item}")
            row.setWordWrap(True)
            row.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; background: transparent; border: none;")
            features_layout.addWidget(row)
        page_layout.addWidget(features_box)

        if key == "hacky":
            link_box = QFrame()
            link_box.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}")
            link_layout = QVBoxLayout(link_box)
            link_layout.setContentsMargins(12, 12, 12, 12)
            link_layout.setSpacing(8)
            question = QLabel('<a href="https://hackclub.com">Not sure what Hack Club is?</a>')
            question.setOpenExternalLinks(True)
            question.setTextInteractionFlags(Qt.TextSelectableByMouse)
            question.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 12px; background: transparent; border: none;")
            link_layout.addWidget(question)

            ai_link = QLabel('<a href="https://ai.hackclub.com">Open Hack Club AI</a>')
            ai_link.setOpenExternalLinks(True)
            ai_link.setTextInteractionFlags(Qt.TextSelectableByMouse)
            ai_link.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 12px; background: transparent; border: none;")
            link_layout.addWidget(ai_link)

            api_note = QLabel("Once signed in and verified, go to the Hack Club AI dashboard and copy your API key into Settings.")
            api_note.setWordWrap(True)
            api_note.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; background: transparent; border: none;")
            link_layout.addWidget(api_note)
            page_layout.addWidget(link_box)

        action_btn = QPushButton()
        if key == "hacky":
            action_btn.setText("Sign in with Hack Club")
            action_btn.setStyleSheet(f"""
                QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                    border-radius: 10px; padding: 10px 14px; font-size: 12px; font-weight: 700; }}
                QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            """)
            action_btn.clicked.connect(self._open_hackclub_signin)
        else:
            is_selected = self.selected_plan == key
            action_btn.setText("Selected" if is_selected else "Select plan")
            if is_selected:
                action_btn.setStyleSheet(f"""
                    QPushButton {{ background: {ACTIVE_BG_COLOR}; color: {PRIMARY_COLOR}; border: 1px solid {PRIMARY_COLOR};
                        border-radius: 10px; padding: 10px 14px; font-size: 12px; font-weight: 700; }}
                    QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                """)
                action_btn.clicked.connect(lambda _, k=key: self._selected_plan_click(k))
            else:
                action_btn.setStyleSheet(f"""
                    QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none;
                        border-radius: 10px; padding: 10px 14px; font-size: 12px; font-weight: 700; }}
                    QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
                """)
                action_btn.clicked.connect(lambda _, k=key: self._select_plan(k))
        page_layout.addWidget(action_btn)
        page_layout.addStretch()
        return page

    def _open_hackclub_signin(self):
        url = QUrl("http://localhost:5000/auth/hackclub/start")
        query = QUrlQuery()
        query.addQueryItem("buddy_user_id", core.get_or_create_buddy_user_id())
        url.setQuery(query)
        QDesktopServices.openUrl(url)

    def _create_compare_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BORDER_COLOR}; color: {TEXT_COLOR_DARK};
                border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
        """)
        back_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.overview_page))
        layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        title = QLabel("Buddy Pro vs Buddy MAX")
        title.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 24px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(title)

        table = QTableWidget(7, 3)
        table.setHorizontalHeaderLabels(["Feature", "Buddy Pro", "Buddy MAX"])
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet(f"""
            QTableWidget {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER_COLOR}; border-radius: 8px; color: {CARD_TEXT_COLOR}; }}
            QHeaderView::section {{ background: rgba(255,255,255,0.05); color: {CARD_TEXT_COLOR}; padding: 8px; border: 1px solid {BORDER_COLOR}; }}
        """)
        rows = [
            ("Usage", "Higher usage", "Maximum usage"),
            ("Access level", "Power user access", "Power user + beta access"),
            ("Feature updates", "Latest stable releases", "Early beta versions"),
            ("Best for", "Regular daily use", "Heavy or advanced use"),
            ("Price", "$7.99/mo", "$11.99/mo"),
            ("Annual savings", "Save 15% with annual billing", "Save 18% with annual billing"),
            ("Recommended", "Solid everyday value", "Best overall value"),
        ]
        for row_idx, (label, pro_val, max_val) in enumerate(rows):
            table.setItem(row_idx, 0, QTableWidgetItem(label))
            table.setItem(row_idx, 1, QTableWidgetItem(pro_val))
            table.setItem(row_idx, 2, QTableWidgetItem(max_val))
        table.resizeColumnsToContents()
        layout.addWidget(table)

        button_box = QFrame()
        button_box.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}")
        button_layout = QVBoxLayout(button_box)
        button_layout.setContentsMargins(12, 12, 12, 12)
        button_layout.setSpacing(10)

        for plan_key, plan_title, monthly_key, annual_key, annual_label in [
            ("pro", "Buddy Pro", "pro_monthly", "pro_annual", "Save 15% / best value"),
            ("max", "Buddy MAX", "max_monthly", "max_annual", "Save 18% / best value"),
        ]:
            group = QFrame()
            group.setStyleSheet(f"QFrame {{ background: transparent; border: 1px solid {BORDER_COLOR}; border-radius: 10px; }}")
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(10, 10, 10, 10)

            title_label = QLabel(plan_title)
            title_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: 700; background: transparent; border: none;")
            group_layout.addWidget(title_label)
            group_layout.addStretch()

            monthly_btn = QPushButton("Subscribe Monthly")
            monthly_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            monthly_btn.setStyleSheet(f"""
                QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 8px;
                    padding: 8px 10px; font-size: 11px; font-weight: 600; }}
                QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            """)
            monthly_btn.clicked.connect(lambda _, k=monthly_key, t=plan_title: self._subscribe(k, t))
            group_layout.addWidget(monthly_btn)

            annual_btn = QPushButton("Subscribe Annually")
            annual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            annual_btn.setStyleSheet(f"""
                QPushButton {{ background: {ACTIVE_BG_COLOR}; color: {PRIMARY_COLOR}; border: 1px solid {PRIMARY_COLOR};
                    border-radius: 8px; padding: 8px 10px; font-size: 11px; font-weight: 700; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            """)
            annual_btn.setToolTip(annual_label)
            annual_btn.clicked.connect(lambda _, k=annual_key, t=plan_title: self._subscribe(k, t))
            group_layout.addWidget(annual_btn)
            button_layout.addWidget(group)

        layout.addWidget(button_box)
        return page

    def _select_plan(self, plan_key):
        self.selected_plan = plan_key
        core.update_profile(subscription_tier=plan_key)
        self.status_label.setText(TIER_LABELS.get(plan_key, "Free Plan"))
        self._refresh_plan_buttons()

    def _selected_plan_click(self, plan_key):
        QMessageBox.information(
            self,
            "Switch plans",
            "Select another plan to switch plans."
        )

    def _refresh_plan_buttons(self):
        for widget in self.stack.widgets():
            if isinstance(widget, QWidget):
                widget.update()
        self.overview_page.update()
        self.stack.setCurrentWidget(self.overview_page)

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