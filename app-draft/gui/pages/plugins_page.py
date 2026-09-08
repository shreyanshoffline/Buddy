"""First-pass Buddy control center.

This page is intentionally UI-only for the draft. It gives the permissions
and integrations a clear home without pretending that macOS permissions or
plugin connections are already wired up.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QVBoxLayout, QWidget,
)

from .card_page import CardPage
from ..theme import (
    ACTIVE_BG_COLOR, BORDER_COLOR, CARD_SUBTITLE_COLOR, CARD_TEXT_COLOR,
    HOVER_BG_COLOR, INPUT_BG, ON_PRIMARY_TEXT, PRIMARY_COLOR,
    PRIMARY_COLOR_DARK, SECTION_CARD_BG, TEXT_COLOR_DARK, TEXT_COLOR_MUTED,
)
from ..widgets import ToggleSwitch


class PluginsPage(CardPage):
    """Manage what Buddy can use, see, and control on a Mac.

    The controls are local to this draft so the page can be reviewed without
    changing profile storage, macOS permissions, or the agent pipeline.
    """

    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Plugins",
            "Choose what Buddy can use, see, and control on your Mac.",
            parent,
            close_callback,
        )
        self._website_rows = []
        self._build_draft_banner()
        self._build_buddy_defaults()
        self._build_universal_section()
        self._build_apps_section()
        self._build_websites_section()
        self._build_system_section()
        self.main_layout.addStretch()

    # --- shared visual helpers -----------------------------------------
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

    def _toggle_row(self, title, description, checked=False, status=None):
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
        if status:
            status_label = QLabel(status)
            status_label.setStyleSheet(
                f"color: {PRIMARY_COLOR}; font-size: 9px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            copy.addWidget(status_label)
        row_layout.addLayout(copy, 1)

        switch = ToggleSwitch(checked=checked, accent=PRIMARY_COLOR)
        switch.setToolTip(f"Toggle {title}")
        row_layout.addWidget(switch, 0, Qt.AlignVCenter)
        return row, switch

    def _combo(self, values, current=0):
        combo = QComboBox()
        combo.addItems(values)
        combo.setCurrentIndex(current)
        combo.setCursor(Qt.PointingHandCursor)
        combo.setStyleSheet(
            f"QComboBox {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 8px; "
            "padding: 6px 10px; font-size: 11px; min-width: 150px; }}"
            f"QComboBox:hover {{ border: 1px solid {PRIMARY_COLOR}; }}"
            f"QComboBox QAbstractItemView {{ background: {INPUT_BG}; color: {TEXT_COLOR_DARK}; "
            f"selection-background-color: {ACTIVE_BG_COLOR}; }}"
        )
        return combo

    # --- draft sections -------------------------------------------------
    def _build_draft_banner(self):
        banner = QFrame()
        banner.setStyleSheet(
            f"QFrame {{ background: {ACTIVE_BG_COLOR}; border: 1px solid {BORDER_COLOR}; "
            "border-radius: 12px; }}"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel("Draft control center")
        label.setStyleSheet(
            f"color: {PRIMARY_COLOR_DARK}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(label)
        note = QLabel("These switches are a visual first pass. Nothing changes on your Mac yet.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {CARD_SUBTITLE_COLOR}; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(note, 1)
        self.main_layout.addWidget(banner)

    def _build_buddy_defaults(self):
        self._section_heading("Buddy defaults", "CORE")
        card, layout = self._make_card(
            "Thinking level",
            "Medium is the everyday default. Free users can still choose any level; Buddy may suggest Low when credits are running low.",
        )
        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        level_copy = QLabel("Default for new chats")
        level_copy.setStyleSheet(
            f"color: {TEXT_COLOR_DARK}; font-size: 11px; font-weight: 600; background: transparent; border: none;"
        )
        row.addWidget(level_copy)
        row.addStretch()
        self.thinking_combo = self._combo(["Low", "Medium", "High", "Extra", "MAX"], current=1)
        self.thinking_combo.setToolTip(
            "Medium is the average setting. You can always change it; Free may auto-suggest Low when credits are low."
        )
        row.addWidget(self.thinking_combo)
        layout.addLayout(row)

    def _build_universal_section(self):
        self._section_heading("Universal", "PLUGINS")
        card, layout = self._make_card(
            "Always available",
            "Services Buddy can use across the Mac, when you connect them.",
        )
        for title, description, checked in (
            ("Gmail", "Read, search, draft, and organize email with your approval.", True),
            ("Web search", "Look things up and bring useful sources into a chat.", True),
        ):
            row, _switch = self._toggle_row(title, description, checked=checked, status="Available in draft")
            layout.addWidget(row)

    def _build_apps_section(self):
        self._section_heading("Apps on this Mac", "PLUGINS")
        card, layout = self._make_card(
            "Mac apps",
            "Only apps installed on the user’s Mac should appear here in the finished version.",
        )
        filter_row, self.installed_only_switch = self._toggle_row(
            "Show installed apps only",
            "Hide apps that are not found on this Mac.",
            checked=True,
        )
        layout.addWidget(filter_row)

        for title, description in (
            ("Slack", "Read channels and help draft or send messages."),
            ("Messages", "Find conversations and draft texts for approval."),
            ("VS Code", "Open projects and work alongside you in the editor."),
            ("Terminal", "Run commands only when you explicitly approve them."),
            ("Chrome", "Open tabs, search, and work with websites."),
        ):
            row, _switch = self._toggle_row(title, description, checked=False, status="Waiting for app access")
            layout.addWidget(row)

    def _build_websites_section(self):
        self._section_heading("Websites", "PLUGINS")
        card, layout = self._make_card(
            "Website access",
            "Add trusted websites Buddy can work with. You can remove them at any time.",
        )
        add_row = QHBoxLayout()
        self.website_input = QLineEdit()
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
            f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 8px; "
            "padding: 7px 13px; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}"
        )
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        self.website_list = QVBoxLayout()
        self.website_list.setSpacing(4)
        layout.addLayout(self.website_list)
        for site in ("github.com", "docs.google.com"):
            self._append_website(site)

    def _normalize_website(self, value):
        return (value or "").strip().replace("https://", "").replace("http://", "").rstrip("/")

    def _add_website(self):
        site = self._normalize_website(self.website_input.text())
        if not site or site in self._website_rows:
            return
        self._append_website(site)
        self.website_input.clear()

    def _append_website(self, site):
        self._website_rows.append(site)
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {HOVER_BG_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(9, 4, 5, 4)
        label = QLabel(site)
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

    def _remove_website(self, site, widget):
        if site in self._website_rows:
            self._website_rows.remove(site)
        widget.deleteLater()

    def _build_system_section(self):
        self._section_heading("System", "PERMISSIONS")
        card, layout = self._make_card(
            "Mac permissions",
            "Sensitive controls stay off until the user turns them on and macOS grants access.",
        )
        permissions = (
            ("Full Disk Access", "Let Buddy work across protected files and folders.", False),
            ("Specific folders", "Choose a small set of folders instead of opening the whole disk.", False),
            ("Microphone", "Use the mic for Talk to Buddy voice chats.", True),
            ("Camera", "Allow Buddy to use the camera when a future feature needs it.", False),
            ("Power controls", "Allow sleep, restart, and shut down actions after confirmation.", False),
        )
        for title, description, checked in permissions:
            row, _switch = self._toggle_row(title, description, checked=checked, status="macOS permission required")
            layout.addWidget(row)
