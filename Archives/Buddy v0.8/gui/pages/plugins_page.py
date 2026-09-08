"""Buddy's real plugin and permissions control center.

The page keeps user choices in the local Buddy profile. macOS privacy
permissions are deliberately handled by macOS: changing one opens the exact
System Settings pane instead of pretending Buddy can grant access itself.
"""
import os
import subprocess
import sys

from PySide6.QtCore import Qt, QThread, Signal, QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from storage import db

from .card_page import CardPage
from ..theme import (
    ACTIVE_BG_COLOR, BORDER_COLOR, CARD_SUBTITLE_COLOR, CARD_TEXT_COLOR,
    HOVER_BG_COLOR, INPUT_BG, ON_PRIMARY_TEXT, PRIMARY_COLOR,
    PRIMARY_COLOR_DARK, SECTION_CARD_BG, TEXT_COLOR_DARK, TEXT_COLOR_MUTED,
)
from ..widgets import ToggleSwitch


DEFAULT_PLUGIN_SETTINGS = {
    "gmail": True,
    "web_search": True,
    # Existing Buddy app tools stay available by default. Turning one off
    # below writes an explicit false and gates that tool until re-enabled.
    "app_slack": True,
    "app_messages": True,
    "app_vscode": True,
    "app_terminal": True,
    "app_chrome": True,
    "system_full_disk": False,
    "system_folders": False,
    "system_microphone": False,
    "system_camera": False,
    "system_accessibility": False,
    "system_power": False,
    "show_installed_only": True,
    "websites": ["github.com", "docs.google.com"],
}

APP_DEFINITIONS = (
    ("Slack", "app_slack", ("Slack",), "Read channels and help draft or send messages."),
    ("Messages", "app_messages", ("Messages",), "Find conversations and draft texts for approval."),
    ("VS Code", "app_vscode", ("Visual Studio Code", "Visual Studio Code - Insiders", "Code"), "Open projects and work alongside you in the editor."),
    ("Terminal", "app_terminal", ("Terminal",), "Run commands only when you explicitly approve them."),
    ("Chrome", "app_chrome", ("Google Chrome", "Chrome"), "Open tabs, search, and work with websites."),
)

SYSTEM_SETTINGS_URLS = {
    "full_disk": "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    "folders": "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders",
    "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
}


class AppDiscoveryWorker(QThread):
    """Find the supported Mac apps without blocking the Qt thread."""

    finished = Signal(list)

    def run(self):
        if sys.platform != "darwin":
            self.finished.emit([])
            return

        candidates = set()
        roots = ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]

        # Spotlight catches apps installed outside the usual folders.
        try:
            result = subprocess.run(
                ["/usr/bin/mdfind", "kMDItemContentType == 'com.apple.application-bundle'"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            candidates.update(result.stdout.splitlines())
        except (OSError, subprocess.SubprocessError):
            pass

        # The filesystem search is a fallback for a new or indexing-disabled Mac.
        if not candidates:
            try:
                result = subprocess.run(
                    ["/usr/bin/find", *roots, "-maxdepth", "3", "-name", "*.app", "-print"],
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                candidates.update(result.stdout.splitlines())
            except (OSError, subprocess.SubprocessError):
                pass

        names = {os.path.splitext(os.path.basename(path.strip()))[0].lower() for path in candidates if path.strip()}
        installed = []
        for title, _key, aliases, _description in APP_DEFINITIONS:
            if any(alias.lower() in names for alias in aliases):
                installed.append(title)
        self.finished.emit(installed)


class PluginsPage(CardPage):
    """Persistent integrations, app access, recommendations, and permissions."""

    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Plugins",
            "Choose what Buddy can use, see, and control on your Mac.",
            parent,
            close_callback,
        )
        self.settings = dict(DEFAULT_PLUGIN_SETTINGS)
        self.settings.update(db.get_plugin_settings() or {})
        self.preference_profile = db.get_preference_profile() or {}
        self.switches = {}
        self.status_labels = {}
        self.app_rows = {}
        self.installed_apps = set()
        self._website_rows = []
        self._app_discovery_worker = None

        self._build_draft_banner()
        self._build_preferences_section()
        self._build_buddy_defaults()
        self._build_universal_section()
        self._build_apps_section()
        self._build_websites_section()
        self._build_system_section()
        self.main_layout.addStretch()
        self.refresh_current_apps()

    # --- shared UI helpers --------------------------------------------
    def _make_card(self, title, subtitle=None):
        card = QFrame()
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
        return card, layout

    def _section_heading(self, title, eyebrow):
        heading = QLabel(f"{eyebrow}  ·  {title}")
        heading.setStyleSheet(
            f"color: {TEXT_COLOR_MUTED}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none; margin-top: 8px;"
        )
        self.main_layout.addWidget(heading)

    def _field_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        return label

    def _line_edit(self, placeholder=""):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setStyleSheet(
            f"QLineEdit {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 8px; padding: 7px 9px; font-size: 11px; }}"
            f"QLineEdit:focus {{ border: 1px solid {PRIMARY_COLOR}; }}"
        )
        return field

    def _combo(self, values, current=0):
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentIndex(max(0, current))
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

    def _toggle_row(self, title, description, checked=False, status=None, enabled=True):
        row = QWidget()
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
        detail.setWordWrap(True)
        detail.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; "
            "background: transparent; border: none;"
        )
        copy.addWidget(detail)
        status_label = None
        if status:
            status_label = QLabel(status)
            status_label.setStyleSheet(
                f"color: {PRIMARY_COLOR}; font-size: 9px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            copy.addWidget(status_label)
        row_layout.addLayout(copy, 1)

        switch = ToggleSwitch(checked=checked, accent=PRIMARY_COLOR)
        switch.setEnabled(enabled)
        switch.setToolTip(f"Toggle {title}")
        row_layout.addWidget(switch, 0, Qt.AlignVCenter)
        return row, switch, status_label

    def _button(self, text, callback, primary=False):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        if primary:
            button.setStyleSheet(
                f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 8px; "
                "padding: 7px 13px; font-size: 11px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {TEXT_COLOR_DARK}; border: 1px solid {BORDER_COLOR}; "
                "border-radius: 8px; padding: 7px 11px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {HOVER_BG_COLOR}; border-color: {PRIMARY_COLOR}; }}"
            )
        button.clicked.connect(callback)
        return button

    def _remember_switch(self, key, switch, status_label=None):
        self.switches[key] = switch
        if status_label is not None:
            self.status_labels[key] = status_label

    def _enabled(self, key, fallback=False):
        return bool(self.settings.get(key, fallback))

    def _save_setting(self, key, value):
        self.settings[key] = value
        db.update_plugin_settings(**{key: value})

    # --- top sections --------------------------------------------------
    def _build_draft_banner(self):
        banner = QFrame()
        banner.setStyleSheet(
            f"QFrame {{ background: {ACTIVE_BG_COLOR}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 12px; }}"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel("Live controls")
        label.setStyleSheet(
            f"color: {PRIMARY_COLOR_DARK}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(label)
        note = QLabel("Changes save to this Buddy install. macOS permissions open in System Settings for you to approve.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(note, 1)
        self.main_layout.addWidget(banner)

    def _build_preferences_section(self):
        self._section_heading("About you", "PERSONALIZE")
        card, layout = self._make_card(
            "Help Buddy recommend the right plugins",
            "Answer these quick questions. You can change them later, and Buddy will only use the answers to tailor this page.",
        )

        self.career_input = self._line_edit("e.g. student, designer, software engineer, musician")
        self.career_input.setText(self.preference_profile.get("career_or_hobby", ""))
        layout.addWidget(self._field_label("What do you do or spend time on?"))
        layout.addWidget(self.career_input)

        self.student_combo = self._combo(["Yes, I’m a student", "No, not right now", "Prefer not to say"])
        current_student = self.preference_profile.get("student_status", "")
        if current_student in ("yes", "no", "prefer_not_to_say"):
            self.student_combo.setCurrentIndex({"yes": 0, "no": 1, "prefer_not_to_say": 2}[current_student])
        layout.addWidget(self._field_label("Are you a student?"))
        layout.addWidget(self.student_combo)

        self.focus_input = self._line_edit("e.g. research, coding, communication, creative work")
        self.focus_input.setText(self.preference_profile.get("focus", ""))
        layout.addWidget(self._field_label("What should Buddy help with most?"))
        layout.addWidget(self.focus_input)

        actions = QHBoxLayout()
        self.recommendation_status = QLabel("")
        self.recommendation_status.setWordWrap(True)
        self.recommendation_status.setStyleSheet(
            f"color: {PRIMARY_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        actions.addWidget(self.recommendation_status, 1)
        actions.addWidget(self._button("Save answers", self._save_preferences, primary=True))
        actions.addWidget(self._button("Use recommendations", self._apply_recommendations))
        layout.addLayout(actions)

        self.recommendation_label = QLabel("")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(self.recommendation_label)
        self._show_recommendations()

    def _student_key(self):
        return ("yes", "no", "prefer_not_to_say")[self.student_combo.currentIndex()]

    def _recommendations(self):
        text = f"{self.career_input.text()} {self.focus_input.text()}".lower()
        student = self._student_key()
        recommendations = ["web_search", "gmail"]
        plugin_names = ["Web search", "Gmail"]

        if student == "yes":
            recommendations += ["app_chrome"]
            plugin_names.append("Chrome")
        if any(word in text for word in ("code", "coding", "developer", "program", "engineer", "software")):
            recommendations += ["app_vscode", "app_terminal"]
            plugin_names += ["VS Code", "Terminal"]
        if any(word in text for word in ("team", "work", "career", "startup", "community", "communication")):
            recommendations += ["app_slack"]
            plugin_names.append("Slack")
        if any(word in text for word in ("message", "family", "friend")):
            recommendations += ["app_messages"]
            plugin_names.append("Messages")
        return list(dict.fromkeys(recommendations)), list(dict.fromkeys(plugin_names))

    def _show_recommendations(self):
        _keys, names = self._recommendations()
        self.recommendation_label.setText("Suggested for you: " + ", ".join(names) + ".")

    def _save_preferences(self):
        profile = db.save_preference_profile(
            career_or_hobby=self.career_input.text().strip(),
            student_status=self._student_key(),
            focus=self.focus_input.text().strip(),
        )
        self.preference_profile = profile
        self._show_recommendations()
        self.recommendation_status.setText("Saved. Your recommendations are updated below.")

    def _apply_recommendations(self):
        keys, names = self._recommendations()
        for key in keys:
            self._save_setting(key, True)
            switch = self.switches.get(key)
            if switch is not None and not switch.isChecked():
                switch.setChecked(True)
            label = self.status_labels.get(key)
            if label is not None:
                label.setText("Enabled by recommendation")
        if self.installed_apps:
            self._render_app_rows()
        self.recommendation_status.setText("Enabled: " + ", ".join(names) + ".")

    def _build_buddy_defaults(self):
        self._section_heading("Buddy defaults", "CORE")
        card, layout = self._make_card(
            "Thinking level",
            "Medium is the everyday default. Free users can still choose any level; Buddy may suggest Low when credits are running low.",
        )
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        row.addWidget(QLabel("Default for new chats"))
        row.addStretch()
        levels = ["Low", "Medium", "High", "Extra", "MAX"]
        current = self.settings.get("thinking_level", "Medium")
        self.thinking_combo = self._combo(levels, levels.index(current) if current in levels else 1)
        self.thinking_combo.currentTextChanged.connect(lambda value: self._save_setting("thinking_level", value))
        row.addWidget(self.thinking_combo)
        layout.addLayout(row)

    def _build_universal_section(self):
        self._section_heading("Universal", "PLUGINS")
        card, layout = self._make_card(
            "Always available",
            "These controls gate the actual Buddy tools used for Gmail and live web search.",
        )
        for title, key, description in (
            ("Gmail", "gmail", "Read, search, draft, and organize email with your approval."),
            ("Web search", "web_search", "Search the live web and bring sources into a chat."),
        ):
            enabled = self._enabled(key, True)
            row, switch, status = self._toggle_row(title, description, checked=enabled, status="Enabled" if enabled else "Disabled")
            switch.toggled.connect(lambda value, k=key, label=status: self._on_plugin_toggle(k, value, label))
            self._remember_switch(key, switch, status)
            layout.addWidget(row)

    # --- installed applications ---------------------------------------
    def _build_apps_section(self):
        self._section_heading("Apps on this Mac", "PLUGINS")
        card, layout = self._make_card(
            "Mac apps",
            "Buddy searches Applications, System Applications, your user Applications folder, and Spotlight.",
        )
        controls = QHBoxLayout()
        self.installed_only_switch = ToggleSwitch(checked=self._enabled("show_installed_only", True), accent=PRIMARY_COLOR)
        self.installed_only_switch.toggled.connect(self._toggle_installed_filter)
        controls.addWidget(self.installed_only_switch)
        controls.addWidget(self._field_label("Show installed apps only"))
        controls.addStretch()
        self.refresh_apps_button = self._button("Refresh current apps", self.refresh_current_apps)
        controls.addWidget(self.refresh_apps_button)
        layout.addLayout(controls)

        self.apps_status_label = QLabel("Checking this Mac…")
        self.apps_status_label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(self.apps_status_label)
        self.apps_container = QVBoxLayout()
        self.apps_container.setSpacing(2)
        layout.addLayout(self.apps_container)

    def refresh_current_apps(self):
        if self._app_discovery_worker is not None and self._app_discovery_worker.isRunning():
            return
        self.refresh_apps_button.setEnabled(False)
        self.apps_status_label.setText("Searching for installed apps…")
        self._app_discovery_worker = AppDiscoveryWorker(self)
        self._app_discovery_worker.finished.connect(self._on_apps_discovered)
        self._app_discovery_worker.start()

    def _on_apps_discovered(self, installed):
        self.installed_apps = set(installed)
        self.refresh_apps_button.setEnabled(True)
        self.apps_status_label.setText(
            f"Found {len(installed)} of {len(APP_DEFINITIONS)} supported apps."
            if installed else "No supported apps found yet. Turn off the filter to see all supported plugins."
        )
        self._render_app_rows()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _render_app_rows(self):
        self._clear_layout(self.apps_container)
        self.app_rows.clear()
        show_installed_only = self.installed_only_switch.isChecked()
        visible = 0
        for title, key, _aliases, description in APP_DEFINITIONS:
            installed = title in self.installed_apps
            if show_installed_only and not installed:
                continue
            visible += 1
            enabled = installed and self._enabled(key, True)
            status_text = "Installed · enabled" if enabled else ("Installed · access off" if installed else "Not installed")
            row, switch, status = self._toggle_row(title, description, checked=enabled, status=status_text, enabled=installed)
            if installed:
                switch.toggled.connect(
                    lambda value, k=key, label=status: self._on_plugin_toggle(
                        k, value, label, permission_url=SYSTEM_SETTINGS_URLS["accessibility"]
                    )
                )
            self._remember_switch(key, switch, status)
            self.app_rows[key] = (title, row, switch, status)
            self.apps_container.addWidget(row)
        if visible == 0:
            empty = QLabel("No matching apps to show. Try turning off “Show installed apps only”.")
            empty.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none; padding: 4px;")
            self.apps_container.addWidget(empty)

    def _toggle_installed_filter(self, enabled):
        self._save_setting("show_installed_only", enabled)
        self._render_app_rows()

    # --- websites ------------------------------------------------------
    def _build_websites_section(self):
        self._section_heading("Websites", "PLUGINS")
        card, layout = self._make_card(
            "Website access",
            "Add trusted websites Buddy can work with. Changes are saved locally.",
        )
        add_row = QHBoxLayout()
        self.website_input = self._line_edit("example.com")
        self.website_input.returnPressed.connect(self._add_website)
        add_row.addWidget(self.website_input, 1)
        add_row.addWidget(self._button("Add website", self._add_website, primary=True))
        layout.addLayout(add_row)

        self.website_list = QVBoxLayout()
        self.website_list.setSpacing(4)
        layout.addLayout(self.website_list)
        sites = self.settings.get("websites", DEFAULT_PLUGIN_SETTINGS["websites"])
        for site in sites if isinstance(sites, list) else DEFAULT_PLUGIN_SETTINGS["websites"]:
            self._append_website(site)

    def _normalize_website(self, value):
        return (value or "").strip().replace("https://", "").replace("http://", "").rstrip("/")

    def _add_website(self):
        site = self._normalize_website(self.website_input.text())
        if not site or site in self._website_rows:
            return
        self._append_website(site)
        self.website_input.clear()
        self._save_setting("websites", list(self._website_rows))

    def _append_website(self, site):
        site = self._normalize_website(site)
        if not site or site in self._website_rows:
            return
        self._website_rows.append(site)
        row = QFrame()
        row.setStyleSheet(f"QFrame {{ background: {HOVER_BG_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(9, 4, 5, 4)
        label = QLabel(site)
        label.setStyleSheet(f"color: {TEXT_COLOR_DARK}; font-size: 11px; background: transparent; border: none;")
        row_layout.addWidget(label, 1)
        row_layout.addWidget(self._button("Remove", lambda _checked=False, item=site, widget=row: self._remove_website(item, widget)))
        self.website_list.addWidget(row)

    def _remove_website(self, site, widget):
        if site in self._website_rows:
            self._website_rows.remove(site)
        widget.deleteLater()
        self._save_setting("websites", list(self._website_rows))

    # --- permissions ---------------------------------------------------
    def _build_system_section(self):
        self._section_heading("System", "PERMISSIONS")
        card, layout = self._make_card(
            "Mac permissions",
            "Turning one of these on or off opens the matching macOS privacy pane. Buddy cannot approve the permission for you.",
        )
        permissions = (
            ("Full Disk Access", "Work across protected files and folders.", "system_full_disk", "full_disk"),
            ("Specific folders", "Choose limited folders instead of opening the whole disk.", "system_folders", "folders"),
            ("Microphone", "Use the mic for Talk to Buddy voice chats.", "system_microphone", "microphone"),
            ("Camera", "Allow Buddy to use the camera for future features.", "system_camera", "camera"),
            ("App control / Accessibility", "Control supported apps with clicks and keystrokes.", "system_accessibility", "accessibility"),
        )
        for title, description, key, url_key in permissions:
            enabled = self._enabled(key, False)
            row, switch, status = self._toggle_row(title, description, checked=enabled, status="Managed in System Settings" if enabled else "Off · click to open System Settings")
            switch.toggled.connect(lambda value, k=key, label=status, url=SYSTEM_SETTINGS_URLS[url_key]: self._on_permission_toggle(k, value, label, url))
            self._remember_switch(key, switch, status)
            layout.addWidget(row)

        enabled = self._enabled("system_power", False)
        row, switch, status = self._toggle_row(
            "Power controls",
            "Allow sleep, restart, and shut down actions after Buddy confirms with you.",
            checked=enabled,
            status="Enabled · Buddy still asks before power actions" if enabled else "Off",
        )
        switch.toggled.connect(lambda value, label=status: self._on_power_toggle(value, label))
        self._remember_switch("system_power", switch, status)
        layout.addWidget(row)

    # --- behavior ------------------------------------------------------
    def _on_plugin_toggle(self, key, enabled, status_label=None, permission_url=None):
        self._save_setting(key, enabled)
        if status_label is not None:
            status_label.setText("Enabled" if enabled else "Disabled")
        if permission_url:
            if status_label is not None:
                status_label.setText("Enabled · finish access in System Settings" if enabled else "Disabled · confirm in System Settings")
            self._open_system_settings(permission_url)

    def _on_permission_toggle(self, key, enabled, status_label, url):
        self._save_setting(key, enabled)
        status_label.setText("Requested · finish in System Settings" if enabled else "Turned off here · confirm in System Settings")
        self._open_system_settings(url)

    def _on_power_toggle(self, enabled, status_label):
        self._save_setting("system_power", enabled)
        status_label.setText("Enabled · Buddy still asks before power actions" if enabled else "Off")

    def _open_system_settings(self, url):
        if sys.platform == "darwin":
            if not QProcess.startDetached("/usr/bin/open", [url]):
                QDesktopServices.openUrl(QUrl(url))
            return
        QMessageBox.information(self, "macOS permission", "This permission link is available when Buddy is running on macOS.")
