"""A transparent, local control panel for Buddy's long-term memory."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QInputDialog,
    QWidget,
)

from storage import db
from tools import lessons

from .card_page import CardPage
from ..theme import (
    ACTIVE_BG_COLOR,
    BORDER_COLOR,
    CARD_SUBTITLE_COLOR,
    CARD_TEXT_COLOR,
    DANGER_COLOR,
    DANGER_SOFT_BG,
    HOVER_BG_COLOR,
    INPUT_BG,
    ON_PRIMARY_TEXT,
    PRIMARY_COLOR,
    PRIMARY_COLOR_DARK,
    TEXT_COLOR_DARK,
    TEXT_COLOR_MUTED,
    TEXT_COLOR_SUBTITLE,
)
from ..widgets import ToggleSwitch


MEMORY_CATEGORIES = (
    ("relationships", "Relationships", "People, family, friends, and connections that matter to you."),
    ("work_patterns", "Work patterns", "How you like to work, your routines, and corrections Buddy should keep in mind."),
    ("preferences", "Preferences and choices", "Tools, formats, defaults, and everyday choices you have shared."),
    ("important", "Important to you", "Goals, values, priorities, and other details you explicitly want remembered."),
    ("communication", "Communication style", "How you like answers written, explained, and delivered."),
)
MEMORY_TITLES = {key: title for key, title, _ in MEMORY_CATEGORIES}


class MemoryPage(CardPage):
    """Show, edit, and disable the durable information Buddy can use."""

    def __init__(self, parent=None, close_callback=None):
        super().__init__(
            "Memory",
            "See and control what Buddy remembers about you.",
            parent,
            close_callback,
        )
        self._category_widgets = {}
        self._build_intro_card()
        for key, title, description in MEMORY_CATEGORIES:
            self._build_category_card(key, title, description)
        self.main_layout.addStretch()
        self.reload_from_db()

    def _label(self, text, color=CARD_SUBTITLE_COLOR, size=11, bold=False):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            f"color: {color}; font-size: {size}px; font-weight: {'600' if bold else 'normal'}; "
            "background: transparent; border: none;"
        )
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        label.setMinimumWidth(0)
        return label

    def _button(self, text, handler, danger=False):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if danger:
            button.setStyleSheet(
                f"QPushButton {{ color: {DANGER_COLOR}; background: transparent; border: none; padding: 4px 6px; }}"
                f"QPushButton:hover {{ background: {DANGER_SOFT_BG}; border-radius: 6px; }}"
            )
        else:
            button.setStyleSheet(
                f"QPushButton {{ color: {PRIMARY_COLOR}; background: transparent; border: none; padding: 4px 6px; }}"
                f"QPushButton:hover {{ background: {HOVER_BG_COLOR}; border-radius: 6px; }}"
            )
        button.clicked.connect(handler)
        return button

    def _build_intro_card(self):
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        card.setStyleSheet(
            f"QFrame {{ background: {ACTIVE_BG_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        layout.addWidget(self._label("Memory controls", color=CARD_TEXT_COLOR, size=13, bold=True))
        layout.addWidget(
            self._label(
                "Buddy keeps these memories locally on this device. Turn off a category to stop new memories there and stop using its existing entries in future replies. You can edit or remove anything below."
            )
        )
        self.memory_status = self._label("Loading memory…", color=TEXT_COLOR_MUTED, size=10)
        layout.addWidget(self.memory_status)
        self.main_layout.addWidget(card)

    def _build_category_card(self, key, title, description):
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        card.setStyleSheet(
            f"QFrame {{ background: {ACTIVE_BG_COLOR}; border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(7)

        header = QHBoxLayout()
        title_label = self._label(title, color=CARD_TEXT_COLOR, size=13, bold=True)
        header.addWidget(title_label, 1)
        toggle = ToggleSwitch(accent=PRIMARY_COLOR)
        toggle.setToolTip(f"Allow Buddy to use {title.lower()} memory")
        toggle.toggled.connect(lambda checked, category=key: self._set_category_enabled(category, checked))
        header.addWidget(toggle, 0, Qt.AlignTop)
        outer.addLayout(header)
        outer.addWidget(self._label(description, size=10))

        status = self._label("", color=TEXT_COLOR_MUTED, size=10)
        outer.addWidget(status)

        facts_host = QWidget()
        facts_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        facts_host.setMinimumWidth(0)
        facts_layout = QVBoxLayout(facts_host)
        facts_layout.setContentsMargins(0, 2, 0, 0)
        facts_layout.setSpacing(5)
        outer.addWidget(facts_host)

        add_button = self._button("+ Add memory", lambda _checked=False, category=key: self._add_fact(category))
        outer.addWidget(add_button, alignment=Qt.AlignLeft)
        self.main_layout.addWidget(card)
        self._category_widgets[key] = {
            "toggle": toggle,
            "status": status,
            "layout": facts_layout,
        }

    def _set_category_enabled(self, category, enabled):
        db.set_memory_preference(category, enabled)
        self.reload_from_db()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _entry_row(self, entry):
        row = QFrame()
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        row.setMinimumWidth(0)
        row.setStyleSheet(
            f"QFrame {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 9px; }}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 7, 6, 7)
        layout.setSpacing(4)

        kind = entry.get("kind")
        prefix = "Learned rule · " if kind == "lesson" else ""
        text = self._label(prefix + (entry.get("lesson") if kind == "lesson" else entry.get("content", "")), color=TEXT_COLOR_DARK, size=11)
        layout.addWidget(text, 1)
        edit = self._button("Edit", lambda _checked=False, item=entry: self._edit_entry(item))
        delete = self._button("Delete", lambda _checked=False, item=entry: self._delete_entry(item), danger=True)
        layout.addWidget(edit, 0, Qt.AlignTop)
        layout.addWidget(delete, 0, Qt.AlignTop)
        return row

    def reload_from_db(self):
        preferences = db.get_memory_preferences()
        facts = db.list_memory_facts(limit=500)
        entries = {key: [] for key, _title, _description in MEMORY_CATEGORIES}
        for fact in facts:
            category = db.normalize_memory_category(fact.get("category"))
            fact["kind"] = "fact"
            entries.setdefault(category, []).append(fact)
        # Lessons are the part of Buddy's memory that captures corrections,
        # prompt style, and work habits. Keep them visible under Work patterns.
        for lesson in lessons.list_lesson_items():
            lesson["kind"] = "lesson"
            entries["work_patterns"].append(lesson)

        total = sum(len(items) for items in entries.values())
        self.memory_status.setText(
            f"{total} saved item{'s' if total != 1 else ''}. Changes apply to future conversations."
        )
        for key, widgets in self._category_widgets.items():
            enabled = preferences.get(key, True)
            widgets["toggle"].setChecked(enabled)
            widgets["status"].setText(
                "On · Buddy can learn and use this category."
                if enabled
                else "Off · Buddy will not learn or use this category. Existing items remain here until deleted."
            )
            self._clear_layout(widgets["layout"])
            if not entries.get(key):
                widgets["layout"].addWidget(self._label("Nothing saved here yet.", color=TEXT_COLOR_MUTED, size=10))
                continue
            for entry in entries[key]:
                widgets["layout"].addWidget(self._entry_row(entry))

    def _add_fact(self, category):
        if not db.memory_category_enabled(category):
            QMessageBox.information(
                self,
                "Memory is off",
                f"Turn on {MEMORY_TITLES[category]} memory before adding a new item.",
            )
            return
        text, ok = QInputDialog.getMultiLineText(
            self,
            f"Add {MEMORY_TITLES[category]} memory",
            "What should Buddy remember?",
        )
        if ok and text.strip():
            db.save_memory_fact(text, category=category)
            self.reload_from_db()

    def _edit_entry(self, entry):
        old_text = entry.get("lesson") if entry.get("kind") == "lesson" else entry.get("content", "")
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Edit memory",
            "Update what Buddy should remember:",
            old_text,
        )
        if not ok or not text.strip() or text.strip() == old_text.strip():
            return
        if entry.get("kind") == "lesson":
            lessons.update_lesson(entry["number"], text)
        else:
            db.update_memory_fact(entry["id"], text)
        self.reload_from_db()

    def _delete_entry(self, entry):
        text = entry.get("lesson") if entry.get("kind") == "lesson" else entry.get("content", "")
        answer = QMessageBox.question(
            self,
            "Delete this memory?",
            f"Buddy will forget this permanently:\n\n{text}\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if entry.get("kind") == "lesson":
            lessons.delete_lesson(entry["number"])
        else:
            db.delete_memory_fact(entry["id"])
        self.reload_from_db()
