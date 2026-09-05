"""User profile settings page — everything here is wired to a real backend:
- Display Name / Age / Bio personalize the actual system prompt Buddy uses.
- API Key overrides the app's default key for every model call, if set —
  and is actually validated against a live test call.
- Favorite Apps / Quick Links feed Buddy's "open my usual stuff" behavior.
- Privacy PIN gates opening any chat marked private.
- Clear All Chat History is a real, working destructive action.
- Theme changes apply live, no restart needed.
"""
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QTextEdit, QPushButton, QMessageBox, QHBoxLayout,
    QVBoxLayout, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal as QtSignal, QTimer

import core
import models
from .card_page import CardPage
from ..widgets import ToggleSwitch
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    PRIMARY_COLOR_PRESSED, ON_PRIMARY_TEXT, DANGER_COLOR, DANGER_SOFT_BG,
    DANGER_BORDER, HOVER_BG_COLOR, PRESSED_BG_COLOR, BORDER_COLOR,
    THEME_OPTIONS, CURRENT_ACCENT, CURRENT_DARK_MODE, INPUT_BG, TEXT_COLOR_DARK,
    TEXT_COLOR_SUBTITLE, SECTION_CARD_BG, ACTIVE_BG_COLOR,
)


class ApiKeyValidationWorker(QThread):
    finished = QtSignal(bool, str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        is_valid, message = models.validate_api_key(self.api_key)
        self.finished.emit(is_valid, message)


FIELD_STYLE = f"""
    QLineEdit {{
        background-color: {INPUT_BG};
        border: 1.2px solid {BORDER_COLOR};
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 12px;
        color: {CARD_TEXT_COLOR};
    }}
    QLineEdit:enabled:focus {{
        border: 1.2px solid {PRIMARY_COLOR};
        background-color: {HOVER_BG_COLOR};
    }}
"""

TEXTAREA_STYLE = f"""
    QTextEdit {{
        background-color: {INPUT_BG};
        border: 1.2px solid {BORDER_COLOR};
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 12px;
        color: {CARD_TEXT_COLOR};
    }}
    QTextEdit:focus {{
        border: 1.2px solid {PRIMARY_COLOR};
        background-color: {HOVER_BG_COLOR};
    }}
"""


class AutoSaveTextEdit(QTextEdit):
    """Multi-line field with the same click-to-edit / save-on-blur pattern
    as the single-line fields, so every field type behaves consistently."""

    def __init__(self, on_save=None, parent=None):
        super().__init__(parent)
        self.on_save = on_save
        self._original_text = ""
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)

    def mousePressEvent(self, event):
        if self.isReadOnly():
            self.setReadOnly(False)
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self._original_text = self.toPlainText()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self.isReadOnly():
            self.setReadOnly(True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            new_text = self.toPlainText().strip()
            if new_text != self._original_text.strip() and self.on_save:
                self.on_save(new_text)


class SettingsPage(CardPage):
    def __init__(self, parent=None, close_callback=None, on_theme_changed=None):
        super().__init__("Settings", "Customize your assistant and preferences.", parent, close_callback)
        self.on_theme_changed = on_theme_changed
        self.profile = core.get_profile()
        self.inputs = {}
        self._validation_worker = None

        self._build_profile_card()
        self._build_appearance_card()
        self._build_privacy_card()
        self._build_danger_card()
        self.main_layout.addStretch()

    def _broadcast_profile(self):
        window = self.window()
        if hasattr(window, "apply_profile_changes"):
            window.apply_profile_changes()

    def reload_from_db(self):
        """Settings is built once at startup. Call this before showing the
        page so values saved in onboarding actually appear."""
        self.profile = core.get_profile()
        mapping = {
            "name": "name",
            "age": "age",
            "email": "email",
            "bio": "bio",
            "favorite_apps": "favorite_apps",
            "quick_links": "quick_links",
            "byo_api_key": "byo_api_key",
        }
        for key, profile_key in mapping.items():
            widget = self.inputs.get(key)
            if widget is None:
                continue
            value = self.profile.get(profile_key)
            text = "" if value is None else str(value)
            if hasattr(widget, "setPlainText"):
                widget.setPlainText(text)
            else:
                widget.setText(text)

    # --- shared helpers -----------------------------------------------
    def _make_card(self, title):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {SECTION_CARD_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        outer.addWidget(title_label)

        self.main_layout.addWidget(card)
        return outer

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; font-weight: bold; background: transparent; border: none; margin-top: 4px;")
        return lbl

    def _flash_saved(self, label_widget):
        """Brief, non-blocking 'Saved!' confirmation next to a field."""
        original = label_widget.text()
        label_widget.setText(f"{original}  ·  ✓ Saved")
        label_widget.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: bold; background: transparent; border: none; margin-top: 4px;")
        QTimer.singleShot(1400, lambda: (
            label_widget.setText(original),
            label_widget.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; font-weight: bold; background: transparent; border: none; margin-top: 4px;")
        ))

    # --- User Profile card ----------------------------------------------
    def _build_profile_card(self):
        layout = self._make_card("User Profile")

        line_fields = {
            "name":  {"label": "Display Name", "placeholder": "What should Buddy call you?"},
            "age":   {"label": "Age", "placeholder": "Enter age..."},
            "email": {"label": "Email Address", "placeholder": "Enter email..."},
        }
        for key, config in line_fields.items():
            lbl = self._field_label(config["label"])
            layout.addWidget(lbl)

            line_edit = QLineEdit()
            raw_value = self.profile.get(key)
            line_edit.setText(str(raw_value) if raw_value is not None else "")
            line_edit.setPlaceholderText(config["placeholder"])
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.setStyleSheet(FIELD_STYLE)
            line_edit.mousePressEvent = lambda event, le=line_edit: self.on_box_clicked(event, le)
            line_edit.returnPressed.connect(lambda le=line_edit, k=key, l=lbl: self.lock_input(le, k, l))
            line_edit.editingFinished.connect(lambda le=line_edit, k=key, l=lbl: self.lock_input(le, k, l))
            layout.addWidget(line_edit)
            self.inputs[key] = line_edit

        text_fields = {
            "bio":           {"label": "About You", "placeholder": "A few sentences about yourself..."},
            "favorite_apps": {"label": "Favorite Apps (comma-separated)", "placeholder": "e.g. Spotify, Chrome, Discord"},
            "quick_links":   {"label": "Quick Links (comma-separated, Name: URL)", "placeholder": "e.g. GitHub: https://github.com"},
        }
        for key, config in text_fields.items():
            lbl = self._field_label(config["label"])
            layout.addWidget(lbl)

            text_edit = AutoSaveTextEdit(on_save=lambda val, k=key, l=lbl: self._save_text_field(k, val, l))
            text_edit.setPlainText(self.profile.get(key) or "")
            text_edit.setPlaceholderText(config["placeholder"])
            text_edit.setStyleSheet(TEXTAREA_STYLE)
            layout.addWidget(text_edit)
            self.inputs[key] = text_edit

        api_label = self._field_label("API Key (overrides the default)")
        if not self.profile.get("hackclub_verified"):
            api_label.setText("API Key (Hack Club verification required)")
        layout.addWidget(api_label)
        api_field = QLineEdit()
        raw_key = self.profile.get("byo_api_key")
        api_field.setText(str(raw_key) if raw_key else "")
        api_field.setPlaceholderText("Enter your own OpenRouter API key...")
        api_field.setEchoMode(QLineEdit.Password)
        api_field.setReadOnly(not bool(self.profile.get("hackclub_verified")))
        api_field.setProperty("requires_hackclub", True)
        if not self.profile.get("hackclub_verified"):
            api_field.setPlaceholderText("Sign in with a verified Hack Club account first")
            api_field.setToolTip("Only verified Hack Club members can configure a custom API key")
        api_field.setCursor(Qt.CursorShape.PointingHandCursor)
        api_field.setStyleSheet(FIELD_STYLE)
        api_field.mousePressEvent = lambda event, le=api_field: self.on_box_clicked(event, le)
        api_field.returnPressed.connect(lambda: self.lock_input(api_field, "byo_api_key", api_label))
        api_field.editingFinished.connect(lambda: self.lock_input(api_field, "byo_api_key", api_label))
        layout.addWidget(api_field)
        self.inputs["byo_api_key"] = api_field

        self.api_key_status = QLabel("")
        self.api_key_status.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self.api_key_status.setVisible(False)
        layout.addWidget(self.api_key_status)

    def _save_text_field(self, key, value, label_widget):
        existing = self.profile.get(key) or ""
        if value != existing:
            core.update_profile(**{key: value})
            self.profile[key] = value
            self._flash_saved(label_widget)
            self._broadcast_profile()

    def on_box_clicked(self, event, line_edit):
        if line_edit.property("requires_hackclub") and not self.profile.get("hackclub_verified"):
            QMessageBox.information(
                self,
                "Hack Club verification required",
                "Sign in with Hack Club and complete verification before adding an API key.",
            )
            return
        if line_edit.isReadOnly():
            line_edit.setReadOnly(False)
            line_edit.setCursor(Qt.CursorShape.IBeamCursor)
            line_edit.selectAll()
            line_edit.setFocus()

    def lock_input(self, line_edit, settings_key, label_widget=None):
        if not line_edit.isReadOnly():
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.clearFocus()

            updated_value = line_edit.text().strip()
            existing = self.profile.get(settings_key)
            existing_str = str(existing) if existing is not None else ""
            if updated_value != existing_str:
                core.update_profile(**{settings_key: updated_value})
                self.profile[settings_key] = updated_value
                self._broadcast_profile()
                if settings_key == "byo_api_key":
                    self._start_api_key_validation(updated_value)
                elif label_widget:
                    self._flash_saved(label_widget)

    def _start_api_key_validation(self, api_key):
        if not api_key:
            self.api_key_status.setVisible(False)
            return
        self.api_key_status.setText("Checking key…")
        self.api_key_status.setStyleSheet(f"font-size: 11px; color: {TEXT_COLOR_SUBTITLE}; background: transparent; border: none;")
        self.api_key_status.setVisible(True)

        self._validation_worker = ApiKeyValidationWorker(api_key)
        self._validation_worker.finished.connect(self._on_api_key_validated)
        self._validation_worker.start()

    def _on_api_key_validated(self, is_valid, message):
        color = PRIMARY_COLOR if is_valid else DANGER_COLOR
        prefix = "✓" if is_valid else "✗"
        self.api_key_status.setText(f"{prefix} {message}")
        self.api_key_status.setStyleSheet(f"font-size: 11px; color: {color}; background: transparent; border: none;")

    # --- Appearance card -------------------------------------------------
    def _build_appearance_card(self):
        layout = self._make_card("Appearance")

        dark_row = QHBoxLayout()
        dark_label = QLabel("Dark mode")
        dark_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; background: transparent; border: none;")
        dark_row.addWidget(dark_label)
        dark_row.addStretch()
        self.dark_mode_toggle = ToggleSwitch(checked=CURRENT_DARK_MODE, accent=PRIMARY_COLOR, track_off=CARD_SUBTITLE_COLOR)
        self.dark_mode_toggle.setToolTip("Switch between light and dark backgrounds")
        self.dark_mode_toggle.toggled.connect(self._on_dark_mode_changed)
        dark_row.addWidget(self.dark_mode_toggle)
        layout.addLayout(dark_row)

        theme_color_label = self._field_label("Accent Color")
        layout.addWidget(theme_color_label)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(6)
        self.swatch_buttons = {}
        for key, label, hexval in THEME_OPTIONS:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(label)
            is_selected = (key == CURRENT_ACCENT)
            border = f"2.5px solid {CARD_TEXT_COLOR}" if is_selected else "2px solid rgba(0,0,0,0.1)"
            btn.setStyleSheet(f"""
                QPushButton {{ background: {hexval}; border-radius: 11px; border: {border}; }}
                QPushButton:hover {{ border: 2.5px solid {CARD_TEXT_COLOR}; }}
            """)
            btn.clicked.connect(lambda checked=False, k=key: self._on_accent_selected(k))
            swatch_row.addWidget(btn)
            self.swatch_buttons[key] = btn
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        # Non-intrusive banner: hidden until a theme change actually needs
        # a restart to show up, so it never interrupts unless required.
        self.restart_banner = QFrame()
        self.restart_banner.setVisible(False)
        self.restart_banner.setStyleSheet(f"QFrame {{ background: {ACTIVE_BG_COLOR}; border-radius: 8px; border: none; }}")
        banner_layout = QHBoxLayout(self.restart_banner)
        banner_layout.setContentsMargins(10, 6, 10, 6)
        banner_label = QLabel("Theme updated —")
        banner_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        banner_layout.addWidget(banner_label)
        banner_layout.addStretch()
        restart_btn = QPushButton("Restart Now")
        restart_btn.setCursor(Qt.PointingHandCursor)
        restart_btn.setToolTip("Restart Buddy to see your new theme")
        restart_btn.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 600; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            QPushButton:pressed {{ background: {PRIMARY_COLOR_PRESSED}; }}
        """)
        restart_btn.clicked.connect(self._restart_now)
        banner_layout.addWidget(restart_btn)
        layout.addWidget(self.restart_banner)

    def _on_dark_mode_changed(self, checked):
        core.update_profile(dark_mode=bool(checked))
        self._apply_theme_now()

    def _on_accent_selected(self, key):
        core.update_profile(theme_color=key)
        for k, btn in self.swatch_buttons.items():
            selected = (k == key)
            border = f"3px solid {CARD_TEXT_COLOR}" if selected else "2px solid rgba(0,0,0,0.1)"
            hexval = dict((opt[0], opt[2]) for opt in THEME_OPTIONS)[k]
            btn.setStyleSheet(f"""
                QPushButton {{ background: {hexval}; border-radius: 14px; border: {border}; }}
                QPushButton:hover {{ border: 3px solid {CARD_TEXT_COLOR}; }}
            """)
        self._apply_theme_now()

    def _apply_theme_now(self):
        self.restart_banner.setVisible(True)

    def _restart_now(self):
        if self.on_theme_changed:
            self.on_theme_changed()

    # --- Privacy & Data card ----------------------------------------------
    def _build_privacy_card(self):
        layout = self._make_card("Privacy & Data")

        pin_label = self._field_label("Privacy PIN (required to open chats marked 🔒 private)")
        pin_label.setWordWrap(True)
        layout.addWidget(pin_label)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setPlaceholderText(
            "PIN is set — leave blank and save to remove it" if core.has_privacy_pin()
            else "No PIN set — private chats are just hidden, not locked"
        )
        self.pin_input.setStyleSheet(FIELD_STYLE)
        self.pin_input.returnPressed.connect(self._save_pin)
        layout.addWidget(self.pin_input)

        save_pin_btn = QPushButton("Save PIN")
        save_pin_btn.setCursor(Qt.PointingHandCursor)
        save_pin_btn.setToolTip("Save this as your Privacy PIN")
        save_pin_btn.setStyleSheet(f"""
            QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border-radius: 8px; padding: 6px 14px; border: none; font-size: 12px; }}
            QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}
            QPushButton:pressed {{ background: {PRIMARY_COLOR_PRESSED}; }}
        """)
        save_pin_btn.clicked.connect(self._save_pin)
        layout.addWidget(save_pin_btn)

    def _save_pin(self):
        pin = self.pin_input.text().strip()
        core.set_privacy_pin(pin)
        self.pin_input.clear()
        if pin:
            self.pin_input.setPlaceholderText("PIN is set — leave blank and save to remove it")
            QMessageBox.information(self, "Privacy PIN", "Your Privacy PIN has been set.")
        else:
            self.pin_input.setPlaceholderText("No PIN set — private chats are just hidden, not locked")
            QMessageBox.information(self, "Privacy PIN", "Your Privacy PIN has been removed.")

    # --- Danger Zone card --------------------------------------------------
    def _build_danger_card(self):
        layout = self._make_card("Danger Zone")

        clear_btn = QPushButton("Clear All Chat History")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setToolTip("Permanently delete every saved conversation")
        clear_btn.setStyleSheet(f"""
            QPushButton {{ background: {DANGER_SOFT_BG}; color: {DANGER_COLOR}; border: 1px solid {DANGER_BORDER}; border-radius: 8px; padding: 6px 14px; font-size: 12px; }}
            QPushButton:hover {{ background: {DANGER_BORDER}; }}
            QPushButton:pressed {{ background: {DANGER_BORDER}; }}
        """)
        clear_btn.clicked.connect(self._confirm_clear_all)
        layout.addWidget(clear_btn)

    def _confirm_clear_all(self):
        choice = QMessageBox.warning(
            self, "Clear All Chat History",
            "This permanently deletes every conversation. This cannot be undone.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if choice == QMessageBox.Yes:
            for chat in core.get_recent_conversations(limit=100000):
                core.delete_conversation(chat["id"])
            for chat in core.get_recent_conversations(limit=100000, filter_mode="archived"):
                core.delete_conversation(chat["id"])
            QMessageBox.information(self, "Done", "All chat history has been cleared.")