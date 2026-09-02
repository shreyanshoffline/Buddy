from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QMenu, QHBoxLayout
)
from PySide6.QtCore import Qt
from .theme import (
    SIDEBAR_BG, BORDER_COLOR, HOVER_BG_COLOR, PRESSED_BG_COLOR, ACTIVE_BG_COLOR, PRIMARY_COLOR,
    SIDEBAR_COLLAPSED_WIDTH, SIDEBAR_EXPANDED_WIDTH, ICON_SIZE, TEXT_COLOR_MUTED, TEXT_COLOR_DARK
)

from .icons import get_svg_icon, ICONS

class NavButton(QPushButton):
    def __init__(self, label, icon_path, small=False):
        super().__init__()
        self.label_text = label
        self.icon_path = icon_path
        self.small = small
        self.is_active = False
        self.setIcon(get_svg_icon(icon_path, size=ICON_SIZE if not small else 14))
        self.setIconSize(self.iconSize())
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.set_collapsed(True)

    def set_active(self, active: bool):
        self.is_active = active
        self.set_collapsed(not self._expanded if hasattr(self, '_expanded') else True)

    def set_collapsed(self, collapsed: bool):
        self._expanded = not collapsed
        active_bg = f"background: {ACTIVE_BG_COLOR};" if self.is_active else "background: transparent;"
        active_border = f"border-left: 2px solid {PRIMARY_COLOR};" if self.is_active else "border-left: 2px solid transparent;"

        if collapsed:
            self.setText("")
            self.setToolTip(self.label_text)
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: center;
                    padding: 0px;
                    border-radius: 8px;
                    {active_border}
                    {active_bg}
                    font-size: {"12px" if self.small else "13px"};
                    font-weight: {"600" if self.is_active else ("normal" if self.small else "500")};
                    color: {PRIMARY_COLOR if self.is_active else TEXT_COLOR_DARK};
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
        else:
            self.setText(f"  {self.label_text}")
            self.setToolTip(self.label_text)
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 0px 8px;
                    border-radius: 8px;
                    {active_border}
                    {active_bg}
                    font-size: {"12px" if self.small else "13px"};
                    font-weight: {"600" if self.is_active else ("normal" if self.small else "500")};
                    color: {PRIMARY_COLOR if self.is_active else TEXT_COLOR_DARK};
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)



# --- Slim & Collapsible Sidebar (animated, properly centered) ---
class Sidebar(QFrame):
    def __init__(self, on_chat_click_callback=None, on_new_chat_callback=None, on_delete_chat_callback=None):
        super().__init__()
        self.is_expanded = False
        self.on_chat_click_callback = on_chat_click_callback
        self.on_new_chat_callback = on_new_chat_callback
        self.on_delete_chat_callback = on_delete_chat_callback
        self.recent_buttons = []


        self.setStyleSheet(f"""
            QFrame {{ 
                background: {SIDEBAR_BG}; 
                border-right: 1px solid {BORDER_COLOR}; 
                border-top-left-radius: 16px; 
                border-bottom-left-radius: 16px;
            }}
            QPushButton {{ 
                text-align: left; 
                padding: 6px 5px; 
                border-radius: 8px; 
                color: {TEXT_COLOR_DARK}; 
                font-size: 13px; 
                font-weight: 500; 
                border: none; 
                background: transparent; 
            }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        self.setToolTip("Click to expand/collapse")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 14, 5, 14)
        self.layout.setSpacing(6)

        # Main Navigation Buttons
        self.btn_new = NavButton("New chat", ICONS["plus"])
        self.btn_lib = NavButton("Library", ICONS["library"])
        self.btn_billing = NavButton("Billing", ICONS["settings"])
        self.btn_settings = NavButton("Settings", ICONS["settings"])
        
        # Recent Chats Section Header
        self.lbl_recents = QLabel("Recents")
        self.lbl_recents.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; font-weight: bold; background: transparent; border: none; margin-top: 8px; margin-bottom: 2px;")
        self.lbl_recents.hide()

        self.layout.addWidget(self.btn_new)
        self.layout.addWidget(self.btn_lib)
        self.layout.addWidget(self.btn_billing)
        self.layout.addWidget(self.lbl_recents)
        
        # Vertical box to hold dynamic recent chat buttons
        self.recents_container = QVBoxLayout()
        self.recents_container.setContentsMargins(0, 0, 0, 0)
        self.recents_container.setSpacing(2)
        self.layout.addLayout(self.recents_container)

        self.layout.addStretch()
        self.layout.addWidget(self.btn_settings)
        if self.on_new_chat_callback:
            self.btn_new.clicked.connect(self.on_new_chat_callback)

    def refresh_recents(self, on_chat_click=None, on_delete_chat=None):
        """Erases existing buttons and rebuilds fresh ones from storage.py."""
        if on_chat_click:
            self.on_chat_click_callback = on_chat_click
        if on_delete_chat:
            self.on_delete_chat_callback = on_delete_chat

        # 1. Clear old buttons from layout and memory
        for row in self.recent_buttons:
            self.recents_container.removeWidget(row)
            row.deleteLater()
        self.recent_buttons.clear()

        # 2. Fetch current conversations via core.py
        import core
        chats = core.get_recent_conversations(limit=5, exclude_private=True)

        # 3. Render a row for each chat
        for chat in chats:
            title = chat.get("title", "Untitled Chat")
            chat_id = chat["id"]

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            btn = QPushButton(title)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.setToolTip(f"{title}\n(right-click to delete)")
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-weight: normal;
                    font-size: 12px;
                    padding: 6px 8px;
                    text-align: left;
                    border: none;
                    background: transparent;
                    color: {TEXT_COLOR_DARK};
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
            if self.on_chat_click_callback:
                btn.clicked.connect(lambda checked=False, cid=chat_id: self.on_chat_click_callback(cid))
            if hasattr(self, 'on_delete_chat_callback') and self.on_delete_chat_callback:
                btn.customContextMenuRequested.connect(
                    lambda pos, cid=chat_id, widget=btn: self._show_chat_context_menu(cid, widget.mapToGlobal(pos))
                )

            row_layout.addWidget(btn)
            row.setVisible(self.is_expanded)

            self.recents_container.addWidget(row)
            self.recent_buttons.append(row)

    def mousePressEvent(self, event):
        """Click anywhere empty on sidebar to expand/collapse."""
        if event.button() == Qt.LeftButton:
            self.is_expanded = not self.is_expanded
            self.setFixedWidth(SIDEBAR_EXPANDED_WIDTH if self.is_expanded else SIDEBAR_COLLAPSED_WIDTH)
            
            # Toggle text visibility
            self.lbl_recents.setVisible(self.is_expanded)
            self.btn_new.set_collapsed(not self.is_expanded)
            self.btn_lib.set_collapsed(not self.is_expanded)
            self.btn_billing.set_collapsed(not self.is_expanded)
            self.btn_settings.set_collapsed(not self.is_expanded)
            for row in self.recent_buttons:
                row.setVisible(self.is_expanded)

    def _show_chat_context_menu(self, conversation_id, global_pos):
        menu = QMenu()
        delete_action = menu.addAction("Delete chat")
        action = menu.exec(global_pos)
        if action == delete_action and hasattr(self, 'on_delete_chat_callback') and self.on_delete_chat_callback:
            self.on_delete_chat_callback(conversation_id)