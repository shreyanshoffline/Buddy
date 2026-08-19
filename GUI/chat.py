from PySide6.QtWidgets import (
    QTextEdit, QWidget, QVBoxLayout, QPushButton, QFrame,
    QLabel, QHBoxLayout, QDialog, QButtonGroup, QRadioButton,
    QApplication, QFileDialog, QSizePolicy, QLayout, QLayoutItem,
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtGui import QKeyEvent, QTextDocument, QDragEnterEvent, QDropEvent, QFontMetrics
from pypdf import PdfReader

try:
    from .utils import get_svg_icon, ICONS
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from GUI.utils import get_svg_icon, ICONS
from pathlib import Path

TEXT_EXTS = {
        ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts",
        ".yaml", ".yml", ".html", ".css",
    }

# Single blue theme for every attachment pill, regardless of file type.
PILL_BG = "#E7F0FA"
PILL_BORDER = "#B7CDE8"
PILL_TEXT = "#1c6ad9"


class FlowLayout(QLayout):
    """Wraps child widgets onto new rows as needed instead of overflowing
    horizontally — so the attachment tray never needs a horizontal scrollbar."""

    def __init__(self, parent=None, margin=0, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self):
        return self._h_spacing

    def verticalSpacing(self):
        return self._v_spacing

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        max_x = rect.right() - margins.right()

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            item_width = item.sizeHint().width()
            item_height = item.sizeHint().height()
            next_x = x + item_width + self._h_spacing
            if next_x - self._h_spacing > max_x and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + self._v_spacing
                next_x = x + item_width + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(item_width, item_height)))
            x = next_x
            line_height = max(line_height, item_height)

        return y + line_height - rect.y() + margins.bottom()


class AttachmentPill(QFrame):
    removed = Signal(str)
    preview_requested = Signal(dict)

    def __init__(self, file_packet, parent=None):
        super().__init__(parent)
        self.file_packet = file_packet
        self.file_path = file_packet["path"]
        bg, border, text = PILL_BG, PILL_BORDER, PILL_TEXT

        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{file_packet.get('name', 'file')}  ·  double-click to preview")
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 13px;
            }}
            QFrame:hover {{
                border: 1px solid #7fa8dd;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 4, 0)
        row.setSpacing(4)

        name = file_packet.get("name", "file")
        label = QLabel()
        label.setStyleSheet(f"color: {text}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        metrics = QFontMetrics(label.font())
        label.setText(metrics.elidedText(name, Qt.ElideMiddle, 120))
        label.setToolTip(name)
        row.addWidget(label)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(16, 16)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Remove file")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {text};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 400;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.08);
                color: #1f2933;
            }}
        """)
        close_btn.clicked.connect(lambda: self.removed.emit(self.file_path))
        row.addWidget(close_btn)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.preview_requested.emit(self.file_packet)
        super().mouseDoubleClickEvent(event)


class AttachmentTray(QWidget):
    file_removed = Signal(str)
    preview_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.row = FlowLayout(self, margin=4, h_spacing=6, v_spacing=6)

    def set_files(self, files):
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for packet in files or []:
            pill = AttachmentPill(packet)
            pill.removed.connect(self.file_removed.emit)
            pill.preview_requested.connect(self.preview_requested.emit)
            self.row.addWidget(pill)

        self.setVisible(bool(files))
 
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
                padding: 10px 48px 10px 40px;
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

        tray = None
        parent = self.parentWidget()
        if parent:
            # find AttachmentTray sibling in composer layout
            from PySide6.QtWidgets import QWidget as _QW
            for child in parent.parent().children() if parent.parent() else []:
                if hasattr(child, 'file_removed'):
                    tray = child
                    break

        tray_height = (tray.sizeHint().height() + 6) if (tray and tray.isVisible()) else 0

        if parent:
            parent.setMinimumHeight(new_height + 10 + tray_height)

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
 
        files = []
        for url in urls:
            local_path = url.toLocalFile()
            if local_path:
                files.append(Path(local_path))
 
        if files:
            self._add_file_attachments(files)
            event.acceptProposedAction()
            return
 
        super().dropEvent(event)
 
    def clear(self):
        super().clear()
        if self.attached_files:
            self.clear_attachments()

    def clear_attachments(self):
        self.attached_files.clear()
        self.attachment_changed.emit()

    def remove_attachment(self, file_path):
        self.attached_files = [
            item for item in self.attached_files if item.get("path") != file_path
        ]
        self.attachment_changed.emit()

    def _show_attached_files(self):
        self.attachment_changed.emit()

    def _extract_file_text(self, file_path):
        suffix = file_path.suffix.lower()
        text_exts = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".yaml", ".yml", ".html", ".css"}
        if suffix in text_exts:
            return file_path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                text = "\n\n".join((page.extract_text() or "") for page in PdfReader(str(file_path)).pages).strip()
                return text or "[PDF had no extractable text.]"
            except Exception as exc:
                return f"[Could not read PDF: {exc}]"
        return "[Unsupported file type. Attach a text file or PDF.]"

    def _add_file_attachments(self, file_paths):
        existing = {item.get("path") for item in self.attached_files}
        for file_path in file_paths:
            if not file_path.exists() or not file_path.is_file():
                continue
            if str(file_path) in existing:
                continue
            try:
                self.attached_files.append({
                    "name": file_path.name,
                    "extension": file_path.suffix,
                    "contents": self._extract_file_text(file_path),
                    "path": str(file_path),
                })
            except Exception:
                continue
        self._show_attached_files()

    def open_file_picker(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach files",
            "",
            "Documents (*.txt *.md *.py *.js *.ts *.json *.csv *.yaml *.yml *.html *.css *.pdf);;All files (*)",
        )
        if paths:
            self._add_file_attachments([Path(p) for p in paths])
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
        self.bubble_container.setMaximumWidth(460)
        self.bubble_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
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