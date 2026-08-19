import sys
import random
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect, QSizeGrip,
    QDialog, QRadioButton, QButtonGroup, QSizePolicy, QGraphicsOpacityEffect,
    QStackedWidget,QLineEdit
)
from PySide6.QtCore import (
    Qt, QEvent, QPoint, QVariantAnimation, QEasingCurve,
    QPropertyAnimation, QTimer
)
from PySide6.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QKeyEvent,
    QTextDocument, QAction, QColor, QCursor
)
from PySide6.QtSvg import QSvgRenderer

import core
from core import process_message, new_message_history, send_and_save_message

from GUI import chat, settings, sidebar, utils
from GUI.chat import ChatBubble, ChatInput, FeedbackDialog, AttachmentBar
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
    CHAT_BUBBLE_AGENT, CHAT_BUBBLE_AGENT_TEXT, SIZE_GRIP_SIZE, TEXT_COLOR_SUBTITLE
)
from GUI.sidebar import Sidebar
from GUI.utils import create_buddy_icon
import storage.storage as db


class CardPage(QWidget):
    def __init__(self, title, subtitle="", parent=None, close_callback=None):
        super().__init__(parent)
        self.setObjectName("CardPage")
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
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 18, 18, 18) # Reduced from 24
        self.main_layout.setSpacing(10)                     # Tightened spacing
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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

class SettingsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Settings", "Customize your assistant and preferences.", parent, close_callback)

        self.profile = db.get_profile()

        self.settings_config = {
            "name":        {"label": "Display Name", "placeholder": "Enter name..."},
            "age":         {"label": "Age", "placeholder": "Enter age..."},
            "email":       {"label": "Email Address", "placeholder": "Enter email..."},
            "bio":         {"label": "About You", "placeholder": "A few sentences about yourself..."},
            "byo_api_key": {"label": "API Key", "placeholder": "Enter API token..."},
        }
        self.inputs = {}

        profile_label = QLabel("User Profile")
        profile_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold; background: transparent; margin-top: 8px;")
        self.main_layout.addWidget(profile_label)

        for key, config in self.settings_config.items():
            input_label = QLabel(config["label"])
            input_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; font-weight: bold; background: transparent;")
            self.main_layout.addWidget(input_label)

            line_edit = QLineEdit()
            line_edit.setText(str(self.profile.get(key)) if self.profile.get(key) not in (None, "") else "")
            line_edit.setPlaceholderText(config["placeholder"])
            if key == "byo_api_key":
                line_edit.setEchoMode(QLineEdit.Password)
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #ffffff;
                    border: 1.2px solid #d2d9e0;
                    border-radius: 8px;
                    padding: 6px 10px;
                    font-size: 12px;
                    color: #24292f;
                }
                QLineEdit:enabled:focus {
                    border: 1.2px solid #0969da;
                    background-color: #f6f8fa;
                }
            """)

            line_edit.mousePressEvent = lambda event, le=line_edit: self.on_box_clicked(event, le)
            line_edit.returnPressed.connect(lambda le=line_edit, k=key: self.lock_input(le, k))
            line_edit.editingFinished.connect(lambda le=line_edit, k=key: self.lock_input(le, k))

            self.main_layout.addWidget(line_edit)
            self.inputs[key] = line_edit

        self.main_layout.addStretch()

    def on_box_clicked(self, event, line_edit):
        if line_edit.isReadOnly():
            line_edit.setReadOnly(False)
            line_edit.setCursor(Qt.CursorShape.IBeamCursor)
            line_edit.selectAll()
            line_edit.setFocus()

    def lock_input(self, line_edit, settings_key):  
        if not line_edit.isReadOnly():
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.clearFocus()

            raw_value = line_edit.text().strip()

            if settings_key == "age":
                if raw_value == "":
                    updated_value = None
                else:
                    try:
                        updated_value = int(raw_value)
                    except ValueError:
                        # not a number, revert the box instead of saving garbage
                        line_edit.setText(str(self.profile.get("age")) if self.profile.get("age") is not None else "")
                        return
            else:
                updated_value = raw_value

            if updated_value != self.profile.get(settings_key):
                db.update_profile(**{settings_key: updated_value})
                self.profile[settings_key] = updated_value
class LibraryPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Library", "Browse your past chat histories and conversations with Buddy.", parent, close_callback)
        
        # 1. Define your chat history records as raw data
        self.chat_history = [
            {"id": "chat_001", "title": "Python Bug Fixing", "last_msg": "Fixed the layout overflow issue.", "time": "10:45 AM"},
            {"id": "chat_002", "title": "Marketing Copy Ideas", "last_msg": "Here are 5 catchy slogans for...", "time": "Yesterday"},
            {"id": "chat_003", "title": "UI Design Brainstorming", "last_msg": "Let's use rounded corners and...", "time": "Oct 14"},
        ]

        # 2. Section Header
        history_label = QLabel("Recent Chats")
        history_label.setStyleSheet(f"""
            QLabel {{
                color: {CARD_TEXT_COLOR}; 
                font-size: 13px; 
                font-weight: bold; 
                background: transparent; 
                margin-top: 8px;
            }}
        """)
        self.main_layout.addWidget(history_label)

        # 3. Dynamic Factory Loop: Creates a selectable item for each past conversation
        for chat in self.chat_history:
            
            # Format the display string: "Title • Last Message Snippet (Time)"
            chat_box = QLineEdit()
            chat_box.setText(f"{chat['title']}  •  \"{chat['last_msg']}\"   ({chat['time']})")
            chat_box.setReadOnly(True)
            chat_box.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Tighter, scaled design matching the settings styling rules
            chat_box.setStyleSheet("""
                QLineEdit {
                    background-color: #ffffff;
                    border: 1.2px solid #d2d9e0;
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 12px;
                    color: #24292f;
                }
                /* Changes color cleanly to show which chat history is highlighted/selected */
                QLineEdit:focus {
                    border: 1.2px solid #0969da;
                    background-color: #f3f7fa;
                    color: #0969da;
                }
            """)
            
            # Bind the mouse click event dynamically using a lambda map
            chat_box.mousePressEvent = lambda event, c_id=chat["id"], box=chat_box: self.on_chat_selected(event, c_id, box)
            
            self.main_layout.addWidget(chat_box)

        self.main_layout.addStretch()

    def on_chat_selected(self, event, chat_id, box):
        """Triggers instantly when a historical chat item is clicked."""
        box.setFocus()
        
        # This is where you would hook your code to load this specific chat into the main window
        
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
    def on_send_message(self):
        full_prompt = self.chat_input.get_formatted_payload()
        if not full_prompt.strip():
            return

        # Add message bubble to GUI chat window
        if hasattr(self, 'add_chat_bubble'):
            self.add_chat_bubble(full_prompt, is_user=True)

        # Process prompt via Core engine
        if hasattr(self, 'core') and self.core:
            self.core.handle_user_message(full_prompt)

        # Clear text edit and attached files
        self.chat_input.clear()

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

        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()
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
        self.greeting.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
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
                min-height: 24px;
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
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)

        # Initialize Attachment Bar and Chat Input
        self.attachment_bar = AttachmentBar()
        self.chat_input = ChatInput(send_callback=self.on_send_message)

        # Wire attachment signals
        self.chat_input.attachment_changed.connect(
            lambda: self.attachment_bar.update_attachments(self.chat_input.attached_files)
        )
        self.attachment_bar.file_removed.connect(self.chat_input.remove_attachment)

        # Safely connect attachment button if it exists
        attach_btn = getattr(self, 'attach_btn', getattr(self, 'attach_button', None))
        if attach_btn:
            attach_btn.clicked.connect(self.chat_input.open_file_dialog)

        # Add to input layout
        self.input_layout.addWidget(self.attachment_bar)
        self.input_layout.addWidget(self.chat_input)
        self.preview_button = QPushButton("Preview", self.input_container)
        self.preview_button.setFixedSize(84, 32)
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.preview_button.setVisible(False)
        self.preview_button.setStyleSheet(f"""
            QPushButton {{
                background: rgba(43,127,240,0.10);
                color: {PRIMARY_COLOR};
                border: 1px solid rgba(43,127,240,0.22);
                border-radius: 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(43,127,240,0.18);
            }}
        """)
        self.preview_button.clicked.connect(self._show_attachment_preview)

        self.send_button = QPushButton("➤", self.input_container)
        self.send_button.setFixedSize(SEND_BUTTON_SIZE, SEND_BUTTON_SIZE)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {CHAT_BUBBLE_USER_TEXT}; border: none; border-radius: {SEND_BUTTON_SIZE // 2}px; font-size: 15px; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
        """)
        self.send_button.clicked.connect(self.handle_send)

        def position_send_button():
            self.send_button.move(
                self.input_container.width() - self.send_button.width() - 8,
                self.input_container.height() - self.send_button.height() - 7
            )
            self.preview_button.move(
                self.send_button.x() - self.preview_button.width() - 10,
                self.input_container.height() - self.preview_button.height() - 7
            )

        self.input_container.resizeEvent = lambda e: (self.input_box.resize(self.input_container.size()), position_send_button())

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

        self.main_layout.addStretch(1)
        self.main_layout.addWidget(self.greeting, stretch=0)
        self.main_layout.setAlignment(self.greeting, Qt.AlignCenter)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet(f"color: {TEXT_COLOR_SUBTITLE}; font-size: {SUBTITLE_FONT_SIZE}px; background: transparent;")
        self.subtitle_label.setVisible(False)
        self.main_layout.addWidget(self.subtitle_label)
        self.main_layout.addWidget(self.scroll_area, stretch=1)
        self.main_layout.addStretch(1)
        self.main_layout.addWidget(self.input_container)

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
        self.library_page = LibraryPage(close_callback=self.hide)
        self.content_stack.addWidget(self.settings_page)
        self.content_stack.addWidget(self.library_page)

        self.sidebar.btn_new.clicked.connect(self.show_chat_view)
        self.sidebar.btn_lib.clicked.connect(self.show_library_view)
        self.sidebar.btn_settings.clicked.connect(self.show_settings_view)

        self.show_chat_view()
        window_layout.addWidget(self.container)

    def _update_attachment_controls(self):
        has_attachments = bool(getattr(self.input_box, 'attached_files', []))
        self.preview_button.setVisible(has_attachments)
        self.preview_button.raise_()

    def _show_attachment_preview(self):
        files = getattr(self.input_box, 'attached_files', [])
        if not files:
            return

        selected = files[-1]
        content = selected.get('contents', '')
        self.preview_title.setText(f"Preview: {selected.get('name', 'Attachment')}")
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
                metadata = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), dict) else {}
                bubble = ChatBubble(
                    text=content,
                    is_user=False,
                    plan_text=metadata.get("plan_text"),
                    tools_used=metadata.get("tools_used"),
                    stats=metadata.get("stats"),
                    callbacks={
                        'copy': lambda text=content: QApplication.clipboard().setText(text),
                        'like': lambda: None,
                        'dislike': lambda: None,
                        'redo': lambda: None
                    } if metadata else None
                )
                self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

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
        self.content_stack.setCurrentWidget(self.library_page)

    def load_chat(self, conversation_id):
        self.show_chat_view()
        self.current_conversation_id = conversation_id
        title = core.get_conversation_title(conversation_id)
        self._set_conversation_title(title)

        history = core.get_conversation_history(conversation_id)
        self.message_history = list(history)
        self._render_chat_history(history)
        self.scroll_area.setVisible(True)
        self.greeting.setVisible(False)

    def delete_chat(self, conversation_id):
        core.delete_conversation(conversation_id)
        if self.current_conversation_id == conversation_id:
            self.current_conversation_id = None
            self.current_chat_title = None
            self._set_conversation_title(None)
            self._clear_chat_history()
            self.scroll_area.setVisible(False)
            self.greeting.setVisible(True)
        self.sidebar.refresh_recents(on_chat_click=self.load_chat, on_delete_chat=self.delete_chat)

    def _new_chat(self):
        self.current_conversation_id = None
        self.current_chat_title = None
        self.message_history = new_message_history()
        self._set_conversation_title(None)
        self._clear_chat_history()
        self.scroll_area.setVisible(False)
        self.greeting.setVisible(True)

    def handle_send(self, forced_text=None):
        attached_files = list(getattr(self.input_box, 'attached_files', []))
        user_text = forced_text if forced_text else self.input_box.toPlainText().strip()

        if attached_files:
            attachment_summary = []
            for item in attached_files:
                attachment_summary.append(f"File: {item['name']}\n{item['contents']}")
            attached_block = "\n\n---\n\n".join(attachment_summary)
            user_text = f"{user_text}\n\n{attached_block}".strip() if user_text else attached_block
            self.input_box.attached_files.clear()

        if not user_text:
            return

        # 1. If new chat, make the DB entry
        if self.current_conversation_id is None:
            self.current_conversation_id = core.create_conversation()
            self._set_conversation_title(None)
            self.sidebar.refresh_recents()

        self.scroll_area.setVisible(True)
        self.greeting.setVisible(False)

        # 2. Add user bubble to UI
        self.message_history.append({"role": "user", "content": user_text})
        user_bubble = ChatBubble(text=user_text, is_user=True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, user_bubble)
        self._scroll_to_bottom()

        # 4. Let core.py handle the heavy lifting!
        result = send_and_save_message(self.current_conversation_id, user_text)
        self.input_box.clear()
        self.input_box.setFocus()
        
        # 5. Update the conversation title if the model generated one
        if result.get("chat_title"):
            self._set_conversation_title(result["chat_title"])
            self.sidebar.refresh_recents(on_chat_click=self.load_chat, on_delete_chat=self.delete_chat)

        # 6. Add AI bubble to UI
        self.message_history.append({"role": "assistant", "content": result["reply"]})
        def on_copy(text_to_copy):
            QApplication.clipboard().setText(text_to_copy)

        def on_like():
            self.message_history.append({"role": "system", "content": "User liked your previous response. Keep up this behavior."})

        def on_dislike():
            dialog = FeedbackDialog(self)
            if dialog.exec():
                feedback = dialog.get_feedback()
                self.message_history.append({"role": "system", "content": f"User disliked your previous response. Reason: {feedback}. Adjust future behavior accordingly."})

        def on_redo():
            return self._redo_assistant_response(user_text)

        callbacks = {
            'copy': on_copy,
            'like': on_like,
            'dislike': on_dislike,
            'redo': on_redo
        }

        reply_bubble = ChatBubble(
            text=result["reply"],
            is_user=False,
            plan_text=result["plan_text"],
            tools_used=result["tools_used"],
            stats=result["stats"],
            callbacks=callbacks
        )
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, reply_bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QApplication.processEvents()
        v_bar = self.scroll_area.verticalScrollBar()
        v_bar.setValue(v_bar.maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = BuddyWindow()
    window.show_window()
    sys.exit(app.exec())