"""User profile settings page — everything here is wired to a real backend:
- Display Name / Age / Bio personalize the actual system prompt Buddy uses.
- API Key overrides the app's default key for every model call, if set.
- Favorite Apps / Quick Links feed Buddy's "open my usual stuff" behavior.
- Privacy PIN gates opening any chat marked private.
- Clear All Chat History is a real, working destructive action.
"""
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Qt

import core
from .card_page import CardPage
from ..theme import CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR


FIELD_STYLE = """
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
"""


class SettingsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Settings", "Customize your assistant and preferences.", parent, close_callback)

        self.profile = core.get_profile()

        self.settings_config = {
            "name":         {"label": "Display Name", "placeholder": "What should Buddy call you?"},
            "age":          {"label": "Age", "placeholder": "Enter age..."},
            "email":        {"label": "Email Address", "placeholder": "Enter email..."},
            "bio":          {"label": "About You", "placeholder": "A few sentences about yourself..."},
            "favorite_apps": {"label": "Favorite Apps (comma-separated)", "placeholder": "e.g. Spotify, Chrome, Discord"},
            "quick_links":  {"label": "Quick Links (comma-separated, Name: URL)", "placeholder": "e.g. GitHub: https://github.com"},
            "byo_api_key":  {"label": "API Key (overrides the default)", "placeholder": "Enter your own OpenRouter API key..."},
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
            line_edit.setText(self.profile.get(key) or "")
            line_edit.setPlaceholderText(config["placeholder"])
            if key == "byo_api_key":
                line_edit.setEchoMode(QLineEdit.Password)
            line_edit.setReadOnly(True)
            line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            line_edit.setStyleSheet(FIELD_STYLE)

            line_edit.mousePressEvent = lambda event, le=line_edit: self.on_box_clicked(event, le)
            line_edit.returnPressed.connect(lambda le=line_edit, k=key: self.lock_input(le, k))
            line_edit.editingFinished.connect(lambda le=line_edit, k=key: self.lock_input(le, k))

            self.main_layout.addWidget(line_edit)
            self.inputs[key] = line_edit

        # --- Privacy PIN: separate handling since it's hashed, not stored as plain profile text ---
        privacy_label = QLabel("Privacy & Data")
        privacy_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 13px; font-weight: bold; background: transparent; margin-top: 14px;")
        self.main_layout.addWidget(privacy_label)

        pin_label = QLabel("Privacy PIN (required to open chats marked 🔒 private)")
        pin_label.setWordWrap(True)
        pin_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; font-weight: bold; background: transparent;")
        self.main_layout.addWidget(pin_label)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setPlaceholderText(
            "PIN is set — leave blank and save to remove it" if core.has_privacy_pin()
            else "No PIN set — private chats are just hidden, not locked"
        )
        self.pin_input.setStyleSheet(FIELD_STYLE)
        self.pin_input.returnPressed.connect(self._save_pin)
        self.main_layout.addWidget(self.pin_input)

        save_pin_btn = QPushButton("Save PIN")
        save_pin_btn.setCursor(Qt.PointingHandCursor)
        save_pin_btn.setStyleSheet("""
            QPushButton { background: #2b7ff0; color: white; border-radius: 6px; padding: 6px 14px; border: none; font-size: 12px; }
            QPushButton:hover { background: #1c6ad9; }
        """)
        save_pin_btn.clicked.connect(self._save_pin)
        self.main_layout.addWidget(save_pin_btn)

        # --- Clear all chat history: real, working, destructive action ---
        danger_label = QLabel("Danger Zone")
        danger_label.setStyleSheet(f"color: #c0392b; font-size: 13px; font-weight: bold; background: transparent; margin-top: 14px;")
        self.main_layout.addWidget(danger_label)

        clear_btn = QPushButton("Clear All Chat History")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton { background: #fdecea; color: #c0392b; border: 1px solid #f5c6cb; border-radius: 6px; padding: 6px 14px; font-size: 12px; }
            QPushButton:hover { background: #f8d7da; }
        """)
        clear_btn.clicked.connect(self._confirm_clear_all)
        self.main_layout.addWidget(clear_btn)

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

            updated_value = line_edit.text().strip()
            if updated_value != (self.profile.get(settings_key) or ""):
                core.update_profile(**{settings_key: updated_value})
                self.profile[settings_key] = updated_value

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
            QMessageBox.information(self, "Done", "All chat history has been cleared.")
