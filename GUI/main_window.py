"""Main application window: the floating chat popover, tray icon, header,
composer, and the background workers that talk to core so the UI thread
never blocks on an LLM call."""
import sys
import random
import threading
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect, QSizeGrip,
    QDialog, QRadioButton, QButtonGroup, QSizePolicy, QGraphicsOpacityEffect,
    QStackedWidget, QLineEdit, QInputDialog, QMessageBox
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

from .widgets import ChatBubble, ChatInput, FeedbackDialog, AttachmentTray
from .icons import create_buddy_icon, get_svg_icon, ICONS
from .theme import (
    WINDOW_DEFAULT_HEIGHT, WINDOW_DEFAULT_WIDTH, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
    WINDOW_TITLE_TEXT, WINDOW_TITLE_COLOR, WINDOW_TITLE_SIZE, WINDOW_TITLE_WEIGHT,
    WINDOW_HEADER_HEIGHT, WINDOW_HEADER_PADDING_TOP, WINDOW_HEADER_PADDING_RIGHT,
    WINDOW_HEADER_PADDING_BOTTOM, WINDOW_HEADER_PADDING_LEFT, WINDOW_CLOSE_BUTTON_SIZE,
    WINDOW_CLOSE_BUTTON_COLOR, WINDOW_CLOSE_BUTTON_HOVER_BG, WINDOW_CLOSE_BUTTON_HOVER_COLOR,
    WINDOW_CLOSE_BUTTON_FONT_SIZE, WINDOW_BG_TOP, WINDOW_BG_MID, WINDOW_BG_BOTTOM,
    PAGE_BG_TOP, PAGE_BG_MID, PAGE_BG_BOTTOM, CARD_TEXT_COLOR, CARD_TEXT_SIZE,
    CARD_TEXT_WEIGHT, CARD_SUBTITLE_COLOR, CARD_SUBTITLE_SIZE, GREETING_FONT_SIZE,
    GREETING_COLOR, SUBTITLE_FONT_SIZE, SEND_BUTTON_SIZE, INPUT_CONTAINER_HEIGHT,
    PRIMARY_COLOR, PRIMARY_COLOR_DARK, PRIMARY_COLOR_PRESSED, ON_PRIMARY_TEXT,
    CHAT_BUBBLE_USER, CHAT_BUBBLE_USER_TEXT,
    CHAT_BUBBLE_AGENT, CHAT_BUBBLE_AGENT_TEXT, SIZE_GRIP_SIZE, TEXT_COLOR_SUBTITLE,
    TEXT_COLOR_MUTED, TEXT_COLOR_DARK, HOVER_BG_COLOR, PRESSED_BG_COLOR, ACTIVE_BG_COLOR,
    BORDER_COLOR, DANGER_COLOR, DANGER_SOFT_BG, DANGER_BORDER, INPUT_BG, CONTAINER_BG
)
from .sidebar import Sidebar
from .pages import SettingsPage, LibraryPage, BillingPage, ArtifactsPage, OnboardingPage

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
                    image_attachments=[item for item in (self.attachments or []) if item.get("mime_type", "").startswith("image/")],
                )
            else:
                result = core.send_and_save_message(
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
        self.cancel_event = threading.Event()

    def run(self):
        try:
            result = core.redo_assistant_response(
                self.conversation_id, self.user_text, cancel_check=self.cancel_event.is_set
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))



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
        self.message_history = core.new_message_history()
        self._thinking_bubble = None
        self._last_assistant_bubble = None
        self._is_sending = False
        self._send_worker = None
        self._redo_worker = None
        self.incognito_mode = False

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_workers)

        self._build_ui()
        self._setup_tray_icon()
 
    def restart_app(self):
        """Fully restarts the Buddy process to apply a new theme. A real
        restart is slower than an in-place live swap, but it's 100%
        reliable — module hot-reloading proved fragile in real use (it
        passed in testing but didn't consistently apply for real), so this
        is the honest, dependable choice instead."""
        import os
        import sys
        self._shutdown_workers()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _fix_sidebar_layout(self):
        """Forces the sidebar back to its correct collapsed width and a real
        layout recalculation. The first paint of a frameless/translucent
        window can settle with the sidebar narrower than intended; this
        re-asserts the actual constant (not whatever width() currently
        reports, which can itself be the wrong value) and invalidates the
        parent layout so Qt actually redraws it correctly."""
        from .theme import SIDEBAR_COLLAPSED_WIDTH
        if not self.sidebar.is_expanded:
            self.sidebar.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH)
        self.sidebar.updateGeometry()
        self.h_wrapper.invalidate()
        self.h_wrapper.activate()
        self.container.updateGeometry()
        self.update()

    def _shutdown_workers(self):
        """Called on app quit — signals any in-flight send/redo to stop and
        gives it a moment to unwind cleanly instead of letting Qt destroy a
        still-running QThread (which crashes)."""
        for worker in (self._send_worker, self._redo_worker):
            if worker is not None and worker.isRunning():
                worker.cancel_event.set()
                worker.wait(3000)  # give it up to 3s to notice and exit cleanly

    def resizeEvent(self, event):
        super().resizeEvent(event)
 
        base_width = 500.0
        scale = max(0.85, min(self.width() / base_width, 2.2))
 
        title_size = max(14, int(WINDOW_TITLE_SIZE * scale))
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {WINDOW_TITLE_COLOR};
                font-size: {title_size}px;
                font-weight: {WINDOW_TITLE_WEIGHT};
                background: transparent;
                border: none;
            }}
        """)
 
        greeting_size = max(18, int(GREETING_FONT_SIZE * scale))
        system_font = QFont("Segoe UI", greeting_size, QFont.Medium)
        if not system_font.exactMatch():
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
        self._maybe_show_intro_tip()

    def _maybe_show_intro_tip(self):
        """The header has a few icon-only buttons (incognito glasses, private
        lock) that aren't self-explanatory at a glance. Explain them once,
        the first time the app is ever shown, rather than relying purely on
        hover tooltips nobody finds."""
        profile = core.get_profile()
        if profile.get("has_seen_intro_tip"):
            return
        core.update_profile(has_seen_intro_tip=True)
        QMessageBox.information(
            self, "Welcome to Buddy",
            "Two quick things about the icons in the header:\n\n"
            "🕶️  Incognito — starts a chat that's never saved anywhere. "
            "Nothing you say in it is written to disk.\n\n"
            "🔒  Private — marks the current chat as private. It won't show up "
            "in the sidebar, and opening it later requires confirmation (or a "
            "PIN, if you set one in Settings).\n\n"
            "You can always hover either icon for a reminder."
        )

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
            on_chat_click_callback=self._request_open_chat,
            on_new_chat_callback=self._new_chat,
            on_delete_chat_callback=self.delete_chat
        )
        self.h_wrapper.addWidget(self.sidebar)
 
        self.sidebar.refresh_recents(on_chat_click=self._request_open_chat, on_delete_chat=self.delete_chat)
        # Qt sometimes paints the sidebar's first frame before the layout has
        # settled, looking squeezed until you click it once. Forcing the
        # same width re-assert that a manual toggle does fixes that.
        self._fix_sidebar_layout()
        QTimer.singleShot(0, self._fix_sidebar_layout)
        QTimer.singleShot(60, self._fix_sidebar_layout)
 
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
                border: none;
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
        self.privacy_btn.setStyleSheet(f"""
            QPushButton {{ border: none; background: transparent; border-radius: 6px; font-size: 14px; padding: 4px; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        self.privacy_btn.clicked.connect(self._toggle_current_chat_private)
        self.privacy_btn.setVisible(False)

        self.incognito_btn = QPushButton("🕶️")
        self.incognito_btn.setFlat(True)
        self.incognito_btn.setCursor(Qt.PointingHandCursor)
        self.incognito_btn.setToolTip("Start an incognito chat (nothing is saved)")
        self.incognito_btn.setStyleSheet(f"""
            QPushButton {{ border: none; background: transparent; border-radius: 6px; font-size: 14px; padding: 4px; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
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
 
        self.greeting = QLabel(self._random_greeting())
        self.greeting.setAlignment(Qt.AlignCenter)
        self.greeting.setWordWrap(True)
        self.greeting.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.greeting.setMinimumHeight(60)
        self.greeting.setStyleSheet(f"color: {GREETING_COLOR}; background: transparent; border: none;")
        self.greeting.setFont(QFont("Helvetica Neue", GREETING_FONT_SIZE, QFont.Medium))
 
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
        self.chat_container.setStyleSheet("background: transparent; border: none;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 12)
        self.chat_layout.setSpacing(6)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)
 
        # --- Unified composer box: rounded frame holding tray + input row ---
        self.input_container = QFrame()
        self.input_container.setObjectName("InputContainer")
        self.input_container.setStyleSheet(f"""
            QFrame#InputContainer {{
                background: {INPUT_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 20px;
            }}
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
        self.attach_button.setToolTip("Attach a file")
        self.attach_button.setIcon(get_svg_icon(ICONS["plus"], TEXT_COLOR_SUBTITLE, 16))
        self.attach_button.setIconSize(QSize(16, 16))
        self.attach_button.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; border-radius: 14px; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        self.attach_button.clicked.connect(lambda: self.input_box.open_file_picker())

        self.input_box = ChatInput(self.handle_send, tray_ref=self.attachment_tray)
        self.input_box.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                border: none;
                padding: 4px 4px;
                font-size: 14px;
                color: {TEXT_COLOR_DARK};
            }}
        """)

        self.send_button = QPushButton("➤")
        self.send_button.setFixedSize(SEND_BUTTON_SIZE, SEND_BUTTON_SIZE)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setToolTip("Send message (Enter)")
        self.send_button.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: {SEND_BUTTON_SIZE // 2}px; font-size: 15px; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            QPushButton:pressed {{ background: {PRIMARY_COLOR_PRESSED}; }}
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
        self.preview_panel.setStyleSheet(f"""
            QFrame#PreviewPanel {{
                background: {CONTAINER_BG};
                border-radius: 18px;
                border: 1px solid {BORDER_COLOR};
            }}
        """)
        self.preview_layout = QVBoxLayout(self.preview_panel)
        self.preview_layout.setContentsMargins(14, 12, 14, 14)
        self.preview_layout.setSpacing(10)
 
        self.preview_header = QHBoxLayout()
        self.preview_title = QLabel("Preview")
        self.preview_title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_COLOR_DARK};")
        self.preview_header.addWidget(self.preview_title)
        self.preview_header.addStretch()
        self.preview_close_btn = QPushButton("✕")
        self.preview_close_btn.setFixedSize(28, 28)
        self.preview_close_btn.setCursor(Qt.PointingHandCursor)
        self.preview_close_btn.setToolTip("Close preview")
        self.preview_close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_COLOR_SUBTITLE};
                border: none;
                border-radius: 14px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG_COLOR};
            }}
            QPushButton:pressed {{
                background: {PRESSED_BG_COLOR};
            }}
        """)
        self.preview_close_btn.clicked.connect(self._hide_attachment_preview)
        self.preview_header.addWidget(self.preview_close_btn)
        self.preview_layout.addLayout(self.preview_header)
 
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet(f"""
            QTextEdit {{
                background: {INPUT_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
                color: {TEXT_COLOR_DARK};
                font-size: 12px;
                padding: 10px;
            }}
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
        self.subtitle_label.setStyleSheet(f"color: {TEXT_COLOR_SUBTITLE}; font-size: {SUBTITLE_FONT_SIZE}px; background: transparent; border: none;")
        self.subtitle_label.setVisible(False)
        self.main_layout.addWidget(self.subtitle_label)
        self.main_layout.addWidget(self.scroll_area, stretch=1)

        self.composer = QWidget()
        self.composer.setStyleSheet("background: transparent; border: none;")
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
 
        self.settings_page = SettingsPage(close_callback=self.hide, on_theme_changed=self.restart_app)
        self.library_page = LibraryPage(close_callback=self.hide, on_chat_selected=self._request_open_chat, on_delete_chat=self._delete_chat_from_library)
        self.billing_page = BillingPage(close_callback=self.hide)
        self.artifacts_page = ArtifactsPage(close_callback=self.hide)
        self.onboarding_page = OnboardingPage(close_callback=self.hide, on_complete=self.show_chat_view)
        self.content_stack.addWidget(self.settings_page)
        self.content_stack.addWidget(self.library_page)
        self.content_stack.addWidget(self.billing_page)
        self.content_stack.addWidget(self.artifacts_page)
        self.content_stack.addWidget(self.onboarding_page)
 
        self.sidebar.btn_new.clicked.connect(self.show_chat_view)
        self.sidebar.btn_lib.clicked.connect(self.show_library_view)
        self.sidebar.btn_artifacts.clicked.connect(self.show_artifacts_view)
        self.sidebar.btn_billing.clicked.connect(self.show_billing_view)
        self.sidebar.btn_settings.clicked.connect(self.show_settings_view)
 
        self.show_chat_view()
        if not core.get_profile().get("onboarding_complete"):
            self.show_onboarding_view()
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
        last_user_text = None
        for msg in history:
            role = msg.get("role")
            content = msg.get("content") or ""
            if role == "user":
                last_user_text = content
                bubble = ChatBubble(text=content, is_user=True)
                self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
            elif role == "assistant":
                metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
                msg_id = msg.get("id")

                def make_history_redo(captured_user_text=last_user_text, captured_conv=self.current_conversation_id):
                    def do_redo():
                        self._trigger_redo_for_bubble(captured_conv, captured_user_text, self._last_assistant_bubble)
                    return do_redo

                bubble = ChatBubble(
                    text=content,
                    is_user=False,
                    plan_text=metadata.get("plan_text"),
                    tools_used=metadata.get("tools_used"),
                    tool_log=metadata.get("tool_log"),
                    stats=metadata.get("stats"),
                    message_id=msg_id,
                    initial_feedback=msg.get("feedback"),
                    callbacks={
                        'copy': lambda text=content: QApplication.clipboard().setText(text),
                        'like': lambda active, mid=msg_id: self._set_feedback(mid, 'like', active),
                        'dislike': lambda active, mid=msg_id: self._set_feedback(mid, 'dislike', active),
                        'redo': make_history_redo() if last_user_text is not None else (lambda: None)
                        },
                        images=metadata.get("images", []),
                )
                self._last_assistant_bubble = bubble
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
        self._set_active_nav(self.sidebar.btn_new)
 
    def apply_profile_changes(self):
        """Settings just changed. Refresh greeting, login chip, and chat prompt."""
        if hasattr(self, "greeting") and self.greeting.isVisible():
            self.greeting.setText(self._random_greeting())
        if hasattr(self, "message_history"):
            try:
                core.refresh_history_profile(self.message_history)
            except Exception:
                self.message_history = core.new_message_history()
        for page in (
            getattr(self, "settings_page", None),
            getattr(self, "library_page", None),
            getattr(self, "billing_page", None),
            getattr(self, "artifacts_page", None),
            getattr(self, "onboarding_page", None),
        ):
            if page is not None and hasattr(page, "refresh_account_header"):
                page.refresh_account_header()

    def show_settings_view(self):
        if hasattr(self.settings_page, "reload_from_db"):
            self.settings_page.reload_from_db()
        self.content_stack.setCurrentWidget(self.settings_page)
        self._set_active_nav(self.sidebar.btn_settings)
 
    def show_billing_view(self):
        self.content_stack.setCurrentWidget(self.billing_page)
        self._set_active_nav(self.sidebar.btn_billing)
 
    def show_library_view(self):
        self.library_page.refresh_chats()
        self.content_stack.setCurrentWidget(self.library_page)
        self._set_active_nav(self.sidebar.btn_lib)

    def show_artifacts_view(self):
        self.artifacts_page.refresh_artifacts()
        self.content_stack.setCurrentWidget(self.artifacts_page)
        self._set_active_nav(self.sidebar.btn_artifacts)

    def show_onboarding_view(self):
        self.content_stack.setCurrentWidget(self.onboarding_page)
        self._set_active_nav(None)
 
    def _set_active_nav(self, active_btn):
        for btn in (self.sidebar.btn_new, self.sidebar.btn_lib, self.sidebar.btn_artifacts, self.sidebar.btn_billing, self.sidebar.btn_settings):
            btn.set_active(btn is active_btn)

    def _request_open_chat(self, conversation_id):
        """Gate in front of load_chat: real chats open immediately, but a
        private chat always requires a deliberate confirm - a PIN if one's
        been set in Settings, otherwise an explicit 'this isn't protected,
        open anyway?' warning. This is the ONLY path that should ever open
        a chat - sidebar clicks, library clicks, and search results all
        route through here."""
        if not core.get_conversation_is_private(conversation_id):
            self.load_chat(conversation_id)
            return

        if core.has_privacy_pin():
            pin, ok = QInputDialog.getText(
                self, "Private Chat", "Enter your PIN to open this chat:",
                QLineEdit.Password
            )
            if not ok:
                return
            if not core.verify_privacy_pin(pin):
                QMessageBox.warning(self, "Incorrect PIN", "That PIN doesn't match. Chat stays locked.")
                return
            self.load_chat(conversation_id)
        else:
            choice = QMessageBox.warning(
                self, "Private Chat",
                "This chat is marked private, but no PIN is set - anyone using "
                "Buddy can open it. Set a Privacy PIN in Settings for real "
                "protection.\n\nOpen it anyway?",
                QMessageBox.Open | QMessageBox.Cancel,
                QMessageBox.Cancel
            )
            if choice == QMessageBox.Open:
                self.load_chat(conversation_id)

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
            self.incognito_btn.setStyleSheet(f"QPushButton {{ border: none; background: {ACTIVE_BG_COLOR}; border-radius: 6px; font-size: 14px; padding: 4px; }}")
            self.incognito_btn.setToolTip("Incognito ON — nothing in this chat will be saved")
            self.subtitle_label.setText("🕶️ Incognito — nothing here is saved")
            self.subtitle_label.setVisible(True)
        else:
            self.incognito_btn.setStyleSheet(f"""
                QPushButton {{ border: none; background: transparent; border-radius: 6px; font-size: 14px; padding: 4px; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
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
        self.sidebar.refresh_recents(on_chat_click=self._request_open_chat, on_delete_chat=self.delete_chat)

    def _delete_chat_from_library(self, conversation_id):
        self.delete_chat(conversation_id)
        self.library_page.refresh_chats()
 
    def _random_greeting(self):
        """Personalizes the greeting with the user's saved name, if any —
        falls back to a friendly generic greeting for a fresh install."""
        name = (core.get_profile().get("name") or "").strip()
        if name:
            return random.choice([
                f"Hi {name}, what's on your mind?",
                f"Hi, how can I help you {name}?",
                f"Let's dive in, {name}",
                f"Welcome back, {name}!",
                "Ready when you are",
            ])
        return random.choice([
            "Hi there, what's on your mind?",
            "Hi, how can I help you today?",
            "Let's dive in",
            "Welcome back!",
            "Ready when you are",
        ])

    def _new_chat(self):
        self.current_conversation_id = None
        self.current_chat_title = None
        self.message_history = core.new_message_history()
        self._set_conversation_title(None)
        self.privacy_btn.setVisible(False)
        if self.incognito_mode:
            self._toggle_incognito_mode()
        self._clear_chat_history()
        self.scroll_area.setVisible(False)
        self.greeting.setText(self._random_greeting())
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
            self.send_button.setToolTip("Send message (Enter)")
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
        if label:
            self._thinking_bubble.add_progress_step(label)

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

            def make_redo(captured_user_text=self._last_send_text, captured_conv=conv_id):
                def do_redo():
                    self._trigger_redo_for_bubble(captured_conv, captured_user_text, self._last_assistant_bubble)
                return do_redo

            msg_id = result.get("message_id")
            assistant_bubble = ChatBubble(
                text=reply,
                is_user=False,
                plan_text=result.get("plan_text"),
                tools_used=result.get("tools_used"),
                tool_log=result.get("tool_log"),
                stats=result.get("stats"),
                images=result.get("images", []),
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
            self.sidebar.refresh_recents(on_chat_click=self._request_open_chat, on_delete_chat=self.delete_chat)

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
        if "insufficient credits" in msg or "paymentrequired" in msg or "credits" in msg:
            return "API credits needed", "Buddy's AI provider rejected this request because the API account has no credits. Add credits to the account linked to API_KEY, or add your own key in Settings."
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
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {DANGER_SOFT_BG};
                border: 1px solid {DANGER_BORDER};
                border-radius: 14px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(4)

        title_label = QLabel(f"⚠ {title}")
        title_label.setStyleSheet(f"color: {DANGER_COLOR}; font-size: 12.5px; font-weight: 700; background: transparent; border: none;")
        card_layout.addWidget(title_label)

        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet(f"color: {DANGER_COLOR}; font-size: 12px; background: transparent; border: none;")
        card_layout.addWidget(detail_label)

        retry_btn = QPushButton("Retry")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.setToolTip("Send that message again")
        retry_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DANGER_COLOR}; color: white; border: none;
                border-radius: 8px; padding: 4px 12px; font-size: 12px; font-weight: 600;
                max-width: 70px;
            }}
            QPushButton:hover {{ background: {DANGER_BORDER}; }}
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
                "tool_log": result.get("tool_log"),
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