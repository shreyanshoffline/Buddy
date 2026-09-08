"""Plugins — everything Buddy can see and touch, in one place.

Four sections:
- Universal: Gmail, web search.
- Apps on this Mac: only apps actually found on disk show up (real
  detection via os.path.exists, not a hardcoded list).
- Websites: specific domains Buddy is allowed to open, with read-only
  vs read/write access.
- System: Full Disk Access, folder access (a real folder picker), mic,
  camera, and power controls.

Every toggle here is a real, persisted preference (storage/db.py's
plugin_toggles / plugin_folders / plugin_websites tables) — but it's a
permission the USER has granted, not a live read of macOS's own TCC
permission database. Wiring tool execution to actually check these
flags is a follow-up revision, not this one.
"""
import os

from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QFrame,
    QFileDialog, QComboBox,
)
from PySide6.QtCore import Qt

import core
from .card_page import CardPage
from ..widgets import ToggleSwitch
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    PRIMARY_COLOR_PRESSED, ON_PRIMARY_TEXT, HOVER_BG_COLOR, PRESSED_BG_COLOR,
    BORDER_COLOR, INPUT_BG, SECTION_CARD_BG, TEXT_COLOR_SUBTITLE,
)

# key, label, candidate app-bundle paths, description shown to the user.
# Only apps whose bundle actually exists on disk are shown at all.
_APP_CANDIDATES = [
    ("app:slack", "Slack", ["/Applications/Slack.app"], "Read channels and send messages you approve."),
    ("app:messages", "Messages", ["/Applications/Messages.app", "/System/Applications/Messages.app"], "Send and read iMessages."),
    ("app:vscode", "VS Code", ["/Applications/Visual Studio Code.app"], "Open files and run tasks in your editor."),
    ("app:terminal", "Terminal", ["/Applications/Utilities/Terminal.app", "/System/Applications/Utilities/Terminal.app"], "Run commands you approve."),
    ("app:chrome", "Chrome", ["/Applications/Google Chrome.app"], "Open tabs and read what's on screen."),
]


def _detect_installed_apps():
    found = []
    for key, label, paths, desc in _APP_CANDIDATES:
        if any(os.path.exists(p) for p in paths):
            found.append((key, label, desc))
    return found


class PluginsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__("Plugins", "Everything Buddy can see and touch. Connect only what you need.", parent, close_callback)
        self._website_rows_layout = None
        self._folder_rows_layout = None

        self._build_universal_card()
        self._build_apps_card()
        self._build_websites_card()
        self._build_system_card()
        self.main_layout.addStretch()

    # --- shared helpers -----------------------------------------------
    def _make_card(self, title, subtitle=None):
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

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;")
            outer.addWidget(subtitle_label)

        self.main_layout.addWidget(card)
        return outer

    def _toggle_row(self, layout, key, title, description, default=False, on_toggle=None):
        row = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        text_col.addWidget(title_label)
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;")
            text_col.addWidget(desc_label)
        row.addLayout(text_col, 1)

        toggle = ToggleSwitch(checked=core.get_plugin_toggle(key, default), accent=PRIMARY_COLOR, track_off=CARD_SUBTITLE_COLOR)

        def _handle(checked, k=key):
            core.set_plugin_toggle(k, checked)
            if on_toggle:
                on_toggle(checked)

        toggle.toggled.connect(_handle)
        row.addWidget(toggle)
        layout.addLayout(row)
        return toggle

    def _small_button(self, text):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {PRIMARY_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 7px; padding: 4px 10px; font-size: 11px; font-weight: 600; }}
            QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}
            QPushButton:pressed {{ background: {PRESSED_BG_COLOR}; }}
        """)
        return btn

    # --- Universal card --------------------------------------------------
    def _build_universal_card(self):
        layout = self._make_card("Universal")
        self._toggle_row(layout, "gmail", "Gmail", "Read and send email on your behalf.")
        self._toggle_row(layout, "web_search", "Web search", "Look things up online when it helps.", default=True)

    # --- Apps card ---------------------------------------------------------
    def _build_apps_card(self):
        apps = _detect_installed_apps()
        layout = self._make_card(
            "Apps on this Mac",
            "Only apps Buddy finds on your Mac show up here." if apps else
            "Buddy didn't find any of its supported apps on this Mac yet.",
        )
        for key, label, desc in apps:
            self._toggle_row(layout, key, label, desc)

    # --- Websites card -----------------------------------------------------
    def _build_websites_card(self):
        layout = self._make_card("Websites", "Give Buddy access to specific sites it can't reach through an app.")

        self._website_rows_layout = QVBoxLayout()
        self._website_rows_layout.setSpacing(4)
        layout.addLayout(self._website_rows_layout)
        self._refresh_websites()

        add_row = QHBoxLayout()
        self.website_input = QLineEdit()
        self.website_input.setPlaceholderText("example.com")
        self.website_input.setStyleSheet(f"QLineEdit {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 6px 10px; font-size: 12px; color: {CARD_TEXT_COLOR}; }}")
        self.website_input.returnPressed.connect(self._add_website)
        add_row.addWidget(self.website_input, 1)
        self.website_access = QComboBox()
        self.website_access.addItem("Read only", "read")
        self.website_access.addItem("Read & write", "read_write")
        add_row.addWidget(self.website_access)
        add_btn = self._small_button("Add")
        add_btn.clicked.connect(self._add_website)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

    def _refresh_websites(self):
        while self._website_rows_layout.count():
            item = self._website_rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        sites = core.list_plugin_websites()
        if not sites:
            empty = QLabel("No websites added yet.")
            empty.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; background: transparent; border: none;")
            self._website_rows_layout.addWidget(empty)
            return

        for site in sites:
            row = QHBoxLayout()
            name = QLabel(site["domain"])
            name.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; background: transparent; border: none;")
            row.addWidget(name, 1)
            tag = QLabel("Read & write" if site["access"] == "read_write" else "Read only")
            tag.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
            row.addWidget(tag)
            remove = QPushButton("✕")
            remove.setCursor(Qt.PointingHandCursor)
            remove.setFixedSize(20, 20)
            remove.setStyleSheet("QPushButton { border: none; background: transparent; color: #9aa1ac; } QPushButton:hover { color: #d64545; }")
            remove.clicked.connect(lambda checked=False, site_id=site["id"]: self._remove_website(site_id))
            row.addWidget(remove)
            self._website_rows_layout.addLayout(row)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_website(self):
        domain = self.website_input.text().strip()
        if not domain:
            return
        access = self.website_access.currentData() or "read"
        core.add_plugin_website(domain, access)
        self.website_input.clear()
        self._refresh_websites()

    def _remove_website(self, site_id):
        core.remove_plugin_website(site_id)
        self._refresh_websites()

    # --- System card -----------------------------------------------------
    def _build_system_card(self):
        layout = self._make_card("System")
        self._toggle_row(layout, "system:full_disk", "Full Disk Access", "Needed to search files across your whole Mac.")

        folder_row = QHBoxLayout()
        folder_label = QLabel("Folder access")
        folder_label.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        folder_row.addWidget(folder_label, 1)
        manage_btn = self._small_button("Manage folders")
        manage_btn.clicked.connect(self._pick_folder)
        folder_row.addWidget(manage_btn)
        layout.addLayout(folder_row)

        self._folder_rows_layout = QVBoxLayout()
        self._folder_rows_layout.setSpacing(4)
        layout.addLayout(self._folder_rows_layout)
        self._refresh_folders()

        self._toggle_row(layout, "system:mic", "Microphone", "Needed for voice mode.", default=True)
        self._toggle_row(layout, "system:camera", "Camera", "Not currently used by any feature.")
        self._toggle_row(layout, "system:power", "Power controls", "Let Buddy sleep, restart, or shut down your Mac when you ask.")

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Give Buddy access to a folder")
        if path:
            core.add_plugin_folder(path)
            self._refresh_folders()

    def _refresh_folders(self):
        while self._folder_rows_layout.count():
            item = self._folder_rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        folders = core.list_plugin_folders()
        if not folders:
            empty = QLabel("No folders added — Buddy can only see what full disk access or individual apps allow.")
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;")
            self._folder_rows_layout.addWidget(empty)
            return

        for folder in folders:
            row = QHBoxLayout()
            name = QLabel(folder["path"])
            name.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 11px; background: transparent; border: none;")
            name.setWordWrap(True)
            row.addWidget(name, 1)
            remove = QPushButton("✕")
            remove.setCursor(Qt.PointingHandCursor)
            remove.setFixedSize(20, 20)
            remove.setStyleSheet("QPushButton { border: none; background: transparent; color: #9aa1ac; } QPushButton:hover { color: #d64545; }")
            remove.clicked.connect(lambda checked=False, folder_id=folder["id"]: self._remove_folder(folder_id))
            row.addWidget(remove)
            self._folder_rows_layout.addLayout(row)

    def _remove_folder(self, folder_id):
        core.remove_plugin_folder(folder_id)
        self._refresh_folders()
