"""Plugins — what Buddy can use on this Mac.

Toggles persist in the profile. Mac app rows check whether the .app exists.
Permission rows open the matching macOS Privacy & Security panel. macOS still
requires the user to approve Buddy there; a permission granted to Terminal or
VS Code is not automatically a permission granted to Buddy.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from core.plugins import load_plugins, save_plugins
from core.thinking import (
    LEVELS,
    LEVEL_LABELS,
    effective_thinking_level,
    listening_model,
    set_listening_model,
    set_speaking_model,
    set_thinking_level,
    should_auto_low,
    speaking_model,
    stored_thinking_level,
)
from .card_page import CardPage
from ..theme import (
    ACTIVE_BG_COLOR,
    BORDER_COLOR,
    CARD_SUBTITLE_COLOR,
    CARD_TEXT_COLOR,
    HOVER_BG_COLOR,
    INPUT_BG,
    ON_PRIMARY_TEXT,
    PRIMARY_COLOR,
    PRIMARY_COLOR_DARK,
    SECTION_CARD_BG,
    TEXT_COLOR_DARK,
    TEXT_COLOR_MUTED,
)
from ..widgets import ToggleSwitch

MAC_APPS = [
    ("messages", "Messages", [
        "/System/Applications/Messages.app",
        "/Applications/Messages.app",
    ]),
    ("slack", "Slack", ["/Applications/Slack.app"]),
    ("vscode", "VS Code", [
        "/Applications/Visual Studio Code.app",
        "/Applications/VS Code.app",
    ]),
    ("terminal", "Terminal", [
        "/System/Applications/Utilities/Terminal.app",
        "/Applications/Utilities/Terminal.app",
    ]),
    ("chrome", "Chrome", [
        "/Applications/Google Chrome.app",
        "/Applications/Chromium.app",
    ]),
]

MACOS_PRIVACY_PANELS = {
    "full_disk_access": (
        "Full Disk Access",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    ),
    "folder_access": (
        "Files & Folders",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_FilesAndFolders",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders",
    ),
    "microphone": (
        "Microphone",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Microphone",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    ),
    "camera": (
        "Camera",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Camera",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    ),
}


def _app_installed(paths):
    if sys.platform != "darwin":
        return False
    return any(Path(p).exists() for p in paths)


class PluginsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Plugins",
            "Choose what Buddy can use. Changes save immediately and apply to the next chat turn.",
            parent,
            close_callback,
        )
        self.plugins = load_plugins()
        self._website_rows = []
        self._system_switches = {}
        self._system_status_labels = {}
        self._build_thinking()
        self._build_voice()
        self._build_universal()
        self._build_apps()
        self._build_websites()
        self._build_system()
        self.main_layout.addStretch()

    def reload_from_db(self):
        self.plugins = load_plugins()
        if hasattr(self, "thinking_combo"):
            self.thinking_combo.blockSignals(True)
            self.thinking_combo.setCurrentText(LEVEL_LABELS[stored_thinking_level()])
            self.thinking_combo.blockSignals(False)
            self._refresh_thinking_note()
        if hasattr(self, "listen_combo"):
            self.listen_combo.blockSignals(True)
            self.listen_combo.setCurrentIndex(0 if listening_model() == "gemini" else 1)
            self.listen_combo.blockSignals(False)
        if hasattr(self, "speak_combo"):
            self.speak_combo.blockSignals(True)
            self.speak_combo.setCurrentIndex(0 if speaking_model() == "system" else 1)
            self.speak_combo.blockSignals(False)
        for key, switch in self._system_switches.items():
            switch.setChecked(bool(self.plugins["system"].get(key, False)))

    def _make_card(self, title, subtitle=None):
        card = QFrame()
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setStyleSheet(
            f"QFrame {{ background: {SECTION_CARD_BG}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 14px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {CARD_TEXT_COLOR}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(
                f"color: {CARD_SUBTITLE_COLOR}; font-size: 11px; "
                "background: transparent; border: none;"
            )
            layout.addWidget(subtitle_label)
        self.main_layout.addWidget(card)
        return layout

    def _section(self, eyebrow, title):
        heading = QLabel(f"{eyebrow}  ·  {title}")
        heading.setStyleSheet(
            f"color: {TEXT_COLOR_MUTED}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none; margin-top: 8px;"
        )
        self.main_layout.addWidget(heading)

    def _combo(self):
        combo = QComboBox()
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setCursor(Qt.PointingHandCursor)
        combo.setStyleSheet(
            f"QComboBox {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 8px; "
            "padding: 6px 10px; font-size: 11px; }}"
            f"QComboBox:hover {{ border: 1px solid {PRIMARY_COLOR}; }}"
            f"QComboBox QAbstractItemView {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; "
            f"selection-background-color: {ACTIVE_BG_COLOR}; }}"
        )
        return combo

    def _toggle_row(
        self, title, description, checked=False, enabled=True,
        status=None, status_key=None,
    ):
        row = QWidget()
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 4, 0, 4)
        row_layout.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        copy.addWidget(title_label)
        detail = QLabel(description)
        detail.setMinimumWidth(0)
        detail.setWordWrap(True)
        detail.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        copy.addWidget(detail)
        if status:
            status_label = QLabel(status)
            status_label.setStyleSheet(
                f"color: {PRIMARY_COLOR}; font-size: 9px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            copy.addWidget(status_label)
            if status_key:
                self._system_status_labels[status_key] = status_label
        row_layout.addLayout(copy, 1)
        switch = ToggleSwitch(checked=checked and enabled, accent=PRIMARY_COLOR)
        switch.setEnabled(enabled)
        switch.setToolTip(f"Toggle {title}")
        row_layout.addWidget(switch, 0, Qt.AlignVCenter)
        return row, switch

    def _build_thinking(self):
        self._section("CORE", "Thinking")
        layout = self._make_card(
            "Thinking level",
            "How hard Buddy works on the next reply. Medium is the default. "
            "A manual pick always wins over the free-tier Low suggestion.",
        )
        row = QHBoxLayout()
        label = QLabel("Default for new chats")
        label.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        row.addWidget(label)
        row.addStretch()
        self.thinking_combo = self._combo()
        for key in LEVELS:
            self.thinking_combo.addItem(LEVEL_LABELS[key], key)
        self.thinking_combo.setCurrentText(LEVEL_LABELS[stored_thinking_level()])
        self.thinking_combo.currentIndexChanged.connect(self._on_thinking)
        row.addWidget(self.thinking_combo)
        layout.addLayout(row)
        self.thinking_note = QLabel("")
        self.thinking_note.setWordWrap(True)
        self.thinking_note.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(self.thinking_note)
        self._refresh_thinking_note()

    def _refresh_thinking_note(self):
        effective = effective_thinking_level()
        stored = stored_thinking_level()
        if should_auto_low() and stored != "low":
            self.thinking_note.setText(
                "Credits look low on Free, so Buddy is running Low until you pick a level."
            )
        else:
            self.thinking_note.setText("Active level: %s." % LEVEL_LABELS[effective])

    def _on_thinking(self):
        set_thinking_level(self.thinking_combo.currentData(), manual=True)
        self._refresh_thinking_note()

    def _build_voice(self):
        self._section("CORE", "Voice")
        layout = self._make_card(
            "Talk engines",
            "Listening picks the speech-to-text path. Speaking picks system say or Inworld TTS.",
        )
        row = QVBoxLayout()
        row.setSpacing(8)
        listen_col = QVBoxLayout()
        listen_col.addWidget(self._mini("Listening"))
        self.listen_combo = self._combo()
        self.listen_combo.addItem("Gemini 2.5 Flash Lite", "gemini")
        self.listen_combo.addItem("Whisper (Hack Club AI)", "whisper")
        self.listen_combo.setCurrentIndex(0 if listening_model() == "gemini" else 1)
        self.listen_combo.currentIndexChanged.connect(
            lambda: set_listening_model(self.listen_combo.currentData())
        )
        listen_col.addWidget(self.listen_combo)
        speak_col = QVBoxLayout()
        speak_col.addWidget(self._mini("Speaking"))
        self.speak_combo = self._combo()
        self.speak_combo.addItem("System voice (macOS say)", "system")
        self.speak_combo.addItem("Inworld (Hack Club AI)", "inworld")
        self.speak_combo.setCurrentIndex(0 if speaking_model() == "system" else 1)
        self.speak_combo.currentIndexChanged.connect(
            lambda: set_speaking_model(self.speak_combo.currentData())
        )
        speak_col.addWidget(self.speak_combo)
        row.addLayout(listen_col, 1)
        row.addLayout(speak_col, 1)
        layout.addLayout(row)

    def _mini(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        return label

    def _build_universal(self):
        self._section("PLUGINS", "Universal")
        layout = self._make_card("Always available", "Tools that are not tied to one Mac app.")
        gmail_on = bool(self.plugins["universal"].get("gmail", True))
        gmail_row, gmail = self._toggle_row(
            "Gmail",
            "Read recent mail and write drafts with the connected Google account.",
            checked=gmail_on,
            status="Uses existing Gmail tools",
        )
        gmail.toggled.connect(lambda on: self._set_universal("gmail", on))
        layout.addWidget(gmail_row)

        search_on = bool(self.plugins["universal"].get("web_search", True))
        search_row, search = self._toggle_row(
            "Web search",
            "Look things up with Hack Club Search.",
            checked=search_on,
            status="Uses search.hackclub.com",
        )
        search.toggled.connect(lambda on: self._set_universal("web_search", on))
        layout.addWidget(search_row)

        weather_on = bool(self.plugins["universal"].get("weather", True))
        weather_row, weather = self._toggle_row(
            "Weather",
            "Get current conditions and today's forecast for a place you name.",
            checked=weather_on,
            status="Uses live Open-Meteo weather data",
        )
        weather.toggled.connect(lambda on: self._set_universal("weather", on))
        layout.addWidget(weather_row)

    def _set_universal(self, key, on):
        self.plugins["universal"][key] = bool(on)
        save_plugins(self.plugins)

    def _build_apps(self):
        self._section("PLUGINS", "Apps on this Mac")
        layout = self._make_card(
            "Mac apps",
            "Only installed apps can be turned on. Off means Buddy will not call that app's tools.",
        )
        shown = 0
        for key, label, paths in MAC_APPS:
            installed = _app_installed(paths)
            checked = bool(self.plugins["apps"].get(key, installed))
            if installed:
                shown += 1
                self.plugins["apps"].setdefault(key, True)
            row, switch = self._toggle_row(
                label,
                "Installed — Buddy can use the matching tools." if installed else "Not found on this Mac.",
                checked=checked,
                enabled=installed,
                status="Ready" if installed else "Missing",
            )
            switch.toggled.connect(lambda on, k=key: self._set_app(k, on))
            layout.addWidget(row)
        if shown == 0:
            note = QLabel("No matching apps were found. On a Mac, Buddy looks in /Applications.")
            note.setWordWrap(True)
            note.setStyleSheet(
                f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
            )
            layout.addWidget(note)
        save_plugins(self.plugins)

    def _set_app(self, key, on):
        self.plugins["apps"][key] = bool(on)
        save_plugins(self.plugins)

    def _build_websites(self):
        self._section("PLUGINS", "Websites")
        layout = self._make_card(
            "Website access",
            "If this list is empty, Buddy can open any URL. If you add sites, open_url is limited to those hosts.",
        )
        add_row = QHBoxLayout()
        self.website_input = QLineEdit()
        self.website_input.setMinimumWidth(0)
        self.website_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.website_input.setPlaceholderText("example.com")
        self.website_input.setStyleSheet(
            f"QLineEdit {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 8px; padding: 7px 9px; font-size: 11px; }}"
            f"QLineEdit:focus {{ border: 1px solid {PRIMARY_COLOR}; }}"
        )
        self.website_input.returnPressed.connect(self._add_website)
        add_row.addWidget(self.website_input, 1)
        add_button = QPushButton("Add")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_website)
        add_button.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; "
            "border-radius: 8px; padding: 7px 13px; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}"
        )
        add_row.addWidget(add_button)
        layout.addLayout(add_row)
        self.website_list = QVBoxLayout()
        self.website_list.setSpacing(4)
        layout.addLayout(self.website_list)
        for site in self.plugins.get("websites") or []:
            self._append_website(site, persist=False)

    def _normalize_website(self, value):
        return (value or "").strip().replace("https://", "").replace("http://", "").rstrip("/").lower()

    def _add_website(self):
        site = self._normalize_website(self.website_input.text())
        if not site or site in self._website_rows:
            return
        self._append_website(site, persist=True)
        self.website_input.clear()

    def _append_website(self, site, persist=True):
        self._website_rows.append(site)
        row = QFrame()
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.setStyleSheet(
            f"QFrame {{ background: {HOVER_BG_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(9, 4, 5, 4)
        label = QLabel(site)
        label.setMinimumWidth(0)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 11px; background: transparent; border: none;"
        )
        row_layout.addWidget(label, 1)
        remove = QPushButton("Remove")
        remove.setCursor(Qt.PointingHandCursor)
        remove.clicked.connect(lambda _checked=False, item=site, widget=row: self._remove_website(item, widget))
        remove.setStyleSheet(
            f"QPushButton {{ color: {CARD_SUBTITLE_COLOR}; background: transparent; border: none; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {PRIMARY_COLOR_DARK}; }}"
        )
        row_layout.addWidget(remove)
        self.website_list.addWidget(row)
        if persist:
            self.plugins["websites"] = list(self._website_rows)
            save_plugins(self.plugins)

    def _remove_website(self, site, widget):
        if site in self._website_rows:
            self._website_rows.remove(site)
        self.plugins["websites"] = list(self._website_rows)
        save_plugins(self.plugins)
        widget.deleteLater()

    def _build_system(self):
        self._section("PERMISSIONS", "System")
        layout = self._make_card(
            "Mac preferences",
            "Buddy's switch controls whether Buddy may use the feature. Permission rows open the exact macOS panel; turn Buddy on there too. Granting Terminal or VS Code access does not grant Buddy access.",
        )
        specs = (
            ("full_disk_access", "Full Disk Access", "Open macOS Full Disk Access and add the Buddy process that is actually running. If you run the source from Terminal, macOS may list Python or Terminal instead of a packaged Buddy app.", False),
            ("folder_access", "Files & Folders", "Open macOS Files & Folders so you can choose which protected locations Buddy may use.", False),
            ("microphone", "Microphone", "Open macOS Microphone permissions. Talk to Buddy stays blocked until macOS approves the running Buddy process.", True),
            ("camera", "Camera", "Open macOS Camera permissions for the running Buddy process.", False),
            ("power_controls", "Power controls", "Buddy-only safety gate for lock, sleep, and screensaver tools. macOS may still ask for authentication per action.", False),
        )
        for key, title, description, default in specs:
            checked = bool(self.plugins["system"].get(key, default))
            if key in MACOS_PRIVACY_PANELS:
                status = "Buddy gate · opens macOS settings"
            else:
                status = "Buddy gate"
            row, switch = self._toggle_row(
                title,
                description,
                checked=checked,
                status=status,
                status_key=key,
            )
            self._system_switches[key] = switch
            switch.toggled.connect(lambda on, k=key: self._set_system(k, on))
            layout.addWidget(row)

    def _set_system(self, key, on):
        self.plugins["system"][key] = bool(on)
        save_plugins(self.plugins)
        if on and key in MACOS_PRIVACY_PANELS:
            self._open_privacy_panel(key)
        status_label = self._system_status_labels.get(key)
        if status_label:
            if not on:
                status_label.setText("Buddy gate off")
            elif key in MACOS_PRIVACY_PANELS:
                status_label.setText("Buddy gate on · confirm access in macOS settings")
            else:
                status_label.setText("Buddy gate on")

    def _open_privacy_panel(self, key):
        if sys.platform != "darwin":
            return
        panel = MACOS_PRIVACY_PANELS.get(key)
        if not panel:
            return
        title, modern_url, legacy_url = panel
        opened = QDesktopServices.openUrl(QUrl(modern_url))
        if not opened:
            opened = QDesktopServices.openUrl(QUrl(legacy_url))
        if not opened:
            QMessageBox.warning(
                self,
                "Could not open macOS settings",
                f"Open System Settings > Privacy & Security > {title} manually, then enable Buddy.",
            )
