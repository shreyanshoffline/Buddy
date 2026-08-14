import sys
import random
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect, QSizeGrip,
    QDialog, QRadioButton, QButtonGroup, QSizePolicy, QGraphicsOpacityEffect
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
from GUI.chat import ChatBubble, ChatInput, FeedbackDialog
from GUI.settings import (
    WINDOW_DEFAULT_HEIGHT, WINDOW_DEFAULT_WIDTH, WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
)
from GUI.sidebar import Sidebar
from GUI.utils import create_buddy_icon

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

        self.app_icon = create_buddy_icon()
        self.setWindowIcon(self.app_icon)
        self.current_conversation_id = None
        self.current_chat_title = None
        self.message_history = new_message_history()

        self._build_ui()
        self._setup_tray_icon()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        base_width = 500.0
        scale = max(0.8, min(self.width() / base_width, 1.6))

        title_size = int(14 * scale)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: #6a737d;
                font-size: {title_size}px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        greeting_size = int(21 * scale)
        system_font = QFont(".AppleSystemUIFont", greeting_size, QFont.Medium)
        if not system_font.exactMatch():
            system_font = QFont("Helvetica Neue", greeting_size, QFont.Medium)
        self.greeting.setFont(system_font)

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
        show_action = QAction("Toggle Overlay", self)
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
        self.container.setStyleSheet("""
            QFrame#MainContainer {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0.0 #fdfeff, stop:0.6 #eaf3fd, stop:1.0 #dceafc
                );
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 0.7);
            }
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

        chat_area = QWidget()
        self.main_layout = QVBoxLayout(chat_area)
        self.main_layout.setContentsMargins(16, 12, 16, 10)
        self.main_layout.setSpacing(10)

        self.h_wrapper.addWidget(chat_area, stretch=1)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 0, 0)

        self.title_label = QLabel("Buddy")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #777; border: none; font-size: 14px; font-weight: bold; border-radius: 12px; }
            QPushButton:hover { background: rgba(0, 0, 0, 0.08); color: #222; }
        """)
        close_btn.clicked.connect(self.hide)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        self.main_layout.addLayout(header_layout)

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
        self.greeting.setStyleSheet("color: #2b2b2b; background: transparent;")

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setVisible(False)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)

        self.input_container = QWidget()
        self.input_container.setFixedHeight(50)

        self.input_box = ChatInput(self.handle_send, self.input_container)
        self.send_button = QPushButton("➤", self.input_container)
        self.send_button.setFixedSize(36, 36)
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton { background: #2b7ff0; color: white; border: none; border-radius: 18px; font-size: 15px; }
            QPushButton:hover { background: #1c6ad9; }
        """)
        self.send_button.clicked.connect(self.handle_send)

        def position_send_button():
            self.send_button.move(
                self.input_container.width() - self.send_button.width() - 8,
                self.input_container.height() - self.send_button.height() - 7
            )

        self.input_container.resizeEvent = lambda e: (self.input_box.resize(self.input_container.size()), position_send_button())

        self.main_layout.addWidget(self.greeting, stretch=1)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("color: #555; font-size: 12px; background: transparent;")
        self.subtitle_label.setVisible(False)
        self.main_layout.addWidget(self.subtitle_label)
        self.main_layout.addWidget(self.scroll_area, stretch=1)
        self.main_layout.addWidget(self.input_container)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        size_grip = QSizeGrip(self.container)
        size_grip.setFixedSize(48, 48)
        size_grip.setCursor(Qt.SizeFDiagCursor)
        size_grip.setStyleSheet("QSizeGrip { background: transparent; }")
        footer_layout.addWidget(size_grip, alignment=Qt.AlignBottom | Qt.AlignRight)

        self.main_layout.addLayout(footer_layout)
        window_layout.addWidget(self.container)

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

    def load_chat(self, conversation_id):
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
        user_text = forced_text if forced_text else self.input_box.toPlainText().strip()
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
    window.toggle_window()
    sys.exit(app.exec())