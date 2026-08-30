import sys
import random
import threading
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect, QSizeGrip,
    QDialog, QRadioButton, QButtonGroup, QSizePolicy, QGraphicsOpacityEffect,
    QStackedWidget, QLineEdit, QComboBox
)
from PySide6.QtCore import (
    Qt, QEvent, QPoint, QVariantAnimation, QEasingCurve,
    QPropertyAnimation, QTimer, QSize, QThread, Signal as QtSignal
)
from PySide6.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QKeyEvent,
    QTextDocument, QAction, QColor, QCursor
)
from PySide6.QtSvg import QSvgRenderer
 
import core
from core import process_message, new_message_history, send_and_save_message

from GUI.chat import ChatBubble, ChatInput, FeedbackDialog, AttachmentTray
from GUI.utils import create_buddy_icon, get_svg_icon, ICONS
from GUI.settings import (
    WINDOW_DEFAULT_HEIGHT, WINDOW_DEFAULT_WIDTH, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
    WINDOW_TITLE_TEXT, WINDOW_TITLE_COLOR, WINDOW_TITLE_SIZE, WINDOW_TITLE_WEIGHT,
    WINDOW_HEADER_HEIGHT, WINDOW_HEADER_PADDING_TOP, WINDOW_HEADER_PADDING_RIGHT,
    WINDOW_HEADER_PADDING_BOTTOM, WINDOW_HEADER_PADDING_LEFT, WINDOW_CLOSE_BUTTON_SIZE,
    WINDOW_CLOSE_BUTTON_COLOR, WINDOW_CLOSE_BUTTON_HOVER_BG, WINDOW_CLOSE_BUTTON_HOVER_COLOR,
    WINDOW_CLOSE_BUTTON_FONT_SIZE, WINDOW_BG_TOP, WINDOW_BG_MID, WINDOW_BG_BOTTOM,
    PAGE_BG_TOP, PAGE_BG_MID, PAGE_BG_BOTTOM, CARD_TEXT_COLOR, CARD_TEXT_SIZE,
    CARD_TEXT_WEIGHT, CARD_SUBTITLE_COLOR, CARD_SUBTITLE_SIZE, GREETING_FONT_SIZE,
    GREETING_COLOR, SUBTITLE_FONT_SIZE, SEND_BUTTON_SIZE, INPUT_CONTAINER_HEIGHT,
    PRIMARY_COLOR, PRIMARY_COLOR_DARK, CHAT_BUBBLE_USER, CHAT_BUBBLE_USER_TEXT,
    CHAT_BUBBLE_AGENT, CHAT_BUBBLE_AGENT_TEXT, SIZE_GRIP_SIZE, TEXT_COLOR_SUBTITLE, HOVER_BG_COLOR
)
from GUI.sidebar import Sidebar
from GUI.utils import create_buddy_icon
import storage.storage as db
 
 
class SendWorker(QThread):
    """Runs send_and_save_message off the main thread so the UI stays responsive."""
    finished = QtSignal(dict)   # emits the result dict on success
    error = QtSignal(str)       # emits error message string on failure
    progress = QtSignal(dict)   # emits live agent events (thinking/plan/tool_call/etc)

    def __init__(self, conversation_id, user_text, attachments=None, incognito=False, history=None):
        super().__init__()
        self.conversation_id = conversation_id
        self.user_text = user_text
        self.attachments = attachments
        self.incognito = incognito
        self.history = history
        self.cancel_event = threading.Event()

    def run(self):
        try:
            if self.incognito:
                result = core.process_message_incognito(
                    self.user_text,
                    self.history,
                    on_event=lambda e: self.progress.emit(e),
                    cancel_check=self.cancel_event.is_set,
                )
            else:
                result = send_and_save_message(
                    self.conversation_id,
                    self.user_text,
                    attachments=self.attachments or None,
                    on_event=lambda e: self.progress.emit(e),
                    cancel_check=self.cancel_event.is_set,
                )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class RedoWorker(QThread):
    """Runs redo_assistant_response off the main thread."""
    finished = QtSignal(dict)
    error = QtSignal(str)

    def __init__(self, conversation_id, user_text):
        super().__init__()
        self.conversation_id = conversation_id
        self.user_text = user_text

    def run(self):
        try:
            result = core.redo_assistant_response(self.conversation_id, self.user_text)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class CardPage(QWidget):
    def __init__(self, title, subtitle="", parent=None, close_callback=None):
        super().__init__(parent)
        self.setObjectName("CardPage")
        
        # 1. Added QScrollArea and ScrollContent transparency to your existing stylesheet
        self.setStyleSheet("""
            QWidget#CardPage {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0.0 #ffffff,
                    stop:0.7 #f3f7fd,
                    stop:1.0 #edf3ff
                );
                border-radius: 14px; /* Slightly tighter curves */
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#ScrollContent {
                background: transparent;
            }
        """)
        
        # 2. Setup a base layout for the card itself
        self.base_layout = QVBoxLayout(self)
        self.base_layout.setContentsMargins(0, 0, 0, 0)
        
        # 3. Create the Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        
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
                }}
            """)
            self.main_layout.addWidget(subtitle_label)
 
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)


class SettingsPage(CardPage):

    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Settings",
            "Customize your assistant and preferences.",
            parent,
            close_callback,
        )
        self.profile = db.get_profile()

        # Define configurations with explicit 'type' and type-specific parameters
        self.settings_config = {
            "name": {
                "type": "text",
                "label": "Full Name",
                "placeholder": "Enter your entire name...",
            },
            "nickname": {
                "type": "text",
                "label": "Nickname",
                "placeholder": "Enter what you would like to be called...",
            },
            "age": {
                "type": "number",
                "label": "Age",
                "min": 0,
                "max": 120,
            },  # Handled by QSpinBox
            "email": {
                "type": "text",
                "label": "Email Address",
                "placeholder": "Enter your personal email...",
            },
            "theme": {
                "type": "dropdown",
                "label": "App Theme",
                "options": ["Light", "Dark", "System"],
            },
            "theme_color": {
                "type": "color_palette",
                "label": "Theme Accent Color",
                "colors": ["#FFB6C1", "#98FB98", "#87CEFA", "#E6E6FA", "#F5F5DC"] # Soft pink, green, blue, purple, beige
            },
            "compact_mode": {
                "type": "circle_toggle",
                "label": "Compact Interface",
            },  # Handled by QComboBox
            "notifications": {
                "type": "toggle",
                "label": "Enable Desktop Notifications",
            },  # Handled by Checkable QPushButton
            "instruction": {
                "type": "text",
                "label": "Instructions for Buddy",
                "placeholder": "Enter a few lines to customize speech...",
            },
            "bio": {
                "type": "text",
                "label": "About You",
                "placeholder": "Enter a few sentences about yourself...",
            },
            "byo_api_key": {
                "type": "password",
                "label": "API Key",
                "placeholder": "Enter API token...",
            },
        }

        self.inputs = {}

        profile_label = QLabel("User Profile")
        profile_label.setStyleSheet(
            f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold;"
            " background: transparent; margin-top: 8px;"
        )
        self.main_layout.addWidget(profile_label)

        # Reusable styles
        self.widget_style = """
            QWidget {
                background-color: #ffffff;
                border: 1.2px solid #d2d9e0;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                color: #24292f;
            }
            QWidget:enabled:focus {
                border: 1.2px solid #0969da;
                background-color: #f6f8fa;
            }
        """

        self.toggle_style = """
            QPushButton {
                background-color: #f6f8fa;
                border: 1.2px solid #d2d9e0;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: bold;
                color: #24292f;
            }
            QPushButton:checked {
                background-color: #2da44e;
                color: white;
                border-color: #2da44e;
            }
        """

        self.circle_toggle_style = """
            QPushButton {
                background-color: #E0E0E0;
                border: none;
                border-radius: 12px;
            }
            QPushButton:checked {
                background-color: #A8E6CF; /* Soft pastel green when ON */
            }
        """

        # Generate fields dynamically based on config type
        for key, config in self.settings_config.items():
            input_label = QLabel(config["label"])
            input_label.setStyleSheet(
                f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; font-weight:"
                " bold; background: transparent;"
            )
            self.main_layout.addWidget(input_label)

            widget_type = config.get("type", "text")
            current_value = self.profile.get(key)

            if widget_type in ["text", "password"]:
                widget = QLineEdit()
                widget.setText(current_value or "")
                widget.setPlaceholderText(config.get("placeholder", ""))
                widget.setStyleSheet(self.widget_style)

                if widget_type == "password":
                    widget.setEchoMode(QLineEdit.Password)
                    widget.setReadOnly(True)
                    widget.setCursor(Qt.CursorShape.PointingHandCursor)
                    widget.mousePressEvent = lambda event, w=widget: (
                        self.on_password_clicked(event, w)
                    )

                # Connect text change events
                widget.returnPressed.connect(
                    lambda w=widget, k=key: self.save_text_input(w, k)
                )
                widget.editingFinished.connect(
                    lambda w=widget, k=key: self.save_text_input(w, k)
                )

            elif widget_type == "number":
                widget = QSpinBox()
                widget.setRange(config.get("min", 0), config.get("max", 100))
                widget.setValue(int(current_value or 0))
                widget.setStyleSheet(self.widget_style)
                # Save immediately when the number changes
                widget.valueChanged.connect(
                    lambda val, k=key: self.update_db(k, val)
                )

            elif widget_type == "dropdown":
                widget = QComboBox()
                widget.addItems(config.get("options", []))
                widget.setCurrentText(current_value or "")
                widget.setStyleSheet(self.widget_style)
                # Save immediately when option changes
                widget.currentTextChanged.connect(
                    lambda text, k=key: self.update_db(k, text)
                )

            elif widget_type == "toggle":
                widget = QPushButton("Off")
                widget.setCheckable(True)
                widget.setStyleSheet(self.toggle_style)

                # Set initial state
                is_checked = str(current_value).lower() in ["true", "1", "yes"]
                widget.setChecked(is_checked)
                widget.setText("On" if is_checked else "Off")

                # Handle dynamic text updates and DB saves
                widget.toggled.connect(
                    lambda checked, w=widget, k=key: self.handle_toggle(
                        w, k, checked
                    )
                )
                # --- ADD THIS FOR THE SOFT COLOR PALETTE ---
            elif config.get("type") == "color_palette":
                palette_widget = QWidget()
                palette_layout = QHBoxLayout(palette_widget)
                palette_layout.setContentsMargins(0, 4, 0, 4)
                palette_layout.setSpacing(10)
                palette_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                
                color_group = QButtonGroup(palette_widget)
                color_group.setExclusive(True)
                
                for color_hex in config.get("colors", []):
                    btn = QPushButton()
                    btn.setFixedSize(28, 28)
                    btn.setCheckable(True)
                    btn.setStyleSheet(f"""
                        QPushButton {{ background-color: {color_hex}; border: 2px solid transparent; border-radius: 14px; }}
                        QPushButton:checked {{ border: 2px solid #1A73E8; }}
                        QPushButton:hover {{ border: 2px solid #121212; }}
                    """)
                    
                    if (self.profile.get(key) or "") == color_hex:
                        btn.setChecked(True)
                        
                    btn.clicked.connect(lambda checked, ch=color_hex, k=key: self.update_db(k, ch))
                    color_group.addButton(btn)
                    palette_layout.addWidget(btn)
                    
                self.main_layout.addWidget(palette_widget)
                self.inputs[key] = palette_widget

            # --- ADD THIS FOR THE SOFT CIRCLE TOGGLES ---
            elif config.get("type") == "circle_toggle":
                switch_container = QWidget()
                switch_layout = QHBoxLayout(switch_container)
                switch_layout.setContentsMargins(0, 4, 0, 4)
                
                track_button = QPushButton()
                track_button.setFixedSize(44, 24)
                track_button.setCheckable(True)
                track_button.setStyleSheet(self.circle_toggle_style)
                
                knob_layout = QHBoxLayout(track_button)
                knob_layout.setContentsMargins(2, 2, 2, 2)
                
                knob = QWidget()
                knob.setFixedSize(20, 20)
                knob.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                knob.setStyleSheet("background-color: white; border-radius: 10px;")
                
                is_active = str(self.profile.get(key)).lower() in ["true", "1", "yes"]
                track_button.setChecked(is_active)
                knob_layout.addWidget(knob, alignment=Qt.AlignmentFlag.AlignRight if is_active else Qt.AlignmentFlag.AlignLeft)
                
                track_button.toggled.connect(lambda checked, kl=knob_layout, kn=knob, k=key: self.handle_circle_toggle(checked, kl, kn, k))
                
                switch_layout.addWidget(track_button)
                switch_layout.addStretch()
                self.main_layout.addWidget(switch_container)
                self.inputs[key] = track_button


            self.main_layout.addWidget(widget)
            self.inputs[key] = widget

        self.main_layout.addStretch()

    # Specialized helper for password field interactions
    def on_password_clicked(self, event, line_edit):
        if line_edit.isReadOnly():
            line_edit.setReadOnly(False)
            line_edit.setCursor(Qt.CursorShape.IBeamCursor)
            line_edit.selectAll()
            line_edit.setFocus()

    # Handles finalizing text input edits
    def save_text_input(self, line_edit, settings_key):
        # Reset password box UI state if it happens to be the password widget
        if self.settings_config[settings_key]["type"] == "password":
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.clearFocus()

        updated_value = line_edit.text().strip()
        self.update_db(settings_key, updated_value)

    # Handles the custom push button toggle updates
    def handle_toggle(self, button, settings_key, is_checked):
        button.setText("On" if is_checked else "Off")
        self.update_db(settings_key, is_checked)

    # Global, type-agnostic database saving mechanism
    def update_db(self, settings_key, current_value):
        old_value = self.profile.get(settings_key)

        # Convert types to strings cleanly if your DB framework prefers string consistency
        if str(current_value) != str(old_value or ""):
            db.update_profile(**{settings_key: current_value})
            self.profile[settings_key] = current_value

    def handle_circle_toggle(self, is_checked, knob_layout, knob, settings_key):
        """Repositions the white visual slider knob and commits state to database."""
        knob_layout.removeWidget(knob)
        if is_checked:
            knob_layout.addWidget(knob, alignment=Qt.AlignmentFlag.AlignRight)
        else:
            knob_layout.addWidget(knob, alignment=Qt.AlignmentFlag.AlignLeft)
            
        self.update_db(settings_key, is_checked)

    def update_db(self, settings_key, current_value):
        """Centralized save handler to verify data mutations cleanly."""
        old_value = self.profile.get(settings_key)
        if str(current_value) != str(old_value or ""):
            db.update_profile(**{settings_key: current_value})
            self.profile[settings_key] = current_value


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
class BuddyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Buddy v1.0.0")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._drag_pos = QPoint()
 
        self.app_icon = create_buddy_icon("GUI/assets/Buddy_menubar.png")
        self.setWindowIcon(self.app_icon)
        self.current_conversation_id = None
        self.current_chat_title = None
        self.message_history = new_message_history()
        self._thinking_bubble = None
        self._last_assistant_bubble = None
        self._is_sending = False
        self._send_worker = None
        self.incognito_mode = False

        self._build_ui()
        self._setup_tray_icon()
 
    def resizeEvent(self, event):
        super().resizeEvent(event)
 
        base_width = 500.0
        scale = max(0.85, min(self.width() / base_width, 1.2))
 
        title_size = max(14, int(WINDOW_TITLE_SIZE * scale))
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {WINDOW_TITLE_COLOR};
                font-size: {title_size}px;
                font-weight: {WINDOW_TITLE_WEIGHT};
                background: transparent;
            }}
        """)
 
        greeting_size = max(18, int(GREETING_FONT_SIZE * scale))
        system_font = QFont(".AppleSystemUIFont", greeting_size, QFont.Medium)
        if not system_font.exactMatch():
            print("Backup font used")
            system_font = QFont("Helvetica Neue", greeting_size, QFont.Medium)
        self.greeting.setFont(system_font)
        self.greeting.setAlignment(Qt.AlignCenter)
        self.main_layout.setAlignment(self.greeting, Qt.AlignCenter)
 
        self._position_preview_overlay()
 
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
 
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
 
    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
 
    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_menu = QMenu()
        show_action = QAction("Initiate Buddy", self)
        show_action.triggered.connect(self.toggle_window)
        self.tray_menu.addAction(show_action)
        self.tray_menu.addSeparator()
        quit_action = QAction("Quit Buddy", self)
        quit_action.triggered.connect(QApplication.quit)
        self.tray_menu.addAction(quit_action)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
 
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window()
        elif reason == QSystemTrayIcon.Context:
            self.tray_menu.popup(QCursor.pos())
 
    def toggle_window(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.position_tray_popover()
            self.show()
            self.raise_()
            self.activateWindow()
 
    def show_window(self):
        self.position_tray_popover()
        self.show()
        self.raise_()
        self.activateWindow()
 
    def position_tray_popover(self):
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geo = self.tray_icon.geometry()
 
        if tray_geo.isValid() and tray_geo.x() > 0:
            x = tray_geo.x() + (tray_geo.width() // 2) - (self.width() // 2)
            y = tray_geo.bottom() + 6
            if x + self.width() > screen.right():
                x = screen.right() - self.width() - 12
            if x < screen.left():
                x = screen.left() + 12
        else:
            x = screen.right() - self.width() - 16
            y = screen.top() + 8
        self.move(x, y)
 
    def _build_ui(self):
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(10, 10, 10, 10)
 
        self.container = QFrame()
        self.container.setObjectName("MainContainer")
        self.container.setStyleSheet(f"""
            QFrame#MainContainer {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0.0 {WINDOW_BG_TOP}, stop:0.6 {WINDOW_BG_MID}, stop:1.0 {WINDOW_BG_BOTTOM}
                );
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.7);
            }}
        """)
 
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 45))
        shadow.setOffset(0, 6)
        self.container.setGraphicsEffect(shadow)
        self.h_wrapper = QHBoxLayout(self.container)
        self.h_wrapper.setContentsMargins(0, 0, 0, 0)
        self.h_wrapper.setSpacing(0)
 
        self.sidebar = Sidebar(
            on_chat_click_callback=self.load_chat,
            on_new_chat_callback=self._new_chat,
            on_delete_chat_callback=self.delete_chat
        )
        self.h_wrapper.addWidget(self.sidebar)
 
        self.sidebar.refresh_recents(on_chat_click=self.load_chat, on_delete_chat=self.delete_chat)
 
        self.content_area = QWidget()
        self.content_area_layout = QVBoxLayout(self.content_area)
        self.content_area_layout.setContentsMargins(0, 0, 0, 0)
        self.content_area_layout.setSpacing(0)
 
        self.header_bar = QWidget()
        self.header_bar.setFixedHeight(WINDOW_HEADER_HEIGHT)
        self.header_bar.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)
        self.header_layout = QHBoxLayout(self.header_bar)
        self.header_layout.setContentsMargins(
            WINDOW_HEADER_PADDING_LEFT,
            WINDOW_HEADER_PADDING_TOP,
            WINDOW_HEADER_PADDING_RIGHT,
            WINDOW_HEADER_PADDING_BOTTOM,
        )
        self.header_layout.setSpacing(0)
 
        self.title_label = QLabel(WINDOW_TITLE_TEXT)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {WINDOW_TITLE_COLOR};
                font-size: {WINDOW_TITLE_SIZE}px;
                font-weight: {WINDOW_TITLE_WEIGHT};
                background: transparent;
            }}
        """)
 
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(WINDOW_CLOSE_BUTTON_SIZE, WINDOW_CLOSE_BUTTON_SIZE)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {WINDOW_CLOSE_BUTTON_COLOR};
                border: none;
                font-size: {WINDOW_CLOSE_BUTTON_FONT_SIZE}px;
                font-weight: bold;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background: {WINDOW_CLOSE_BUTTON_HOVER_BG};
                color: {WINDOW_CLOSE_BUTTON_HOVER_COLOR};
            }}
        """)
        self.close_btn.clicked.connect(self.hide)

        self.privacy_btn = QPushButton("🔓")
        self.privacy_btn.setFlat(True)
        self.privacy_btn.setCursor(Qt.PointingHandCursor)
        self.privacy_btn.setToolTip("Mark this chat as private")
        self.privacy_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; }")
        self.privacy_btn.clicked.connect(self._toggle_current_chat_private)
        self.privacy_btn.setVisible(False)

        self.incognito_btn = QPushButton("🕶️")
        self.incognito_btn.setFlat(True)
        self.incognito_btn.setCursor(Qt.PointingHandCursor)
        self.incognito_btn.setToolTip("Start an incognito chat (nothing is saved)")
        self.incognito_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; }")
        self.incognito_btn.clicked.connect(self._toggle_incognito_mode)

        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.incognito_btn)
        self.header_layout.addWidget(self.privacy_btn)
        self.header_layout.addWidget(self.close_btn)
 
        self.content_area_layout.addWidget(self.header_bar)
 
        self.content_stack = QStackedWidget()
        self.content_stack.setContentsMargins(0, 0, 0, 0)
        self.content_area_layout.addWidget(self.content_stack)
        self.h_wrapper.addWidget(self.content_area, stretch=1)
 
        self.chat_page = QWidget()
        self.chat_page.setObjectName("ChatPage")
        self.chat_page.setStyleSheet(f"""
            QWidget#ChatPage {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0.0 {PAGE_BG_TOP}, stop:0.7 {PAGE_BG_MID}, stop:1.0 {PAGE_BG_BOTTOM}
                );
                border-radius: 18px;
            }}
        """)
        self.main_layout = QVBoxLayout(self.chat_page)
        self.main_layout.setContentsMargins(16, 8, 16, 0)
        self.main_layout.setSpacing(0)
 
        self.content_stack.addWidget(self.chat_page)
 
        greetings = [
            "Hi Shrey, what's on your mind?",
            "Hi, how can I help you Shrey?",
            "Let's dive in, Shrey",
            "Welcome back, Shrey!",
            "Ready when you are"
        ]
        self.greeting = QLabel(random.choice(greetings))
        self.greeting.setAlignment(Qt.AlignCenter)
        self.greeting.setWordWrap(True)
        self.greeting.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.greeting.setMinimumHeight(60)
        self.greeting.setStyleSheet(f"color: {GREETING_COLOR}; background: transparent;")
        self.greeting.setFont(QFont(".AppleSystemUIFont", GREETING_FONT_SIZE, QFont.Medium))
 
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 9px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(95, 107, 122, 0.52);
                border-radius: 4px;
                min-height: 48px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(70, 90, 108, 0.75);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical {
                background: none;
                border: none;
                height: 0px;
            }
        """)
        self.scroll_area.setVisible(False)
 
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 12)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)
 
        # --- Unified composer box: white rounded frame holding tray + input row ---
        self.input_container = QFrame()
        self.input_container.setObjectName("InputContainer")
        self.input_container.setStyleSheet("""
            QFrame#InputContainer {
                background: white;
                border: 1px solid rgba(0,0,0,0.06);
                border-radius: 20px;
            }
        """)
        input_outer = QVBoxLayout(self.input_container)
        input_outer.setContentsMargins(0, 6, 0, 6)
        input_outer.setSpacing(0)

        # Tray lives inside the frame, shown only when files attached
        self.attachment_tray = AttachmentTray()
        self.attachment_tray.setContentsMargins(10, 4, 10, 0)
        input_outer.addWidget(self.attachment_tray)

        # Row: attach btn | text field | send btn
        input_row = QHBoxLayout()
        input_row.setContentsMargins(8, 0, 8, 0)
        input_row.setSpacing(4)

        self.attach_button = QPushButton()
        self.attach_button.setFixedSize(28, 28)
        self.attach_button.setCursor(Qt.PointingHandCursor)
        self.attach_button.setToolTip("Attach files")
        self.attach_button.setIcon(get_svg_icon(ICONS["plus"], "#6B7280", 16))
        self.attach_button.setIconSize(QSize(16, 16))
        self.attach_button.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 14px; }
            QPushButton:hover { background: rgba(0,0,0,0.06); }
        """)
        self.attach_button.clicked.connect(lambda: self.input_box.open_file_picker())

        self.input_box = ChatInput(self.handle_send, tray_ref=self.attachment_tray)
        self.input_box.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                padding: 4px 4px;
                font-size: 14px;
                color: #333;
            }
        """)

        self.send_button = QPushButton("➤")
        self.send_button.setFixedSize(SEND_BUTTON_SIZE, SEND_BUTTON_SIZE)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {CHAT_BUBBLE_USER_TEXT}; border: none; border-radius: {SEND_BUTTON_SIZE // 2}px; font-size: 15px; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
        """)
        self.send_button.clicked.connect(self.handle_send)

        input_row.addWidget(self.attach_button, 0, Qt.AlignBottom)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_button, 0, Qt.AlignBottom)
        input_outer.addLayout(input_row)

        self.attachment_tray.file_removed.connect(self.input_box.remove_attachment)
        self.attachment_tray.preview_requested.connect(self._show_attachment_preview)
        self.input_box.attachment_changed.connect(self._update_attachment_controls)
 
        self.preview_overlay = QFrame(self.chat_page)
        self.preview_overlay.setObjectName("PreviewOverlay")
        self.preview_overlay.setVisible(False)
        self.preview_overlay.setStyleSheet("""
            QFrame#PreviewOverlay {
                background: rgba(18, 24, 38, 0.44);
                border: none;
            }
        """)
 
        self.preview_panel = QFrame(self.preview_overlay)
        self.preview_panel.setObjectName("PreviewPanel")
        self.preview_panel.setStyleSheet("""
            QFrame#PreviewPanel {
                background: rgba(255,255,255,0.96);
                border-radius: 18px;
                border: 1px solid rgba(0,0,0,0.08);
            }
        """)
        self.preview_layout = QVBoxLayout(self.preview_panel)
        self.preview_layout.setContentsMargins(14, 12, 14, 14)
        self.preview_layout.setSpacing(10)
 
        self.preview_header = QHBoxLayout()
        self.preview_title = QLabel("Preview")
        self.preview_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #2d2d2d;")
        self.preview_header.addWidget(self.preview_title)
        self.preview_header.addStretch()
        self.preview_close_btn = QPushButton("✕")
        self.preview_close_btn.setFixedSize(28, 28)
        self.preview_close_btn.setCursor(Qt.PointingHandCursor)
        self.preview_close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                border-radius: 14px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(0,0,0,0.06);
            }
        """)
        self.preview_close_btn.clicked.connect(self._hide_attachment_preview)
        self.preview_header.addWidget(self.preview_close_btn)
        self.preview_layout.addLayout(self.preview_header)
 
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background: rgba(245,247,250,0.95);
                border: 1px solid rgba(0,0,0,0.06);
                border-radius: 12px;
                color: #333;
                font-size: 12px;
                padding: 10px;
            }
        """)
        self.preview_layout.addWidget(self.preview_text)
    
        self._update_attachment_controls()
        self._position_preview_overlay()
 
        self.greeting_spacer = QWidget()
        self.greeting_spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.main_layout.addWidget(self.greeting_spacer, stretch=1)
        self.main_layout.addWidget(self.greeting, stretch=0)
        self.main_layout.setAlignment(self.greeting, Qt.AlignCenter)
        self.greeting_spacer_bottom = QWidget()
        self.greeting_spacer_bottom.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.main_layout.addWidget(self.greeting_spacer_bottom, stretch=1)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet(f"color: {TEXT_COLOR_SUBTITLE}; font-size: {SUBTITLE_FONT_SIZE}px; background: transparent;")
        self.subtitle_label.setVisible(False)
        self.main_layout.addWidget(self.subtitle_label)
        self.main_layout.addWidget(self.scroll_area, stretch=1)

        self.composer = QWidget()
        self.composer.setStyleSheet("background: transparent;")
        composer_layout = QVBoxLayout(self.composer)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        composer_layout.setSpacing(0)
        composer_layout.addWidget(self.input_container)
        self.main_layout.addWidget(self.composer)
 
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 5, 2)
        footer_layout.addStretch()
        size_grip = QSizeGrip(self.container)
        size_grip.setFixedSize(SIZE_GRIP_SIZE, SIZE_GRIP_SIZE)
        size_grip.setCursor(Qt.SizeFDiagCursor)
        size_grip.setStyleSheet("QSizeGrip { background: transparent; }")
        footer_layout.addWidget(size_grip, alignment=Qt.AlignBottom | Qt.AlignRight)
 
        self.main_layout.addLayout(footer_layout)
 
        self.settings_page = SettingsPage(close_callback=self.hide)
        self.library_page = LibraryPage(close_callback=self.hide, on_chat_selected=self.load_chat, on_delete_chat=self._delete_chat_from_library)
        self.content_stack.addWidget(self.settings_page)
        self.content_stack.addWidget(self.library_page)
 
        self.sidebar.btn_new.clicked.connect(self.show_chat_view)
        self.sidebar.btn_lib.clicked.connect(self.show_library_view)
        self.sidebar.btn_settings.clicked.connect(self.show_settings_view)
 
        self.show_chat_view()
        window_layout.addWidget(self.container)
 
    def _update_attachment_controls(self):
        files = getattr(self.input_box, "attached_files", [])
        self.attachment_tray.set_files(files)
 
    def _show_attachment_preview(self, file_packet=None):
        files = getattr(self.input_box, 'attached_files', [])
        if file_packet is None:
            if not files:
                return
            file_packet = files[-1]
 
        content = file_packet.get('contents', '')
        self.preview_title.setText(f"Preview: {file_packet.get('name', 'Attachment')}")
        self.preview_text.setPlainText(content)
        self._position_preview_overlay()
        self.preview_overlay.show()
        self.preview_overlay.raise_()
 
    def _hide_attachment_preview(self):
        self.preview_overlay.hide()
 
    def _position_preview_overlay(self):
        if not self.preview_overlay.isVisible():
            self.preview_overlay.resize(self.chat_page.size())
            self.preview_overlay.move(0, 0)
            self.preview_panel.resize(int(self.chat_page.width() * 0.7), int(self.chat_page.height() * 0.7))
            self.preview_panel.move(
                (self.chat_page.width() - self.preview_panel.width()) // 2,
                (self.chat_page.height() - self.preview_panel.height()) // 2,
            )
        else:
            self.preview_overlay.resize(self.chat_page.size())
            self.preview_overlay.move(0, 0)
            self.preview_panel.resize(int(self.chat_page.width() * 0.7), int(self.chat_page.height() * 0.7))
            self.preview_panel.move(
                (self.chat_page.width() - self.preview_panel.width()) // 2,
                (self.chat_page.height() - self.preview_panel.height()) // 2,
            )
 
    def _set_conversation_title(self, title):
        self.current_chat_title = title
        if title:
            self.subtitle_label.setText(f"Conversation: {title}")
            self.subtitle_label.setVisible(True)
        else:
            self.subtitle_label.setText("")
            self.subtitle_label.setVisible(False)
 
    def _clear_chat_history(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.chat_layout.addStretch()
 
    def _render_chat_history(self, history):
        self._clear_chat_history()
        for msg in history:
            role = msg.get("role")
            content = msg.get("content") or ""
            if role == "user":
                bubble = ChatBubble(text=content, is_user=True)
                self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
            elif role == "assistant":
                metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
                msg_id = msg.get("id")
                bubble = ChatBubble(
                    text=content,
                    is_user=False,
                    plan_text=metadata.get("plan_text"),
                    tools_used=metadata.get("tools_used"),
                    stats=metadata.get("stats"),
                    message_id=msg_id,
                    initial_feedback=msg.get("feedback"),
                    callbacks={
                        'copy': lambda text=content: QApplication.clipboard().setText(text),
                        'like': lambda active, mid=msg_id: self._set_feedback(mid, 'like', active),
                        'dislike': lambda active, mid=msg_id: self._set_feedback(mid, 'dislike', active),
                        'redo': lambda: None
                    }
                )
                self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def _set_feedback(self, message_id, kind, active):
        if message_id is None:
            return
        core.set_message_feedback(message_id, kind if active else None)
 
    def _redo_assistant_response(self, user_text):
        if self.current_conversation_id is None:
            return {"reply": "", "plan_text": None, "tools_used": None, "stats": None}
 
        result = core.redo_assistant_response(self.current_conversation_id, user_text)
        self.message_history.append({"role": "assistant", "content": result["reply"]})
        return result
 
    def show_chat_view(self):
        self.content_stack.setCurrentWidget(self.chat_page)
 
    def show_settings_view(self):
        self.content_stack.setCurrentWidget(self.settings_page)
 
    def show_library_view(self):
        self.library_page.refresh_chats()
        self.content_stack.setCurrentWidget(self.library_page)
 
    def load_chat(self, conversation_id):
        self.show_chat_view()
        self.current_conversation_id = conversation_id
        title = core.get_conversation_title(conversation_id)
        self._set_conversation_title(title)
        self._refresh_privacy_button()
 
        history = core.get_conversation_history(conversation_id)
        self.message_history = list(history)
        self._render_chat_history(history)
        self.scroll_area.setVisible(True)
        self.greeting.setVisible(False)
        self.greeting_spacer.setVisible(False)
        self.greeting_spacer_bottom.setVisible(False)

    def _toggle_incognito_mode(self):
        if self.current_conversation_id is not None:
            # Already a real, saved chat — incognito can only start fresh.
            return
        self.incognito_mode = not self.incognito_mode
        if self.incognito_mode:
            self.incognito_btn.setStyleSheet("QPushButton { border: none; background: rgba(43,127,240,0.15); border-radius: 6px; font-size: 14px; }")
            self.incognito_btn.setToolTip("Incognito ON — nothing in this chat will be saved")
            self.subtitle_label.setText("🕶️ Incognito — nothing here is saved")
            self.subtitle_label.setVisible(True)
        else:
            self.incognito_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; }")
            self.incognito_btn.setToolTip("Start an incognito chat (nothing is saved)")
            self.subtitle_label.setVisible(False)

    def _refresh_privacy_button(self):
        if self.current_conversation_id is None:
            self.privacy_btn.setVisible(False)
            return
        is_private = core.get_conversation_is_private(self.current_conversation_id)
        self.privacy_btn.setText("🔒" if is_private else "🔓")
        self.privacy_btn.setToolTip("Private chat — click to unmark" if is_private else "Mark this chat as private")
        self.privacy_btn.setVisible(True)

    def _toggle_current_chat_private(self):
        if self.current_conversation_id is None:
            return
        is_private = core.get_conversation_is_private(self.current_conversation_id)
        core.set_conversation_private(self.current_conversation_id, not is_private)
        self._refresh_privacy_button()
 
    def delete_chat(self, conversation_id):
        core.delete_conversation(conversation_id)
        if self.current_conversation_id == conversation_id:
            self.current_conversation_id = None
            self.current_chat_title = None
            self._set_conversation_title(None)
            self._clear_chat_history()
            self.scroll_area.setVisible(False)
            self.greeting.setVisible(True)
            self.greeting_spacer.setVisible(True)
            self.greeting_spacer_bottom.setVisible(True)
        self.sidebar.refresh_recents(on_chat_click=self.load_chat, on_delete_chat=self.delete_chat)

    def _delete_chat_from_library(self, conversation_id):
        self.delete_chat(conversation_id)
        self.library_page.refresh_chats()
 
    def _new_chat(self):
        self.current_conversation_id = None
        self.current_chat_title = None
        self.message_history = new_message_history()
        self._set_conversation_title(None)
        self.privacy_btn.setVisible(False)
        if self.incognito_mode:
            self._toggle_incognito_mode()
        self._clear_chat_history()
        self.scroll_area.setVisible(False)
        self.greeting.setVisible(True)
        self.greeting_spacer.setVisible(True)
        self.greeting_spacer_bottom.setVisible(True)
 
    def _set_input_enabled(self, enabled):
        self.input_box.setReadOnly(not enabled)
        self.send_button.setEnabled(enabled)
        self.attach_button.setEnabled(enabled)

    def handle_send(self, forced_text=None):
        if self._is_sending:
            return
        attached_files = list(getattr(self.input_box, 'attached_files', []))
        user_text = forced_text if forced_text else self.input_box.toPlainText().strip()

        if attached_files:
            markers = {f"📎 {item['name']}" for item in attached_files}
            user_text = "\n".join(
                line for line in user_text.splitlines() if line.strip() not in markers
            ).strip()

        display_text = user_text
        if attached_files:
            chip = "📎 " + ", ".join(item["name"] for item in attached_files)
            display_text = f"{user_text}\n\n{chip}".strip() if user_text else chip

        if not user_text and not attached_files:
            return
        if not user_text and attached_files:
            names = ", ".join(item["name"] for item in attached_files)
            user_text = f"Please use the attached file(s): {names}"

        if not self.incognito_mode and self.current_conversation_id is None:
            self.current_conversation_id = core.create_conversation()
            self._set_conversation_title(None)
            self._refresh_privacy_button()
            self.sidebar.refresh_recents()

        self.scroll_area.setVisible(True)
        self.greeting.setVisible(False)
        self.greeting_spacer.setVisible(False)
        self.greeting_spacer_bottom.setVisible(False)

        # process_message_incognito appends the user turn itself; only track
        # it here for non-incognito bookkeeping to avoid a duplicate entry.
        if not self.incognito_mode:
            self.message_history.append({"role": "user", "content": display_text})
        user_bubble = ChatBubble(text=display_text, is_user=True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, user_bubble)
        self._scroll_to_bottom()

        self._last_send_text = user_text
        self._last_send_attachments = attached_files

        # Show a "thinking" placeholder bubble (animated paw loader)
        self._thinking_bubble = ChatBubble(is_user=False, is_thinking=True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, self._thinking_bubble)
        self._scroll_to_bottom()

        self.input_box.clear()
        self._set_input_enabled(False)
        self._set_send_button_stop_mode(True)

        self._is_sending = True
        if self.incognito_mode:
            # Incognito: no conversation_id, no db writes — the pipeline works
            # purely off the in-memory message_history this window owns.
            self._send_worker = SendWorker(
                None, user_text, attached_files,
                incognito=True, history=self.message_history
            )
        else:
            self._send_worker = SendWorker(self.current_conversation_id, user_text, attached_files)
        self._send_worker.finished.connect(lambda result: self._on_send_result(result))
        self._send_worker.error.connect(lambda err: self._on_send_error(err))
        self._send_worker.progress.connect(self._on_send_progress)
        self._send_worker.start()

    def _set_send_button_stop_mode(self, is_stopping):
        """Swaps the send button into a Stop button while a request is in flight."""
        if is_stopping:
            self.send_button.setText("■")
            self.send_button.setEnabled(True)
            self.send_button.setToolTip("Stop")
            try:
                self.send_button.clicked.disconnect()
            except TypeError:
                pass
            self.send_button.clicked.connect(self._cancel_current_send)
        else:
            self.send_button.setText("➤")
            self.send_button.setToolTip("")
            try:
                self.send_button.clicked.disconnect()
            except TypeError:
                pass
            self.send_button.clicked.connect(self.handle_send)

    def _cancel_current_send(self):
        if self._send_worker is not None:
            self._send_worker.cancel_event.set()
            self.send_button.setEnabled(False)
            self.send_button.setToolTip("Stopping…")
            if self._thinking_bubble and hasattr(self._thinking_bubble, 'paw_loader'):
                pass  # loader keeps animating until the worker actually returns

    def _on_send_progress(self, event):
        if not self._thinking_bubble:
            return
        etype = event.get("type")
        label = None
        if etype == "thinking":
            label = "Buddy is thinking…"
        elif etype == "plan":
            label = "Working on it…"
        elif etype == "tool_call":
            label = f"Using {event.get('name', 'a tool')}…"
        elif etype == "refining":
            label = "Refining the plan…"
        elif etype == "malformed_retry":
            label = "Retrying…"
        if label and hasattr(self._thinking_bubble, 'layout'):
            # Find the thinking label inside the bubble and update it
            for child in self._thinking_bubble.findChildren(QLabel):
                if child.text().startswith("Buddy is thinking") or child.text() in (
                    "Working on it…", "Refining the plan…", "Retrying…"
                ) or child.text().startswith("Using "):
                    child.setText(label)
                    break

    def _remove_thinking_bubble(self):
        if self._thinking_bubble:
            self.chat_layout.removeWidget(self._thinking_bubble)
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None

    def _on_send_result(self, result):
        self._is_sending = False
        self._send_worker = None
        self._set_send_button_stop_mode(False)
        self._remove_thinking_bubble()
        self._set_input_enabled(True)
        self.input_box.setFocus()

        reply = result.get("reply", "")
        if reply:
            if not self.incognito_mode:
                self.message_history.append({"role": "assistant", "content": reply})
            conv_id = self.current_conversation_id

            def make_redo(captured_reply=reply, captured_conv=conv_id):
                def do_redo():
                    self._trigger_redo_for_bubble(captured_conv, captured_reply, self._last_assistant_bubble)
                return do_redo

            msg_id = result.get("message_id")
            assistant_bubble = ChatBubble(
                text=reply,
                is_user=False,
                plan_text=result.get("plan_text"),
                tools_used=result.get("tools_used"),
                stats=result.get("stats"),
                message_id=msg_id,
                callbacks={
                    'copy': lambda text=reply: QApplication.clipboard().setText(text),
                    'like': lambda active, mid=msg_id: self._set_feedback(mid, 'like', active),
                    'dislike': lambda active, mid=msg_id: self._set_feedback(mid, 'dislike', active),
                    'redo': make_redo(),
                }
            )
            self._last_assistant_bubble = assistant_bubble
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, assistant_bubble)
            self._scroll_to_bottom()

        if result.get("chat_title"):
            self._set_conversation_title(result["chat_title"])
            self.sidebar.refresh_recents(on_chat_click=self.load_chat, on_delete_chat=self.delete_chat)

    def _on_send_error(self, error_msg):
        self._is_sending = False
        self._send_worker = None
        self._set_send_button_stop_mode(False)
        self._remove_thinking_bubble()
        self._set_input_enabled(True)
        self.input_box.setFocus()
        self._insert_error_bubble(error_msg)
        self._scroll_to_bottom()

    def _classify_error(self, error_msg):
        msg = (error_msg or "").lower()
        if "429" in msg or "rate limit" in msg or "too many" in msg:
            return "Rate limited", "Buddy's model provider is being hit too fast. This is usually retryable."
        if "permission" in msg or "unauthorized" in msg or "403" in msg:
            return "Permission issue", "Buddy doesn't have permission to do that. Check API key / access."
        if "500" in msg or "502" in msg or "503" in msg or "timeout" in msg:
            return "Server error", "The model provider had a hiccup. Usually fine on retry."
        if "error executing" in msg or "tool" in msg:
            return "Tool error", "A tool call failed while running the task."
        return "Something went wrong", error_msg

    def _insert_error_bubble(self, error_msg):
        title, detail = self._classify_error(error_msg)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #fff2f0;
                border: 1px solid #f3b8b0;
                border-radius: 14px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(4)

        title_label = QLabel(f"⚠ {title}")
        title_label.setStyleSheet("color: #b3261e; font-size: 12.5px; font-weight: 700; background: transparent;")
        card_layout.addWidget(title_label)

        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #7a2c26; font-size: 12px; background: transparent;")
        card_layout.addWidget(detail_label)

        retry_btn = QPushButton("Retry")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton {
                background: #b3261e; color: white; border: none;
                border-radius: 8px; padding: 4px 12px; font-size: 12px; font-weight: 600;
                max-width: 70px;
            }
            QPushButton:hover { background: #931f19; }
        """)
        retry_btn.clicked.connect(self._retry_last_send)
        card_layout.addWidget(retry_btn, alignment=Qt.AlignLeft)

        card.setMaximumWidth(320)
        row_layout.addWidget(card)
        row_layout.addStretch()

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)

    def _retry_last_send(self):
        if getattr(self, '_last_send_text', None) is None or self._is_sending:
            return
        if getattr(self, '_last_send_attachments', None):
            self.input_box.attached_files = list(self._last_send_attachments)
        self.handle_send(forced_text=self._last_send_text)

    def _trigger_redo_for_bubble(self, conversation_id, user_text, bubble):
        """Kick off a redo in a background thread and push the new version into bubble."""
        if not bubble or len(bubble.versions) >= 3:
            return

        bubble.text_label.setText("<i>Buddy is thinking…</i>")
        if hasattr(bubble, 'redo_btn'):
            bubble.redo_btn.setEnabled(False)

        worker = RedoWorker(conversation_id, user_text)

        def on_done(result):
            bubble.versions.append({
                "text": result["reply"],
                "plan": result.get("plan_text"),
                "tools": result.get("tools_used"),
                "stats": result.get("stats"),
            })
            bubble.current_idx = len(bubble.versions) - 1
            bubble._render_current_version()
            if hasattr(bubble, 'redo_btn'):
                bubble.redo_btn.setEnabled(len(bubble.versions) < 3)

        def on_err(msg):
            bubble.text_label.setText(f"<i>Redo failed: {msg}</i>")
            if hasattr(bubble, 'redo_btn'):
                bubble.redo_btn.setEnabled(True)

        worker.finished.connect(on_done)
        worker.error.connect(on_err)
        # Keep a reference so the thread isn't GC'd
        self._redo_worker = worker
        worker.start()
        
    def _scroll_to_bottom(self):
        QApplication.processEvents()
        v_bar = self.scroll_area.verticalScrollBar()
        v_bar.setValue(v_bar.maximum())
        # Bubble sizes can still be settling (word-wrap, dev chamber, etc.)
        # a beat after this runs, so re-snap to bottom on the next tick too.
        QTimer.singleShot(0, lambda: v_bar.setValue(v_bar.maximum()))
 
 
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
 
    window = BuddyWindow()
    window.show_window()
    sys.exit(app.exec())