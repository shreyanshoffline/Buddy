"""Plugins — what Buddy can use on this Mac.

Toggles persist in the profile. Mac app rows check whether the .app exists.
Permission switches stay off until a probe of *this* process succeeds.
Gmail and GitHub show Connect / Connected / Not connected / Unavailable
from a real credential check.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal as QtSignal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox, QInputDialog, QLineEdit,
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
from tools import macos_permissions

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


def _app_installed(paths):
    if sys.platform != "darwin":
        return False
    return any(Path(p).exists() for p in paths)


class _GmailConnectWorker(QThread):
    connected = QtSignal(str)
    failed = QtSignal(str)

    def run(self):
        try:
            from tools import tools as tools_mod
            email = tools_mod.gmail_connect()
            self.connected.emit(email or "connected")
        except Exception as exc:
            self.failed.emit(str(exc))


class _GitHubDeviceWorker(QThread):
    connected = QtSignal(str)
    failed = QtSignal(str)

    def __init__(self, device_code, interval):
        super().__init__()
        self.device_code = device_code
        self.interval = interval
        self._cancelled = False

    def run(self):
        try:
            from tools import integrations
            import core
            token = integrations.github_poll_for_token(
                self.device_code, interval=self.interval, cancel_check=lambda: self._cancelled
            )
            username = integrations.github_whoami(token)
            core.set_plugin_connection("github", token, username)
            self.connected.emit(username)
        except Exception as exc:
            self.failed.emit(str(exc))


class PluginsPage(CardPage):
    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Plugins",
            "Choose what Buddy can use. A switch turns on only after this Buddy process is allowed.",
            parent,
            close_callback,
        )
        self.plugins = load_plugins()
        self._website_rows = []
        self._system_switches = {}
        self._system_status_labels = {}
        self._workers = []
        self._build_thinking()
        self._build_voice()
        self._build_universal()
        self._build_connections()
        self._build_apps()
        self._build_websites()
        self._build_system()
        self.main_layout.addStretch()
        QTimer.singleShot(200, self._refresh_system_probes)

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
        self._refresh_gmail_status()
        self._refresh_github_status()
        self._refresh_system_probes()

    def _make_card(self, title, subtitle=None):
        card = QFrame()
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card.setStyleSheet(
            f"QFrame {{ background: {SECTION_CARD_BG}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 14px; }"
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
            "padding: 6px 10px; font-size: 11px; }"
            f"QComboBox:hover {{ border: 1px solid {PRIMARY_COLOR}; }}"
            f"QComboBox QAbstractItemView {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; "
            f"selection-background-color: {ACTIVE_BG_COLOR}; }}"
        )
        return combo

    def _small_button(self, text):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {PRIMARY_COLOR}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 7px; padding: 4px 10px; font-size: 11px; font-weight: 600; }"
            f"QPushButton:hover {{ background: {HOVER_BG_COLOR}; }}"
        )
        return button

    def _toggle_row(self, title, description, checked=False, enabled=True, status=None, status_key=None):
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
            status_label.setWordWrap(True)
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
        switch.setToolTip("Toggle %s" % title)
        switch.setAccessibleName(title)
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

        gmail_row = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("Gmail")
        title.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        text_col.addWidget(title)
        self.gmail_status = QLabel("Not connected")
        self.gmail_status.setWordWrap(True)
        self.gmail_status.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        text_col.addWidget(self.gmail_status)
        gmail_row.addLayout(text_col, 1)
        self.gmail_button = self._small_button("Connect")
        self.gmail_button.clicked.connect(self._on_gmail_button)
        gmail_row.addWidget(self.gmail_button)
        layout.addLayout(gmail_row)
        self._refresh_gmail_status()

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

    def _gmail_snapshot(self):
        try:
            from tools import tools as tools_mod
            return tools_mod.gmail_connection_status()
        except Exception:
            return {"connected": False, "available": False}

    def _refresh_gmail_status(self):
        info = self._gmail_snapshot()
        connected = bool(info.get("connected"))
        available = info.get("available", True)
        if connected:
            self.plugins["universal"]["gmail"] = True
            save_plugins(self.plugins)
            email = info.get("email") or "connected account"
            self.gmail_status.setText("Connected as %s." % email)
            self.gmail_button.setText("Disconnect")
            self.gmail_button.setEnabled(True)
            return
        self.plugins["universal"]["gmail"] = False
        save_plugins(self.plugins)
        if not available:
            reason = "Unavailable"
            if not info.get("has_libraries", True):
                reason = "Unavailable — install google-api-python-client to enable Gmail."
            elif not info.get("has_credentials", True):
                reason = "Unavailable — add credentials.json next to Buddy's tools folder."
            self.gmail_status.setText(reason)
            self.gmail_button.setText("Unavailable")
            self.gmail_button.setEnabled(False)
            return
        self.gmail_status.setText("Not connected. Connect opens Google's official sign-in.")
        self.gmail_button.setText("Connect")
        self.gmail_button.setEnabled(True)

    def _on_gmail_button(self):
        info = self._gmail_snapshot()
        if info.get("connected"):
            try:
                from tools import tools as tools_mod
                tools_mod.gmail_disconnect()
            except Exception:
                pass
            self._refresh_gmail_status()
            return
        self.gmail_button.setEnabled(False)
        self.gmail_button.setText("Connecting…")
        worker = _GmailConnectWorker()
        worker.connected.connect(self._on_gmail_connected)
        worker.failed.connect(self._on_gmail_failed)
        self._workers.append(worker)
        worker.start()

    def _on_gmail_connected(self, email):
        self.gmail_button.setEnabled(True)
        self._refresh_gmail_status()
        self.gmail_status.setText("Connected as %s." % email)

    def _on_gmail_failed(self, message):
        self.gmail_button.setEnabled(True)
        self.gmail_button.setText("Connect")
        self.gmail_status.setText("Couldn't connect: %s" % message)

    def _build_connections(self):
        self._section("PLUGINS", "Connections")
        layout = self._make_card(
            "Outside accounts",
            "Connect only works after the provider confirms an account. Slack uses a verified token stored in Keychain.",
        )
        row = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("GitHub")
        title.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        text_col.addWidget(title)
        self.github_status = QLabel("Not connected")
        self.github_status.setWordWrap(True)
        self.github_status.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        text_col.addWidget(self.github_status)
        row.addLayout(text_col, 1)
        self.github_button = self._small_button("Connect")
        self.github_button.clicked.connect(self._on_github_button)
        row.addWidget(self.github_button)
        layout.addLayout(row)
        slack_row = QHBoxLayout()
        slack_col = QVBoxLayout()
        slack_col.setSpacing(2)
        slack_title = QLabel("Slack")
        slack_title.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        slack_col.addWidget(slack_title)
        self.slack_status = QLabel("Not connected")
        self.slack_status.setWordWrap(True)
        self.slack_status.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        slack_col.addWidget(self.slack_status)
        slack_row.addLayout(slack_col, 1)
        self.slack_button = self._small_button("Connect")
        self.slack_button.clicked.connect(self._on_slack_button)
        slack_row.addWidget(self.slack_button)
        layout.addLayout(slack_row)
        self._refresh_github_status()
        self._refresh_slack_status()

    def _refresh_github_status(self):
        try:
            import core
            conn = core.get_plugin_connection("github")
        except Exception:
            conn = None
        if conn:
            self.github_status.setText("Connected as %s." % (conn.get("account_label") or "GitHub user"))
            self.github_button.setText("Disconnect")
            self.github_button.setEnabled(True)
            return
        from tools import integrations
        if not integrations.GITHUB_CLIENT_ID:
            self.github_status.setText(
                "Unavailable — set BUDDY_GITHUB_CLIENT_ID for GitHub Device Flow."
            )
            self.github_button.setText("Unavailable")
            self.github_button.setEnabled(False)
            return
        self.github_status.setText("Not connected. Connect shows a GitHub device code.")
        self.github_button.setText("Connect")
        self.github_button.setEnabled(True)

    def _on_github_button(self):
        import core
        from tools import integrations
        if core.get_plugin_connection("github"):
            core.remove_plugin_connection("github")
            self._refresh_github_status()
            return
        self.github_button.setEnabled(False)
        try:
            data = integrations.github_start_device_flow()
        except Exception as exc:
            self.github_status.setText(str(exc))
            self.github_button.setEnabled(True)
            return
        user_code = data.get("user_code", "")
        verification_uri = data.get("verification_uri", "https://github.com/login/device")
        self.github_status.setText("Enter code %s at %s. Waiting for approval…" % (user_code, verification_uri))
        self.github_button.setText("Waiting…")
        QDesktopServices.openUrl(QUrl(verification_uri))
        worker = _GitHubDeviceWorker(data.get("device_code"), data.get("interval", 5))
        worker.connected.connect(lambda _name: self._refresh_github_status() or self.github_button.setEnabled(True))
        worker.failed.connect(self._on_github_failed)
        self._workers.append(worker)
        worker.start()

    def _on_github_failed(self, message):
        self.github_button.setEnabled(True)
        self.github_button.setText("Connect")
        self.github_status.setText("Couldn't connect: %s" % message)

    def _refresh_slack_status(self):
        try:
            import core
            connection = core.get_plugin_connection("slack")
        except Exception:
            connection = None
        if connection:
            self.slack_status.setText(
                "Connected as %s." % (connection.get("account_label") or "Slack account")
            )
            self.slack_button.setText("Disconnect")
            self.slack_button.setEnabled(True)
        else:
            self.slack_status.setText("Not connected. Add a Slack token to verify this workspace.")
            self.slack_button.setText("Connect")
            self.slack_button.setEnabled(True)

    def _on_slack_button(self):
        import core
        if core.get_plugin_connection("slack"):
            core.remove_plugin_connection("slack")
            self._refresh_slack_status()
            return

        token, ok = QInputDialog.getText(
            self,
            "Connect Slack",
            "Paste a Slack bot token. Buddy will verify it without sending a message:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not token.strip():
            return
        self.slack_button.setEnabled(False)
        self.slack_status.setText("Verifying Slack token...")
        try:
            from tools.integrations import slack_verify_token
            account_label = slack_verify_token(token.strip())
            core.set_plugin_connection("slack", token.strip(), account_label)
            self._refresh_slack_status()
        except Exception as exc:
            self.slack_button.setEnabled(True)
            self.slack_status.setText("Couldn't connect: %s" % exc)

    def _set_universal(self, key, on):
        self.plugins["universal"][key] = bool(on)
        save_plugins(self.plugins)

    def _build_apps(self):
        self._section("PLUGINS", "Apps on this Mac")
        layout = self._make_card(
            "Mac apps",
            "Found means the app is on this Mac. Off means Buddy will not call that app's tools.",
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
                status="Found" if installed else "Not found",
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
            "border-radius: 8px; padding: 7px 9px; font-size: 11px; }"
            f"QLineEdit:focus {{ border: 1px solid {PRIMARY_COLOR}; }}"
        )
        self.website_input.returnPressed.connect(self._add_website)
        add_row.addWidget(self.website_input, 1)
        add_button = QPushButton("Add")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_website)
        add_button.setStyleSheet(
            f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; "
            "border-radius: 8px; padding: 7px 13px; font-size: 11px; font-weight: 700; }"
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
        identity = macos_permissions.process_identity()
        warning = macos_permissions.identity_warning()
        subtitle = (
            "This process appears as %s. A switch cannot turn on until macOS grants that process access. "
            "Granting Terminal or VS Code does not grant Buddy."
        ) % identity
        if warning:
            subtitle = warning
        layout = self._make_card("Mac permissions", subtitle)
        specs = (
            ("full_disk_access", "Full Disk Access", "Lets Buddy search more of your disk after macOS grants this process."),
            ("folder_access", "Files & Folders", "Lets Buddy use folders you approve after macOS grants this process."),
            ("microphone", "Microphone", "Needed for Talk to Buddy. Buddy can hear you only after this process is approved."),
            ("camera", "Camera", "Not used by any Buddy feature yet. Leave this off."),
            ("power_controls", "Power controls", "Buddy-only safety gate for lock, sleep, and screensaver. No extra macOS pane."),
        )
        for key, title, description in specs:
            row, switch = self._toggle_row(
                title,
                description,
                checked=False,
                status="Off",
                status_key=key,
            )
            self._system_switches[key] = switch
            switch.toggled.connect(lambda on, k=key, s=switch: self._on_system_toggled(k, on, s))
            layout.addWidget(row)
        self.permission_help = QLabel(
            "Turn a permission off here to stop Buddy using it. To revoke the macOS grant, use System Settings > Privacy & Security."
        )
        self.permission_help.setWordWrap(True)
        self.permission_help.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(self.permission_help)

    def _on_system_toggled(self, key, on, switch):
        if not on:
            self.plugins["system"][key] = False
            save_plugins(self.plugins)
            self._set_system_status(key, "Off")
            return
        if key == "camera":
            switch.setChecked(False)
            self.plugins["system"][key] = False
            save_plugins(self.plugins)
            self._set_system_status(key, "Unavailable — not used by any feature")
            return
        if key == "power_controls":
            self.plugins["system"][key] = True
            save_plugins(self.plugins)
            self._set_system_status(key, "Granted")
            return
        switch.setChecked(False)
        self._set_system_status(key, "Waiting for macOS approval")
        macos_permissions.open_privacy_panel(key)
        QTimer.singleShot(1200, lambda k=key, s=switch: self._finish_permission_request(k, s))

    def _finish_permission_request(self, key, switch):
        granted = macos_permissions.probe(key)
        if granted:
            switch.setChecked(True)
            self.plugins["system"][key] = True
            save_plugins(self.plugins)
            self._set_system_status(key, "Granted for %s" % macos_permissions.process_identity())
            return
        switch.setChecked(False)
        self.plugins["system"][key] = False
        save_plugins(self.plugins)
        self._set_system_status(key, "Off — macOS did not grant this process")

    def _refresh_system_probes(self):
        for key, switch in self._system_switches.items():
            wanted = bool(self.plugins["system"].get(key, False))
            if key == "camera":
                switch.setChecked(False)
                self._set_system_status(key, "Unavailable — not used by any feature")
                continue
            if key == "power_controls":
                switch.setChecked(wanted)
                self._set_system_status(key, "Granted" if wanted else "Off")
                continue
            granted = macos_permissions.probe(key)
            on = bool(wanted and granted)
            if wanted and not granted:
                self.plugins["system"][key] = False
                save_plugins(self.plugins)
            switch.setChecked(on)
            if on:
                self._set_system_status(key, "Granted for %s" % macos_permissions.process_identity())
            elif wanted:
                self._set_system_status(key, "Off — macOS grant missing")
            else:
                self._set_system_status(key, "Off")

    def _set_system_status(self, key, text):
        label = self._system_status_labels.get(key)
        if label:
            label.setText(text)
