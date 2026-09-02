"""Chat library: searchable list of past conversations, with All/Favorites/
Archived filter tabs, per-chat favorite/private/archive controls, and
right-click delete."""
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QFrame, QPushButton, QMenu,
)
from PySide6.QtCore import Qt

import core
from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, HOVER_BG_COLOR, PRESSED_BG_COLOR,
    PRIMARY_COLOR, PRIMARY_COLOR_DARK, ON_PRIMARY_TEXT, ACTIVE_BG_COLOR,
    BORDER_COLOR, INPUT_BG, TEXT_COLOR_DARK, TEXT_COLOR_SUBTITLE,
)


class LibraryPage(CardPage):
    FILTERS = [("all", "All"), ("favorites", "★ Favorites"), ("archived", "🗄 Archived")]

    def __init__(self, parent=None, close_callback=None, on_chat_selected=None, on_delete_chat=None):
        super().__init__("Library", "Browse your past chat histories and conversations with Buddy.", parent, close_callback)

        self.on_chat_selected = on_chat_selected
        self.on_delete_chat = on_delete_chat
        self.all_chats = []
        self.chat_item_widgets = []
        self.active_filter = "all"

        # --- Filter tabs: All / Favorites / Archived ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.filter_buttons = {}
        for key, label in self.FILTERS:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.setToolTip(f"Show {label.lstrip('★🗄 ')} chats")
            btn.clicked.connect(lambda checked=False, k=key: self._on_filter_selected(k))
            filter_row.addWidget(btn)
            self.filter_buttons[key] = btn
        filter_row.addStretch()
        self.main_layout.addLayout(filter_row)
        self._restyle_filter_buttons()

        # --- Search bar ---
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("\U0001F50D  Search chats...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setToolTip("Search chats by title or content")
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background-color: {INPUT_BG};
                border: 1.2px solid {BORDER_COLOR};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 12px;
                color: {TEXT_COLOR_DARK};
            }}
            QLineEdit:focus {{
                border: 1.2px solid {PRIMARY_COLOR};
                background-color: {HOVER_BG_COLOR};
            }}
        """)
        self.search_box.textChanged.connect(self._filter_chats)
        self.search_box.returnPressed.connect(lambda: self._filter_chats(self.search_box.text()))
        search_row.addWidget(self.search_box)
        self.main_layout.addLayout(search_row)

        self.history_label = QLabel("Recent Chats")
        self.history_label.setStyleSheet(f"""
            QLabel {{
                color: {CARD_TEXT_COLOR}; 
                font-size: 13px; 
                font-weight: bold; 
                background: transparent; 
                border: none;
                margin-top: 8px;
            }}
        """)
        self.main_layout.addWidget(self.history_label)

        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(6)
        self.main_layout.addLayout(self.list_container)

        self.no_results_label = QLabel("No chats here yet.")
        self.no_results_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        self.no_results_label.setVisible(False)
        self.main_layout.addWidget(self.no_results_label)

        self.main_layout.addStretch()

        self.refresh_chats()

    def _restyle_filter_buttons(self):
        for key, btn in self.filter_buttons.items():
            active = (key == self.active_filter)
            bg = ACTIVE_BG_COLOR if active else "transparent"
            color = PRIMARY_COLOR if active else TEXT_COLOR_SUBTITLE
            weight = "600" if active else "500"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: {color}; font-weight: {weight};
                    border: none; border-radius: 8px; padding: 5px 10px; font-size: 11.5px;
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)

    def _on_filter_selected(self, key):
        self.active_filter = key
        for k, btn in self.filter_buttons.items():
            btn.setChecked(k == key)
        self._restyle_filter_buttons()
        query = self.search_box.text().strip()
        if query:
            self._filter_chats(query)
        else:
            self.refresh_chats()

    def refresh_chats(self):
        """Reload the chat list for the active filter (most recent first)."""
        try:
            self.all_chats = core.get_recent_conversations(limit=200, filter_mode=self.active_filter)
        except Exception:
            self.all_chats = []
        self._render_chat_list(self.all_chats)

    def _clear_list(self):
        while self.list_container.count():
            item = self.list_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.chat_item_widgets = []

    def _render_chat_list(self, chats):
        self._clear_list()
        self.no_results_label.setText(
            "No chats match your search." if self.search_box.text().strip() else
            {"all": "No chats here yet.", "favorites": "No favorites yet — star a chat to pin it here.",
             "archived": "Nothing archived."}.get(self.active_filter, "No chats here yet.")
        )
        self.no_results_label.setVisible(len(chats) == 0)
        for chat in chats:
            title = chat.get("title") or "Untitled Chat"
            chat_id = chat["id"]
            is_private = bool(chat.get("is_private"))
            is_favorite = bool(chat.get("is_favorite"))
            is_archived = bool(chat.get("is_archived"))

            box = QFrame()
            box.setCursor(Qt.PointingHandCursor)
            box.setToolTip(f"{title}\n(right-click for more options)")
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: {INPUT_BG};
                    border: 1.2px solid {BORDER_COLOR};
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    border: 1.2px solid {PRIMARY_COLOR};
                    background-color: {HOVER_BG_COLOR};
                }}
            """)
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 8)

            label = QLabel(title)
            label.setStyleSheet(f"font-size: 12px; color: {TEXT_COLOR_DARK}; background: transparent; border: none;")
            label.setWordWrap(False)
            box_layout.addWidget(label)
            box_layout.addStretch()

            star_btn = QPushButton("★" if is_favorite else "☆")
            star_btn.setFlat(True)
            star_btn.setCursor(Qt.PointingHandCursor)
            star_btn.setToolTip("Favorited — click to unmark" if is_favorite else "Mark as favorite")
            star_btn.setStyleSheet(f"""
                QPushButton {{ border: none; background: transparent; border-radius: 4px; font-size: 13px; padding: 2px;
                    color: {PRIMARY_COLOR if is_favorite else TEXT_COLOR_SUBTITLE}; }}
                QPushButton:hover {{ background: {PRESSED_BG_COLOR}; }}
            """)
            star_btn.clicked.connect(lambda checked=False, c_id=chat_id, cur=is_favorite: self._toggle_favorite(c_id, cur))
            box_layout.addWidget(star_btn)

            lock_btn = QPushButton("🔒" if is_private else "🔓")
            lock_btn.setFlat(True)
            lock_btn.setCursor(Qt.PointingHandCursor)
            lock_btn.setToolTip("Private — click to unmark" if is_private else "Mark as private")
            lock_btn.setStyleSheet(f"""
                QPushButton {{ border: none; background: transparent; border-radius: 4px; font-size: 12px; padding: 2px; }}
                QPushButton:hover {{ background: {PRESSED_BG_COLOR}; }}
            """)
            lock_btn.clicked.connect(lambda checked=False, c_id=chat_id, cur=is_private: self._toggle_private(c_id, cur))
            box_layout.addWidget(lock_btn)

            box.setContextMenuPolicy(Qt.CustomContextMenu)
            box.customContextMenuRequested.connect(
                lambda pos, c_id=chat_id, w=box, arch=is_archived: self._show_context_menu(c_id, w.mapToGlobal(pos), arch)
            )
            box.mousePressEvent = lambda event, c_id=chat_id: self._select_chat(c_id)

            self.list_container.addWidget(box)
            self.chat_item_widgets.append((box, title.lower()))

    def _show_context_menu(self, chat_id, global_pos, is_archived):
        menu = QMenu()
        archive_action = menu.addAction("Unarchive" if is_archived else "Archive")
        delete_action = menu.addAction("Delete chat")
        action = menu.exec(global_pos)
        if action == archive_action:
            self._toggle_archived(chat_id, is_archived)
        elif action == delete_action and self.on_delete_chat:
            self.on_delete_chat(chat_id)

    def _toggle_private(self, chat_id, currently_private):
        core.set_conversation_private(chat_id, not currently_private)
        self._refresh_after_change()

    def _toggle_favorite(self, chat_id, currently_favorite):
        core.set_conversation_favorite(chat_id, not currently_favorite)
        self._refresh_after_change()

    def _toggle_archived(self, chat_id, currently_archived):
        core.set_conversation_archived(chat_id, not currently_archived)
        self._refresh_after_change()

    def _refresh_after_change(self):
        query = self.search_box.text().strip()
        if query:
            self._filter_chats(query)
        else:
            self.refresh_chats()

    def _filter_chats(self, query):
        query = (query or "").strip()
        if not query:
            self._render_chat_list(self.all_chats)
            return
        try:
            results = core.search_conversations(query, limit=200, filter_mode=self.active_filter)
        except Exception:
            results = [c for c in self.all_chats if query.lower() in (c.get("title") or "").lower()]
        self._render_chat_list(results)

    def _select_chat(self, chat_id):
        """Opens the clicked chat; the main window handles switching off the settings/library page."""
        if self.on_chat_selected:
            self.on_chat_selected(chat_id)