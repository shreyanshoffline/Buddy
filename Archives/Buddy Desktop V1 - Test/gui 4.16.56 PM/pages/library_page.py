"""Chat library: searchable list of past conversations, private-chat lock
toggle, and right-click delete."""
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QFrame, QPushButton, QMenu,
)
from PySide6.QtCore import Qt

import core
from .card_page import CardPage
from ..theme import CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, HOVER_BG_COLOR

class LibraryPage(CardPage):
    def __init__(self, parent=None, close_callback=None, on_chat_selected=None, on_delete_chat=None):
        super().__init__("Library", "Browse your past chat histories and conversations with Buddy.", parent, close_callback)

        self.on_chat_selected = on_chat_selected
        self.on_delete_chat = on_delete_chat
        self.all_chats = []          # full list, most recent first: [{"id":..., "title":...}, ...]
        self.chat_item_widgets = []  # (frame, title_lower) pairs currently shown

        # --- Rounded pill search bar ---
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("\U0001F50D  Search chats...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1.2px solid #d2d9e0;
                border-radius: 16px;
                padding: 8px 16px;
                font-size: 12px;
                color: #24292f;
            }
            QLineEdit:focus {
                border: 1.2px solid #0969da;
                background-color: #f6f8fa;
            }
        """)
        self.search_box.textChanged.connect(self._filter_chats)
        self.search_box.returnPressed.connect(lambda: self._filter_chats(self.search_box.text()))
        search_row.addWidget(self.search_box)
        self.main_layout.addLayout(search_row)

        # 2. Section Header
        self.history_label = QLabel("Recent Chats")
        self.history_label.setStyleSheet(f"""
            QLabel {{
                color: {CARD_TEXT_COLOR}; 
                font-size: 13px; 
                font-weight: bold; 
                background: transparent; 
                margin-top: 8px;
            }}
        """)
        self.main_layout.addWidget(self.history_label)

        # Container just for the chat list, so we can clear/rebuild it on filter/refresh
        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(6)
        self.main_layout.addLayout(self.list_container)

        self.no_results_label = QLabel("No chats match your search.")
        self.no_results_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent;")
        self.no_results_label.setVisible(False)
        self.main_layout.addWidget(self.no_results_label)

        self.main_layout.addStretch()

        self.refresh_chats()

    def refresh_chats(self):
        """Reload the full chat list from storage (most recent first) and redraw."""
        try:
            self.all_chats = core.get_recent_conversations(limit=200)
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
        self.no_results_label.setVisible(len(chats) == 0)
        for chat in chats:
            title = chat.get("title") or "Untitled Chat"
            chat_id = chat["id"]
            is_private = bool(chat.get("is_private"))

            box = QFrame()
            box.setCursor(Qt.PointingHandCursor)
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: #ffffff;
                    border: 1.2px solid #d2d9e0;
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    border: 1.2px solid #0969da;
                    background-color: {HOVER_BG_COLOR};
                }}
            """)
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 8)

            label = QLabel(title)
            label.setStyleSheet("font-size: 12px; color: #24292f; background: transparent; border: none;")
            label.setWordWrap(False)
            box_layout.addWidget(label)
            box_layout.addStretch()

            lock_btn = QPushButton("🔒" if is_private else "🔓")
            lock_btn.setFlat(True)
            lock_btn.setCursor(Qt.PointingHandCursor)
            lock_btn.setToolTip("Private chat" if is_private else "Mark as private")
            lock_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 12px; }")
            lock_btn.clicked.connect(lambda checked=False, c_id=chat_id, cur=is_private: self._toggle_private(c_id, cur))
            box_layout.addWidget(lock_btn)

            box.setContextMenuPolicy(Qt.CustomContextMenu)
            box.customContextMenuRequested.connect(
                lambda pos, c_id=chat_id, w=box: self._show_context_menu(c_id, w.mapToGlobal(pos))
            )
            box.mousePressEvent = lambda event, c_id=chat_id: self._select_chat(c_id)

            self.list_container.addWidget(box)
            self.chat_item_widgets.append((box, title.lower()))

    def _show_context_menu(self, chat_id, global_pos):
        menu = QMenu()
        delete_action = menu.addAction("Delete chat")
        action = menu.exec(global_pos)
        if action == delete_action and self.on_delete_chat:
            self.on_delete_chat(chat_id)

    def _toggle_private(self, chat_id, currently_private):
        core.set_conversation_private(chat_id, not currently_private)
        self.refresh_chats()
        query = self.search_box.text().strip()
        if query:
            self._filter_chats(query)

    def _filter_chats(self, query):
        query = (query or "").strip()
        if not query:
            self._render_chat_list(self.all_chats)
            return
        try:
            results = core.search_conversations(query, limit=200)
        except Exception:
            results = [c for c in self.all_chats if query.lower() in (c.get("title") or "").lower()]
        self._render_chat_list(results)

    def _select_chat(self, chat_id):
        """Opens the clicked chat; the main window handles switching off the settings/library page."""
        if self.on_chat_selected:
            self.on_chat_selected(chat_id)

# --- Moveable & Resizable Pop-out Overlay Window ---
