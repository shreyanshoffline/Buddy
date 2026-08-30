"""User profile settings page (name/age/email/bio/API key)."""
from PySide6.QtWidgets import QLabel, QLineEdit
from PySide6.QtCore import Qt

import core
from .card_page import CardPage
from ..theme import CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR

class SettingsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Settings", "Customize your assistant and preferences.", parent, close_callback)

        self.profile = core.get_profile()

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
            line_edit.setText(self.profile.get(key) or "")
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

            updated_value = line_edit.text().strip()
            if updated_value != (self.profile.get(settings_key) or ""):
                core.update_profile(**{settings_key: updated_value})
                self.profile[settings_key] = updated_value
