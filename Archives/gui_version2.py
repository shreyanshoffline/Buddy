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

# ==============================================================================
# GLOBAL CONFIGURATION & UI CONSTANTS
# ==============================================================================
# Sidebar Dimensions
SIDEBAR_COLLAPSED_WIDTH = 52
SIDEBAR_EXPANDED_WIDTH = 168
ICON_SIZE = 18
SIDEBAR_ANIM_MS = 170

# Version Control / Redo Limits
MAX_REDOS = 3

# UI Colors & Styling
PRIMARY_COLOR = "#2b7ff0"
TEXT_COLOR_DARK = "#222222"
TEXT_COLOR_MUTED = "#8a8a8e"
HOVER_BG_COLOR = "rgba(0, 0, 0, 0.06)"
ACTIVE_BG_COLOR = "rgba(43, 127, 240, 0.12)"
CONTAINER_BG = "rgba(255, 255, 255, 0.85)"
SIDEBAR_BG = "rgba(248, 249, 251, 0.75)"
BORDER_COLOR = "rgba(0, 0, 0, 0.07)"

# Window sizing — kept generous enough that nothing clips at min size
WINDOW_MIN_WIDTH = 400
WINDOW_MIN_HEIGHT = 480
WINDOW_DEFAULT_WIDTH = 500
WINDOW_DEFAULT_HEIGHT = 620


# --- Cyber / Modern App Icon ---
def create_buddy_icon():
    svg_data = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
        <defs>
            <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#1c1c1e;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#000000;stop-opacity:1" />
            </linearGradient>
            <linearGradient id="logoGrad" x1="0%" y1="100%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#00f2fe;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#4facfe;stop-opacity:1" />
            </linearGradient>
        </defs>
        <rect width="64" height="64" rx="16" fill="url(#bgGrad)" />
        <path d="M 32 14 L 48 24 L 48 40 L 32 50 L 16 40 L 16 24 Z" fill="none" stroke="url(#logoGrad)" stroke-width="4" stroke-linejoin="round"/>
        <circle cx="32" cy="32" r="6" fill="url(#logoGrad)" />
    </svg>"""
    renderer = QSvgRenderer(svg_data.encode('utf-8'))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# --- SVG Icon Generator ---
def get_svg_icon(svg_path, color="#888888", size=20):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
                <path fill="{color}" d="{svg_path}"/>
              </svg>"""
    renderer = QSvgRenderer(svg.encode('utf-8'))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


ICONS = {
    "copy": "M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z",
    "like": "M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z",
    "dislike": "M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2c0 1.1.9 2 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L9.83 23l6.59-6.59c.36-.36.58-.86.58-1.41V5c0-1.1-.9-2-2-2zm4 0v12h4V3h-4z",
    "redo": "M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
    "left": "M15.41 16.59L10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z",
    "right": "M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z",
    "plus": "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "library": "M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12z",
    "settings": "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.73 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .43-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.49-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"
}


# --- Dynamic Expanding Input ---
class ChatInput(QTextEdit):
    def __init__(self, send_callback, parent=None):
        super().__init__(parent)
        self.send_callback = send_callback
        self.setPlaceholderText("Ask Buddy...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.setStyleSheet("""
            QTextEdit {
                background: white;
                border: 1px solid rgba(0,0,0,0.06);
                border-radius: 20px;
                padding: 10px 45px 10px 16px;
                font-size: 14px;
                color: #333;
            }
        """)
        self.textChanged.connect(self.adjust_height)

    def adjust_height(self):
        doc_height = self.document().size().height()
        min_height = 40
        max_height = 150
        new_height = max(min_height, min(int(doc_height) + 16, max_height))

        if self.parentWidget():
            self.parentWidget().setFixedHeight(new_height + 10)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_callback()
        else:
            super().keyPressEvent(event)


# --- DEV CHAMBER: Collapsible Thought Process ---
class DevChamber(QWidget):
    def __init__(self, plan_text="", tools_used=None, stats=None):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 0)
        self.layout.setSpacing(0)

        self.toggle_btn = QPushButton("▶ See thought process")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                color: #888888;
                font-size: 11px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: 4px 0px;
            }
            QPushButton:hover { color: #555555; }
            QPushButton:checked { color: #2b7ff0; }
        """)
        self.toggle_btn.toggled.connect(self.on_toggle)

        self.content_frame = QFrame()
        self.content_frame.setVisible(False)
        self.content_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.04);
                border-radius: 8px;
                border: 1px solid rgba(0, 0, 0, 0.06);
                margin-top: 4px;
            }
        """)

        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(8)

        if plan_text:
            plan_doc = QTextDocument()
            plan_doc.setMarkdown(plan_text)
            plan_label = QLabel(plan_doc.toHtml())
            plan_label.setWordWrap(True)
            plan_label.setStyleSheet("color: #555; font-size: 11px; background: transparent; border: none;")
            content_layout.addWidget(plan_label)

        if tools_used:
            tools_str = f"<b>Tools Executed:</b> {', '.join(tools_used)}"
            tools_label = QLabel(tools_str)
            tools_label.setWordWrap(True)
            tools_label.setStyleSheet("color: #999; font-size: 10px; font-style: italic; background: transparent; border: none;")
            content_layout.addWidget(tools_label)

        if stats:
            stats_str = " • ".join([f"{k}: {v}" for k, v in stats.items()])
            stats_label = QLabel(stats_str)
            stats_label.setWordWrap(True)
            stats_label.setStyleSheet("color: #aaa; font-size: 10px; font-family: monospace; background: transparent; border: none;")
            content_layout.addWidget(stats_label)

        self.layout.addWidget(self.toggle_btn)
        self.layout.addWidget(self.content_frame)

    def on_toggle(self, checked):
        self.toggle_btn.setText("▼ Hide thought process" if checked else "▶ See thought process")
        self.content_frame.setVisible(checked)


# --- Chat Bubble with Dev Chamber & Action Footer ---
class ChatBubble(QWidget):
    def __init__(self, text, is_user=True, plan_text=None, tools_used=None, stats=None, callbacks=None):
        super().__init__()
        self.is_user = is_user
        self.callbacks = callbacks
        self.dev_chamber_container = None

        self.versions = [{"text": text, "plan": plan_text, "tools": tools_used, "stats": stats}]
        self.current_idx = 0

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 4)
        self.layout.setAlignment(Qt.AlignTop)

        self.bubble_container = QFrame()
        self.bubble_container.setMaximumWidth(320)
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(14, 10, 14, 10)
        self.bubble_layout.setSpacing(6)

        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.text_label.setOpenExternalLinks(True)
        self.text_label.setStyleSheet("background: transparent; border: none;")
        self.bubble_layout.addWidget(self.text_label)

        if self.is_user:
            self.bubble_container.setStyleSheet("""
                QFrame { background-color: #2b7ff0; border-radius: 16px; border-bottom-right-radius: 4px; }
                QLabel { color: white; font-size: 14px; }
                QLabel a { color: #d0e2ff; }
            """)
            self.layout.addStretch()
            self.layout.addWidget(self.bubble_container)
        else:
            self.bubble_container.setStyleSheet("""
                QFrame { background-color: rgba(255, 255, 255, 0.9); border-radius: 16px; border-bottom-left-radius: 4px; }
                QLabel { color: #222222; font-size: 14px; }
                QLabel a { color: #2b7ff0; }
                QLabel pre { background-color: #f0f0f0; padding: 6px; border-radius: 6px; font-family: monospace; }
            """)

            self.dev_chamber_container = QVBoxLayout()
            self.bubble_layout.addLayout(self.dev_chamber_container)

            if self.callbacks:
                self._build_footer()

            self.layout.addWidget(self.bubble_container)
            self.layout.addStretch()

        self._render_current_version()

    def _build_footer(self):
        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(0, 4, 0, 0)

        btn_style = """
            QPushButton { background: transparent; border: none; padding: 4px; border-radius: 4px; }
            QPushButton:hover { background: rgba(0,0,0,0.05); }
            QPushButton:pressed { background: rgba(43,127,240,0.1); }
        """

        if 'copy' in self.callbacks:
            self.copy_btn = QPushButton(icon=get_svg_icon(ICONS["copy"]))
            self.copy_btn.setStyleSheet(btn_style)
            self.copy_btn.setCursor(Qt.PointingHandCursor)
            self.copy_btn.clicked.connect(lambda: self.callbacks['copy'](self.versions[self.current_idx]["text"]))
            self.footer_layout.addWidget(self.copy_btn)

        if 'like' in self.callbacks:
            self.like_btn = QPushButton(icon=get_svg_icon(ICONS["like"]))
            self.like_btn.setStyleSheet(btn_style)
            self.like_btn.setCursor(Qt.PointingHandCursor)
            self.like_btn.clicked.connect(lambda: (self.callbacks['like'](), self.like_btn.setIcon(get_svg_icon(ICONS["like"], "#2b7ff0"))))
            self.footer_layout.addWidget(self.like_btn)

        if 'dislike' in self.callbacks:
            self.dislike_btn = QPushButton(icon=get_svg_icon(ICONS["dislike"]))
            self.dislike_btn.setStyleSheet(btn_style)
            self.dislike_btn.setCursor(Qt.PointingHandCursor)
            self.dislike_btn.clicked.connect(lambda: (self.callbacks['dislike'](), self.dislike_btn.setIcon(get_svg_icon(ICONS["dislike"], "#f44336"))))
            self.footer_layout.addWidget(self.dislike_btn)

        self.footer_layout.addStretch()

        self.prev_btn = QPushButton(icon=get_svg_icon(ICONS["left"], "#555"))
        self.prev_btn.setFixedSize(20, 20)
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.clicked.connect(lambda: self._switch_page(-1))
        self.footer_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("1/1")
        self.page_label.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; background: transparent;")
        self.footer_layout.addWidget(self.page_label)

        self.next_btn = QPushButton(icon=get_svg_icon(ICONS["right"], "#555"))
        self.next_btn.setFixedSize(20, 20)
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.clicked.connect(lambda: self._switch_page(1))
        self.footer_layout.addWidget(self.next_btn)

        if 'redo' in self.callbacks:
            self.redo_btn = QPushButton(icon=get_svg_icon(ICONS["redo"]))
            self.redo_btn.setStyleSheet(btn_style)
            self.redo_btn.setCursor(Qt.PointingHandCursor)
            self.redo_btn.clicked.connect(self._trigger_redo)
            self.footer_layout.addWidget(self.redo_btn)

        self.bubble_layout.addLayout(self.footer_layout)

    def _trigger_redo(self):
        if len(self.versions) >= 3:
            return

        self.text_label.setText("<i>Buddy is thinking...</i>")
        self.redo_btn.setEnabled(False)
        QApplication.processEvents()

        new_result = self.callbacks['redo']()

        self.versions.append({
            "text": new_result["reply"],
            "plan": new_result["plan_text"],
            "tools": new_result["tools_used"],
            "stats": new_result["stats"]
        })
        self.current_idx = len(self.versions) - 1
        self._render_current_version()
        self.redo_btn.setEnabled(True)

    def _switch_page(self, direction):
        new_idx = self.current_idx + direction
        if 0 <= new_idx < len(self.versions):
            self.current_idx = new_idx
            self._render_current_version()

    def _render_current_version(self):
        data = self.versions[self.current_idx]

        doc = QTextDocument()
        doc.setMarkdown(data["text"])
        self.text_label.setText(doc.toHtml())

        if self.dev_chamber_container is not None:
            while self.dev_chamber_container.count():
                item = self.dev_chamber_container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            if not self.is_user and (data["plan"] or data["tools"] or data["stats"]):
                dev_chamber = DevChamber(data["plan"], data["tools"], data["stats"])
                self.dev_chamber_container.addWidget(dev_chamber)

        if not self.is_user and hasattr(self, 'page_label'):
            total = len(self.versions)
            self.page_label.setText(f"{self.current_idx + 1}/{total}")

            has_versions = total > 1
            self.prev_btn.setVisible(has_versions)
            self.page_label.setVisible(has_versions)
            self.next_btn.setVisible(has_versions)

            self.prev_btn.setEnabled(self.current_idx > 0)
            self.next_btn.setEnabled(self.current_idx < total - 1)

            if total >= 3:
                self.redo_btn.setIcon(get_svg_icon(ICONS["redo"], "#dddddd"))
                self.redo_btn.setEnabled(False)


# --- Feedback Pop-up for Dislikes ---
class FeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Feedback")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.selected_feedback = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 12px;
                border: 1px solid #ddd;
            }
        """)
        vbox = QVBoxLayout(container)
        vbox.setSpacing(12)
        vbox.setContentsMargins(20, 20, 20, 20)

        title = QLabel("<b>What went wrong?</b>")
        title.setStyleSheet("font-size: 14px; color: #333; border: none;")
        vbox.addWidget(title)

        self.btn_group = QButtonGroup(self)
        options = ["Didn't follow instructions", "Not helpful", "Incorrect information", "Other"]

        for i, opt in enumerate(options):
            radio = QRadioButton(opt)
            radio.setStyleSheet("color: #555; font-size: 13px; border: none;")
            self.btn_group.addButton(radio, i)
            vbox.addWidget(radio)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        submit_btn = QPushButton("Submit")

        cancel_btn.setStyleSheet("background: #f0f0f0; color: #555; border-radius: 6px; padding: 6px 12px; border: none;")
        submit_btn.setStyleSheet("background: #2b7ff0; color: white; border-radius: 6px; padding: 6px 12px; border: none;")

        cancel_btn.clicked.connect(self.reject)
        submit_btn.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(submit_btn)

        vbox.addLayout(btn_layout)
        layout.addWidget(container)

    def get_feedback(self):
        checked = self.btn_group.checkedButton()
        return checked.text() if checked else "User provided no specific reason."


# --- Nav Button: icon-only when collapsed, icon+label when expanded ---
class NavButton(QPushButton):
    def __init__(self, label, icon_path, small=False):
        super().__init__()
        self.label_text = label
        self.icon_path = icon_path
        self.small = small
        self.setIcon(get_svg_icon(icon_path, size=ICON_SIZE if not small else 14))
        self.setIconSize(self.iconSize())
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.set_collapsed(True)

    def set_collapsed(self, collapsed: bool):
        
        if collapsed:
            self.setText("")
            self.setToolTip(self.label_text)
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: center;
                    padding: 0px;
                    border-radius: 8px;
                    border: none;
                    background: transparent;
                    font-size: {"12px" if self.small else "13px"};
                    color: #444;
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            """)
        else:
            self.setText(f"  {self.label_text}")
            self.setToolTip("")
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 0px 8px;
                    border-radius: 8px;
                    border: none;
                    background: transparent;
                    font-size: {"12px" if self.small else "13px"};
                    font-weight: {"normal" if self.small else "500"};
                    color: #444;
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
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
                color: #444; 
                font-size: 13px; 
                font-weight: 500; 
                border: none; 
                background: transparent; 
            }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
        """)
        
        self.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 14, 5, 14)
        self.layout.setSpacing(6)

        # Main Navigation Buttons
        self.btn_new = NavButton("New chat", ICONS["plus"])
        self.btn_lib = NavButton("Library", ICONS["library"])
        self.btn_settings = NavButton("Settings", ICONS["settings"])
        
        # Recent Chats Section Header
        self.lbl_recents = QLabel("Recents")
        self.lbl_recents.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; font-weight: bold; margin-top: 8px; margin-bottom: 2px;")
        self.lbl_recents.hide()

        self.layout.addWidget(self.btn_new)
        self.layout.addWidget(self.btn_lib)
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
        chats = core.get_recent_conversations(limit=5)

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
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-weight: normal;
                    font-size: 12px;
                    padding: 6px 8px;
                    text-align: left;
                    border: none;
                    background: transparent;
                }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
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
            self.btn_settings.set_collapsed(not self.is_expanded)
            for row in self.recent_buttons:
                row.setVisible(self.is_expanded)

    def _show_chat_context_menu(self, conversation_id, global_pos):
        menu = QMenu()
        delete_action = menu.addAction("Delete chat")
        action = menu.exec(global_pos)
        if action == delete_action and hasattr(self, 'on_delete_chat_callback') and self.on_delete_chat_callback:
            self.on_delete_chat_callback(conversation_id)

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
                border-radius: 20px;
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
        size_grip.setStyleSheet("width: 14px; height: 14px; background: transparent;")
        footer_layout.addWidget(size_grip)

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