from PySide6.QtWidgets import (
    QTextEdit, QWidget, QVBoxLayout, QPushButton, QFrame, 
    QLabel, QHBoxLayout, QDialog, QButtonGroup, QRadioButton, 
    QApplication, QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QTextDocument, QDragEnterEvent, QDropEvent

try:
    from .utils import get_svg_icon, ICONS
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from GUI.utils import get_svg_icon, ICONS
from pathlib import Path


# --- File Attachment Pill Badge ---
class AttachmentBadge(QFrame):
    removed = Signal(dict)

    def __init__(self, file_data: dict, parent=None):
        super().__init__(parent)
        self.file_data = file_data

        self.setStyleSheet("""
            QFrame {
                background-color: #eef3fc;
                border: 1px solid #d0e2ff;
                border-radius: 12px;
                padding: 2px 8px;
            }
            QLabel {
                color: #2b7ff0;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #888888;
                font-size: 12px;
                font-weight: bold;
                padding: 0px 2px;
            }
            QPushButton:hover {
                color: #f44336;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        label = QLabel(f"📄 {file_data['name']}")
        remove_btn = QPushButton("✕")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.removed.emit(self.file_data))

        layout.addWidget(label)
        layout.addWidget(remove_btn)


# --- Attachment Container Bar ---
class AttachmentBar(QWidget):
    file_removed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(6)
        self.layout.setAlignment(Qt.AlignLeft)
        self.hide()

    def update_attachments(self, files: list):
        # Clear existing badges
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not files:
            self.hide()
            return

        for file_data in files:
            badge = AttachmentBadge(file_data)
            badge.removed.connect(self._on_badge_removed)
            self.layout.addWidget(badge)

        self.show()

    def _on_badge_removed(self, file_data):
        self.file_removed.emit(file_data)


# --- Dynamic Expanding Input ---
class ChatInput(QTextEdit):
    attachment_changed = Signal()

    def __init__(self, send_callback, parent=None):
        super().__init__(parent)
        self.send_callback = send_callback
        self.setPlaceholderText("Ask Buddy...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAcceptDrops(True)
        self.attached_files = []

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

    def open_file_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            "",
            "All Supported (*.txt *.md *.json *.csv *.py *.js *.ts *.yaml *.yml *.html *.css);;All Files (*)"
        )
        if file_paths:
            self._add_file_attachments([Path(p) for p in file_paths])

    def clear_attachments(self):
        self.attached_files.clear()
        self.attachment_changed.emit()

    def remove_attachment(self, file_data: dict):
        if file_data in self.attached_files:
            self.attached_files.remove(file_data)
            self.attachment_changed.emit()

    def _add_file_attachments(self, file_paths):
        text_extensions = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".yaml", ".yml", ".html", ".css", ".xml", ".sh"}

        for file_path in file_paths:
            if not file_path.exists() or not file_path.is_file():
                continue

            try:
                if file_path.suffix.lower() in text_extensions:
                    file_contents = file_path.read_text(encoding="utf-8", errors="replace")
                else:
                    file_contents = f"[Binary or unsupported file: {file_path.name}]"

                packet = {
                    "name": file_path.name,
                    "extension": file_path.suffix,
                    "contents": file_contents,
                    "path": str(file_path)
                }
                # Prevent duplicate file attachments by path
                if not any(f["path"] == str(file_path) for f in self.attached_files):
                    self.attached_files.append(packet)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")

        self.attachment_changed.emit()

    def get_formatted_payload(self) -> str:
        """Combines the typed prompt with attached file content."""
        prompt_text = self.toPlainText().strip()
        if not self.attached_files:
            return prompt_text

        attachment_blocks = []
        for file_info in self.attached_files:
            ext_lang = file_info["extension"].lstrip(".")
            block = f"[Attached File: {file_info['name']}]\n```{ext_lang}\n{file_info['contents']}\n```"
            attachment_blocks.append(block)

        combined_attachments = "\n\n".join(attachment_blocks)
        if prompt_text:
            return f"{prompt_text}\n\n{combined_attachments}"
        return combined_attachments

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

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return

        files = [Path(url.toLocalFile()) for url in urls if url.toLocalFile()]
        if files:
            self._add_file_attachments(files)
            event.acceptProposedAction()
            return

        super().dropEvent(event)

    def clear(self):
        super().clear()
        self.clear_attachments()


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

        def set_active_button(button, active, active_color, inactive_color="#555"):
            button.setIcon(get_svg_icon(button.property("icon_key"), active_color if active else inactive_color))
            button.setProperty("active", active)
            button.setStyleSheet(btn_style + ("QPushButton[active=true] { background: rgba(43,127,240,0.12); }" if active_color == "#2b7ff0" else "QPushButton[active=true] { background: rgba(244,67,54,0.12); }" if active_color == "#f44336" else ""))

        if 'copy' in self.callbacks:
            self.copy_btn = QPushButton(icon=get_svg_icon(ICONS["copy"], "#555"))
            self.copy_btn.setProperty("icon_key", "copy")
            self.copy_btn.setStyleSheet(btn_style)
            self.copy_btn.setCursor(Qt.PointingHandCursor)
            self.copy_btn.clicked.connect(lambda: (self.callbacks['copy'](self.versions[self.current_idx]["text"]), set_active_button(self.copy_btn, True, "#2b7ff0")))
            self.footer_layout.addWidget(self.copy_btn)

        if 'like' in self.callbacks:
            self.like_btn = QPushButton(icon=get_svg_icon(ICONS["like"], "#555"))
            self.like_btn.setProperty("icon_key", "like")
            self.like_btn.setStyleSheet(btn_style)
            self.like_btn.setCursor(Qt.PointingHandCursor)
            self.like_btn.clicked.connect(self._toggle_like)
            self.footer_layout.addWidget(self.like_btn)

        if 'dislike' in self.callbacks:
            self.dislike_btn = QPushButton(icon=get_svg_icon(ICONS["dislike"], "#555"))
            self.dislike_btn.setProperty("icon_key", "dislike")
            self.dislike_btn.setStyleSheet(btn_style)
            self.dislike_btn.setCursor(Qt.PointingHandCursor)
            self.dislike_btn.clicked.connect(self._toggle_dislike)
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
            self.redo_btn = QPushButton(icon=get_svg_icon(ICONS["redo"], "#555"))
            self.redo_btn.setProperty("icon_key", "redo")
            self.redo_btn.setStyleSheet(btn_style)
            self.redo_btn.setCursor(Qt.PointingHandCursor)
            self.redo_btn.clicked.connect(self._trigger_redo)
            self.footer_layout.addWidget(self.redo_btn)

        self.bubble_layout.addLayout(self.footer_layout)

    def _toggle_like(self):
        if getattr(self, 'like_btn', None) is None:
            return

        is_active = self.like_btn.property('active')
        if is_active:
            self.like_btn.setProperty('active', False)
            self.like_btn.setIcon(get_svg_icon(ICONS['like'], '#555'))
            self.like_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; padding: 4px; border-radius: 4px; }
                QPushButton:hover { background: rgba(0,0,0,0.05); }
                QPushButton:pressed { background: rgba(43,127,240,0.1); }
            """)
            if hasattr(self, 'callbacks') and self.callbacks and 'like' in self.callbacks:
                self.callbacks['like']()
            return

        self.like_btn.setProperty('active', True)
        self.like_btn.setIcon(get_svg_icon(ICONS['like'], '#2b7ff0'))
        self.like_btn.setStyleSheet("""
            QPushButton { background: rgba(43,127,240,0.12); border: none; padding: 4px; border-radius: 4px; }
            QPushButton:hover { background: rgba(43,127,240,0.18); }
            QPushButton:pressed { background: rgba(43,127,240,0.2); }
        """)

        if hasattr(self, 'dislike_btn') and self.dislike_btn.property('active'):
            self.dislike_btn.setProperty('active', False)
            self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], '#555'))
            self.dislike_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; padding: 4px; border-radius: 4px; }
                QPushButton:hover { background: rgba(0,0,0,0.05); }
                QPushButton:pressed { background: rgba(43,127,240,0.1); }
            """)

        if hasattr(self, 'callbacks') and self.callbacks and 'like' in self.callbacks:
            self.callbacks['like']()

    def _toggle_dislike(self):
        if getattr(self, 'dislike_btn', None) is None:
            return

        is_active = self.dislike_btn.property('active')
        if is_active:
            self.dislike_btn.setProperty('active', False)
            self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], '#555'))
            self.dislike_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; padding: 4px; border-radius: 4px; }
                QPushButton:hover { background: rgba(0,0,0,0.05); }
                QPushButton:pressed { background: rgba(43,127,240,0.1); }
            """)
            if hasattr(self, 'callbacks') and self.callbacks and 'dislike' in self.callbacks:
                self.callbacks['dislike']()
            return

        self.dislike_btn.setProperty('active', True)
        self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], '#f44336'))
        self.dislike_btn.setStyleSheet("""
            QPushButton { background: rgba(244,67,54,0.12); border: none; padding: 4px; border-radius: 4px; }
            QPushButton:hover { background: rgba(244,67,54,0.18); }
            QPushButton:pressed { background: rgba(244,67,54,0.2); }
        """)

        if hasattr(self, 'like_btn') and self.like_btn.property('active'):
            self.like_btn.setProperty('active', False)
            self.like_btn.setIcon(get_svg_icon(ICONS['like'], '#555'))
            self.like_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; padding: 4px; border-radius: 4px; }
                QPushButton:hover { background: rgba(0,0,0,0.05); }
                QPushButton:pressed { background: rgba(43,127,240,0.1); }
            """)

        if hasattr(self, 'callbacks') and self.callbacks and 'dislike' in self.callbacks:
            self.callbacks['dislike']()

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
        self.redo_btn.setIcon(get_svg_icon(ICONS["redo"], "#2b7ff0"))
        self.redo_btn.setStyleSheet("""
            QPushButton { background: rgba(43,127,240,0.12); border: none; padding: 4px; border-radius: 4px; }
            QPushButton:hover { background: rgba(43,127,240,0.18); }
            QPushButton:pressed { background: rgba(43,127,240,0.2); }
        """)

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