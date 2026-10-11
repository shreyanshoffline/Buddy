"""The message composer: FlowLayout (wraps attachment pills), attachment
pill/tray widgets, and the auto-growing ChatInput text box.

Compatible with current Buddy widgets + main_window:
  ChatInput(send_callback, parent=None, tray_ref=None)
  attached_files packets include name/extension/contents/path/mime_type/data_url
"""
import base64
import mimetypes
from pathlib import Path

from PySide6.QtWidgets import (
    QTextEdit, QWidget, QPushButton, QFrame,
    QLabel, QHBoxLayout, QFileDialog, QMessageBox,
    QLayout,
)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize, QThread
from PySide6.QtGui import QKeyEvent, QDragEnterEvent, QDropEvent, QFontMetrics
from pypdf import PdfReader

from ..theme import (
    HOVER_BG_COLOR, PRESSED_BG_COLOR, TEXT_COLOR_DARK,
    PILL_BG, PILL_BORDER, PILL_TEXT, UI_ATTACHMENT_HEIGHT,
    UI_ATTACHMENT_CLOSE_SIZE, UI_ATTACHMENT_FONT_SIZE, UI_INPUT_FONT_SIZE,
)

TEXT_EXTS = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".ts",
    ".yaml", ".yml", ".html", ".css",
}

MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_FILE_BYTES = 40 * 1024 * 1024
MAX_IMAGE_FILE_BYTES = 12 * 1024 * 1024

class FlowLayout(QLayout):
    """Wraps child widgets onto new rows as needed — no horizontal scrollbar ever."""

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

        self.setFixedHeight(UI_ATTACHMENT_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("%s · double-click to preview" % file_packet.get("name", "file"))
        self.setStyleSheet(f"""
            QFrame {{
                background: {PILL_BG};
                border: 1px solid {PILL_BORDER};
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
        label.setStyleSheet(f"color: {PILL_TEXT}; font-size: {UI_ATTACHMENT_FONT_SIZE}px; font-weight: 600; background: transparent; border: none;")
        metrics = QFontMetrics(label.font())
        label.setText(metrics.elidedText(name, Qt.ElideMiddle, 120))
        label.setToolTip(name)
        row.addWidget(label)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(UI_ATTACHMENT_CLOSE_SIZE, UI_ATTACHMENT_CLOSE_SIZE)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Remove file")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {PILL_TEXT};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 400;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG_COLOR};
                color: {TEXT_COLOR_DARK};
            }}
            QPushButton:pressed {{
                background: {PRESSED_BG_COLOR};
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


class ChatInput(QTextEdit):
    attachment_changed = Signal()

    def __init__(self, send_callback, parent=None, tray_ref=None):
        super().__init__(parent)
        self.send_callback = send_callback
        self.tray_ref = tray_ref
        self.setPlaceholderText("Ask Buddy...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAcceptDrops(True)
        self.attached_files = []
        self._pending_worker = None
        self.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                padding: 4px;
                font-size: {UI_INPUT_FONT_SIZE}px;
                color: #333;
            }
        """)
        # A comfortable writing field, while the controls stay in one compact
        # strip below it.
        self.setFixedHeight(58)
        self.textChanged.connect(self.adjust_height)

    def adjust_height(self):
        doc_height = self.document().size().height()
        if doc_height <= 0 or doc_height > 500:
            return
        self.setFixedHeight(max(58, min(int(doc_height) + 26, 140)))

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

    def _add_file_attachments(self, file_paths):
        existing = {item.get("path") for item in self.attached_files}
        valid_paths = []
        for file_path in file_paths:
            if not file_path.exists() or not file_path.is_file():
                continue
            if str(file_path) in existing:
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            suffix = file_path.suffix.lower()
            mime_type = mimetypes.guess_type(str(file_path))[0] or ""
            if mime_type.startswith("image/"):
                cap, label = MAX_IMAGE_FILE_BYTES, "12 MB"
            elif suffix == ".pdf":
                cap, label = MAX_PDF_FILE_BYTES, "40 MB"
            else:
                cap, label = MAX_TEXT_FILE_BYTES, "5 MB"
            if size > cap:
                QMessageBox.warning(
                    self, "File too large",
                    "“%s” is larger than the %s limit for this file type and won't be attached."
                    % (file_path.name, label),
                )
                continue
            valid_paths.append(file_path)
        if not valid_paths:
            return
        self._pending_worker = _AttachmentReadWorker(valid_paths)
        self._pending_worker.file_ready.connect(self._on_file_read)
        self._pending_worker.file_failed.connect(self._on_file_failed)
        self._pending_worker.finished.connect(self._show_attached_files)
        self._pending_worker.start()

    def _on_file_read(self, packet):
        self.attached_files.append(packet)

    def _on_file_failed(self, name, reason):
        QMessageBox.warning(self, "Couldn't attach file", "“%s” couldn't be attached: %s" % (name, reason))

    def open_file_picker(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach files",
            "",
            "Images and documents (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.txt *.md *.py *.js *.ts *.json *.csv *.yaml *.yml *.html *.css *.pdf);;All files (*)",
        )
        if paths:
            self._add_file_attachments([Path(p) for p in paths])


class _AttachmentReadWorker(QThread):
    file_ready = Signal(dict)
    file_failed = Signal(str, str)

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        for file_path in self.file_paths:
            try:
                packet = self._read_one(file_path)
                if packet:
                    self.file_ready.emit(packet)
            except Exception as exc:
                self.file_failed.emit(file_path.name, str(exc))

    def _read_one(self, file_path):
        suffix = file_path.suffix.lower()
        mime_type = mimetypes.guess_type(str(file_path))[0] or ""
        data_url = None
        if mime_type.startswith("image/"):
            encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
            data_url = "data:%s;base64,%s" % (mime_type, encoded)
            contents = "[Image attached]"
        else:
            contents = self._extract_file_text(file_path, suffix)
        return {
            "name": file_path.name,
            "extension": file_path.suffix,
            "contents": contents,
            "path": str(file_path),
            "mime_type": mime_type,
            "data_url": data_url,
        }

    def _extract_file_text(self, file_path, suffix):
        if suffix in TEXT_EXTS:
            try:
                return file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeError) as exc:
                return "[Could not read file: %s]" % exc
        if suffix == ".pdf":
            try:
                reader = PdfReader(str(file_path))
            except Exception as exc:
                return "[Could not open PDF: %s]" % exc
            pages = []
            failed_pages = 0
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    failed_pages += 1
            text = "\n\n".join(pages).strip()
            if not text:
                return "[PDF had no extractable text — it may be scanned images without OCR, or password-protected.]"
            if failed_pages:
                text += "\n\n[Note: %s page(s) in this PDF couldn't be read and were skipped.]" % failed_pages
            return text
        return "[Unsupported file type. Attach a text file, PDF, or image.]"
