"""The 'thinking' paw-print loader, the collapsible dev-chamber, and the
main ChatBubble widget (user/assistant messages, feedback footer, redo)."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFrame,
    QLabel, QHBoxLayout, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRectF
from PySide6.QtGui import (
    QKeyEvent, QTextDocument, QFontMetrics,
    QPainter, QColor, QPainterPath
)

from ..icons import get_svg_icon, ICONS
from ..theme import (
    HOVER_BG_COLOR, PRESSED_BG_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK, DANGER_COLOR, DANGER_SOFT_BG,
    TEXT_COLOR_SUBTITLE, TEXT_COLOR_MUTED, BORDER_COLOR,
    CHAT_BUBBLE_USER, CHAT_BUBBLE_USER_TEXT, CHAT_BUBBLE_AGENT, CHAT_BUBBLE_AGENT_TEXT,
)

class BuddyPawLoader(QWidget):
    """Compact animated thinking indicator featuring bear paw prints walking upward."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 38)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(35)  # ~30 FPS smooth walking loop

    def _animate(self):
        self._phase = (self._phase + 0.045) % 4.0
        self.update()

    def _draw_paw(self, painter: QPainter, cx: float, cy: float, scale: float, opacity: float, is_right: bool):
        if opacity <= 0.01:
            return

        painter.save()
        painter.translate(cx, cy)
        painter.scale(scale, scale)

        # Primary accent color for Buddy paws
        color = QColor("#2b7ff0")
        color.setAlphaF(max(0.0, min(1.0, opacity)))
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)

        # Main heel pad
        main_pad = QPainterPath()
        main_pad.addRoundedRect(QRectF(-4.5, -2.0, 9.0, 6.0), 3.0, 3.0)
        painter.drawPath(main_pad)

        # 4 Toe pads in an arc
        toe_offsets = [
            (-3.5, -4.8, 1.4),  # Toe 1 (Outer)
            (-1.2, -5.8, 1.6),  # Toe 2
            (1.2, -5.8, 1.6),   # Toe 3
            (3.5, -4.8, 1.4),   # Toe 4 (Inner)
        ]

        for tx, ty, radius in toe_offsets:
            toe_x = tx + (0.3 if is_right else -0.3)
            painter.drawEllipse(QRectF(toe_x - radius, ty - radius, radius * 2, radius * 2))

        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center_x = self.width() / 2.0
        total_paws = 4
        spacing_y = 8.0
        base_y = 30.0

        for i in range(total_paws):
            # Calculate position for paw i offset by continuous phase walking upwards
            progress = (i - self._phase) % total_paws
            y_pos = base_y - (progress * spacing_y)
            is_right = (i % 2 == 1)
            x_offset = 6.5 if is_right else -6.5
            x_pos = center_x + x_offset

            # Opacity transition: New paws form at top, old paws erase at bottom
            if y_pos > 25.0:
                opacity = max(0.0, (32.0 - y_pos) / 7.0)
            elif y_pos < 10.0:
                opacity = max(0.0, (y_pos - 3.0) / 7.0)
            else:
                opacity = 0.92

            scale = 0.85 + (opacity * 0.15)
            self._draw_paw(painter, x_pos, y_pos, scale, opacity, is_right)


class DevChamber(QWidget):
    def __init__(self, plan_text="", tools_used=None, stats=None, tool_log=None):
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

        if tool_log:
            # Detailed per-call breakdown: name, args, result, timing.
            log_header = QLabel("<b>Tool Log:</b>")
            log_header.setStyleSheet("color: #777; font-size: 10px; background: transparent; border: none;")
            content_layout.addWidget(log_header)

            for i, entry in enumerate(tool_log, start=1):
                args_str = ", ".join(f"{k}={v!r}" for k, v in (entry.get("args") or {}).items())
                call_line = f"{i}. <b>{entry.get('name', 'tool')}</b>({args_str}) — {entry.get('duration', '?')}"
                call_label = QLabel(call_line)
                call_label.setWordWrap(True)
                call_label.setStyleSheet("color: #666; font-size: 10px; background: transparent; border: none;")
                content_layout.addWidget(call_label)

                result_text = entry.get("result", "")
                if result_text:
                    result_label = QLabel(f"↳ {result_text}")
                    result_label.setWordWrap(True)
                    result_label.setStyleSheet("color: #999; font-size: 10px; font-family: monospace; background: transparent; border: none; padding-left: 8px;")
                    content_layout.addWidget(result_label)
        elif tools_used:
            # Fallback for older saved messages that only have the flat name list.
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


class ChatBubble(QWidget):
    def __init__(self, text="", is_user=True, plan_text=None, tools_used=None, stats=None, tool_log=None, callbacks=None, is_thinking=False, message_id=None, initial_feedback=None):
        super().__init__()
        self.is_user = is_user
        self.is_thinking = is_thinking
        self.callbacks = callbacks if callbacks is not None else ({} if not is_user else None)
        self.message_id = message_id
        self.initial_feedback = initial_feedback
        self.dev_chamber_container = None

        self.versions = [{"text": text, "plan": plan_text, "tools": tools_used, "tool_log": tool_log, "stats": stats}]
        self.current_idx = 0

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setAlignment(Qt.AlignTop)

        self.bubble_container = QFrame()
        self.bubble_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(14, 10, 14, 10)
        self.bubble_layout.setSpacing(6)

        if self.is_thinking:
            # Accumulating "thinking" transcript: completed steps stack up as
            # small muted lines above, the current step stays next to the
            # animated paw loader — similar to how Claude shows its work.
            self.thinking_container = QVBoxLayout()
            self.thinking_container.setContentsMargins(0, 0, 0, 0)
            self.thinking_container.setSpacing(2)

            self.thinking_history_layout = QVBoxLayout()
            self.thinking_history_layout.setContentsMargins(0, 0, 0, 0)
            self.thinking_history_layout.setSpacing(2)
            self.thinking_container.addLayout(self.thinking_history_layout)

            current_row = QHBoxLayout()
            current_row.setContentsMargins(0, 0, 0, 0)
            current_row.setSpacing(8)
            self.paw_loader = BuddyPawLoader()
            current_row.addWidget(self.paw_loader)

            self.thinking_current_label = QLabel("Buddy is thinking...")
            self.thinking_current_label.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 13px; font-weight: 500; font-style: italic; background: transparent; border: none;")
            current_row.addWidget(self.thinking_current_label)
            current_row.addStretch()
            self.thinking_container.addLayout(current_row)

            self.bubble_layout.addLayout(self.thinking_container)
        else:
            self.text_label = QLabel()
            self.text_label.setWordWrap(True)
            self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            self.text_label.setOpenExternalLinks(True)
            self.text_label.setStyleSheet("background: transparent; border: none;")
            self.bubble_layout.addWidget(self.text_label)

        if self.is_user:
            self.bubble_container.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {CHAT_BUBBLE_USER}, stop:1 {PRIMARY_COLOR_DARK});
                    border-radius: 18px;
                    border-bottom-right-radius: 4px;
                }}
                QLabel {{
                    color: {CHAT_BUBBLE_USER_TEXT};
                    font-size: 13.5px;
                    line-height: 1.4;
                }}
                QLabel a {{ color: {CHAT_BUBBLE_USER_TEXT}; text-decoration: underline; }}
            """)
            self.layout.addStretch()
            self.layout.addWidget(self.bubble_container)
        else:
            self.bubble_container.setStyleSheet(f"""
                QFrame {{
                    background-color: {CHAT_BUBBLE_AGENT};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: 18px;
                    border-bottom-left-radius: 4px;
                }}
                QLabel {{
                    color: {CHAT_BUBBLE_AGENT_TEXT};
                    font-size: 13.5px;
                    line-height: 1.4;
                }}
                QLabel a {{ color: {PRIMARY_COLOR}; text-decoration: none; font-weight: 600; }}
                QLabel pre {{
                    background-color: {HOVER_BG_COLOR};
                    color: {CHAT_BUBBLE_AGENT_TEXT};
                    padding: 8px 10px;
                    border-radius: 8px;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 12px;
                }}
            """)

            if not self.is_thinking:
                self.dev_chamber_container = QVBoxLayout()
                self.bubble_layout.addLayout(self.dev_chamber_container)
                self._build_footer()

            self.layout.addWidget(self.bubble_container)
            self.layout.addStretch()

        if not self.is_thinking:
            self._render_current_version()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_width()

    def _update_responsive_width(self):
        """Ensures bubble stretches up to slightly less than halfway (~46%) when window expands."""
        parent_w = self.width()
        if parent_w > 0:
            # Sizing constraint: Max width is ~46% of window width so each side gets roughly half
            calc_max = int(parent_w * 0.46)
            target_max = max(240, calc_max)
            self.bubble_container.setMaximumWidth(target_max)

    def _build_footer(self):
        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(0, 4, 0, 0)

        btn_style = f"""
            QPushButton {{ background: transparent; border: none; padding: 4px; border-radius: 4px; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """

        def set_active_button(button, active, active_color, inactive_color=TEXT_COLOR_SUBTITLE):
            button.setIcon(get_svg_icon(button.property("icon_key"), active_color if active else inactive_color))
            button.setProperty("active", active)
            button.setStyleSheet(btn_style)

        self.copy_btn = QPushButton(icon=get_svg_icon(ICONS["copy"], TEXT_COLOR_SUBTITLE))
        self.copy_btn.setProperty("icon_key", "copy")
        self.copy_btn.setStyleSheet(btn_style)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy this reply")
        self.copy_btn.clicked.connect(lambda: (self.callbacks.get('copy', lambda t: None)(self.versions[self.current_idx]["text"]), set_active_button(self.copy_btn, True, PRIMARY_COLOR)))
        self.footer_layout.addWidget(self.copy_btn)

        self.like_btn = QPushButton(icon=get_svg_icon(ICONS["like"], TEXT_COLOR_SUBTITLE))
        self.like_btn.setProperty("icon_key", "like")
        self.like_btn.setStyleSheet(btn_style)
        self.like_btn.setCursor(Qt.PointingHandCursor)
        self.like_btn.setToolTip("Good response")
        self.like_btn.clicked.connect(self._toggle_like)
        self.footer_layout.addWidget(self.like_btn)

        self.dislike_btn = QPushButton(icon=get_svg_icon(ICONS["dislike"], TEXT_COLOR_SUBTITLE))
        self.dislike_btn.setProperty("icon_key", "dislike")
        self.dislike_btn.setStyleSheet(btn_style)
        self.dislike_btn.setCursor(Qt.PointingHandCursor)
        self.dislike_btn.setToolTip("Bad response")
        self.dislike_btn.clicked.connect(self._toggle_dislike)
        self.footer_layout.addWidget(self.dislike_btn)

        self.footer_layout.addStretch()

        self.prev_btn = QPushButton(icon=get_svg_icon(ICONS["left"], TEXT_COLOR_SUBTITLE))
        self.prev_btn.setFixedSize(20, 20)
        self.prev_btn.setStyleSheet(btn_style)
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setToolTip("Previous version")
        self.prev_btn.clicked.connect(lambda: self._switch_page(-1))
        self.footer_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("1/1")
        self.page_label.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        self.footer_layout.addWidget(self.page_label)

        self.next_btn = QPushButton(icon=get_svg_icon(ICONS["right"], TEXT_COLOR_SUBTITLE))
        self.next_btn.setFixedSize(20, 20)
        self.next_btn.setStyleSheet(btn_style)
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setToolTip("Next version")
        self.next_btn.clicked.connect(lambda: self._switch_page(1))
        self.footer_layout.addWidget(self.next_btn)

        self.redo_btn = QPushButton(icon=get_svg_icon(ICONS["redo"], TEXT_COLOR_SUBTITLE))
        self.redo_btn.setProperty("icon_key", "redo")
        self.redo_btn.setStyleSheet(btn_style)
        self.redo_btn.setCursor(Qt.PointingHandCursor)
        self.redo_btn.setToolTip("Regenerate this response (up to 3 times)")
        self.redo_btn.clicked.connect(self._trigger_redo)
        self.footer_layout.addWidget(self.redo_btn)

        self.bubble_layout.addLayout(self.footer_layout)

        if self.initial_feedback == "like":
            self.like_btn.setProperty('active', True)
            self.like_btn.setIcon(get_svg_icon(ICONS['like'], PRIMARY_COLOR))
        elif self.initial_feedback == "dislike":
            self.dislike_btn.setProperty('active', True)
            self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], DANGER_COLOR))

    def _toggle_like(self):
        is_active = self.like_btn.property('active')
        if is_active:
            self.like_btn.setProperty('active', False)
            self.like_btn.setIcon(get_svg_icon(ICONS['like'], TEXT_COLOR_SUBTITLE))
            self.like_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; padding: 4px; border-radius: 4px; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
            self.callbacks.get('like', lambda active: None)(False)
            return

        self.like_btn.setProperty('active', True)
        self.like_btn.setIcon(get_svg_icon(ICONS['like'], PRIMARY_COLOR))
        self.like_btn.setStyleSheet(f"""
            QPushButton {{ background: {HOVER_BG_COLOR}; border: none; padding: 4px; border-radius: 4px; }}
            QPushButton:hover {{ background: {PRESSED_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        if hasattr(self, 'dislike_btn'):
            self.dislike_btn.setProperty('active', False)
            self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], TEXT_COLOR_SUBTITLE))
            self.dislike_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; padding: 4px; border-radius: 4px; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
        self.callbacks.get('like', lambda active: None)(True)

    def _toggle_dislike(self):
        is_active = self.dislike_btn.property('active')
        if is_active:
            self.dislike_btn.setProperty('active', False)
            self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], TEXT_COLOR_SUBTITLE))
            self.dislike_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; padding: 4px; border-radius: 4px; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
            self.callbacks.get('dislike', lambda active: None)(False)
            return

        # Dislike stays a fixed semantic red regardless of the chosen theme —
        # a negative signal shouldn't visually blend in as "just the theme color".
        self.dislike_btn.setProperty('active', True)
        self.dislike_btn.setIcon(get_svg_icon(ICONS['dislike'], DANGER_COLOR))
        self.dislike_btn.setStyleSheet(f"""
            QPushButton {{ background: {DANGER_SOFT_BG}; border: none; padding: 4px; border-radius: 4px; }}
            QPushButton:hover {{ background: {DANGER_SOFT_BG}; }}
            QPushButton:pressed {{ background: {DANGER_SOFT_BG}; }}
        """)
        if hasattr(self, 'like_btn'):
            self.like_btn.setProperty('active', False)
            self.like_btn.setIcon(get_svg_icon(ICONS['like'], TEXT_COLOR_SUBTITLE))
            self.like_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; padding: 4px; border-radius: 4px; }}
                QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
                QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
            """)
        self.callbacks.get('dislike', lambda active: None)(True)

    def _switch_page(self, direction):
        new_idx = self.current_idx + direction
        if 0 <= new_idx < len(self.versions):
            self.current_idx = new_idx
            self._render_current_version()

    def _trigger_redo(self):
        self.callbacks.get('redo', lambda: None)()

    def add_progress_step(self, text, max_history=4):
        """Pushes the current 'thinking' status into the transcript as a
        completed step, then shows the new text as the active step. Older
        steps are capped so a long-running task doesn't grow the bubble
        forever."""
        if not self.is_thinking or not hasattr(self, 'thinking_current_label'):
            return
        prev_text = self.thinking_current_label.text().rstrip("…").rstrip(".")
        if prev_text and text != self.thinking_current_label.text():
            done_label = QLabel(f"✓  {prev_text}")
            done_label.setStyleSheet(f"color: {TEXT_COLOR_MUTED}; font-size: 11px; background: transparent; border: none; padding-left: 24px;")
            self.thinking_history_layout.addWidget(done_label)
            while self.thinking_history_layout.count() > max_history:
                old_item = self.thinking_history_layout.takeAt(0)
                if old_item.widget():
                    old_item.widget().deleteLater()
        self.thinking_current_label.setText(text)

    def _render_current_version(self):
        v = self.versions[self.current_idx]

        doc = QTextDocument()
        doc.setMarkdown(v["text"])
        self.text_label.setText(doc.toHtml())

        if not self.is_user and self.dev_chamber_container is not None:
            while self.dev_chamber_container.count():
                item = self.dev_chamber_container.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            has_chamber_data = v.get("plan") or v.get("tools") or v.get("tool_log") or v.get("stats")
            if has_chamber_data:
                chamber = DevChamber(plan_text=v.get("plan"), tools_used=v.get("tools"), stats=v.get("stats"), tool_log=v.get("tool_log"))
                self.dev_chamber_container.addWidget(chamber)

        if hasattr(self, 'page_label'):
            self.page_label.setText(f"{self.current_idx + 1}/{len(self.versions)}")
            self.prev_btn.setEnabled(self.current_idx > 0)
            self.next_btn.setEnabled(self.current_idx < len(self.versions) - 1)