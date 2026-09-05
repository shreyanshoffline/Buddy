"""First-run account and personalization wizard."""
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton,
    QStackedWidget, QWidget, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices

import core
import billing_client
from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    ON_PRIMARY_TEXT, BORDER_COLOR, INPUT_BG, HOVER_BG_COLOR, TEXT_COLOR_DARK,
    THEME_OPTIONS,
)


class OnboardingPage(CardPage):
    def __init__(self, parent=None, close_callback=None, on_complete=None):
        super().__init__("Welcome to Buddy", "Set up your account and preferences. Everything can be changed later in Settings.", parent, close_callback)
        self.on_complete = on_complete
        self.profile = core.get_profile()
        self.pages = QStackedWidget()
        self.main_layout.addWidget(self.pages)
        self._build_steps()
        self._build_navigation()

    def _label(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {CARD_SUBTITLE_COLOR}; font-size: 12px; background: transparent; border: none;")
        return label

    def _field(self, value, placeholder):
        field = QLineEdit(str(value or ""))
        field.setPlaceholderText(placeholder)
        field.setStyleSheet(f"QLineEdit {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 8px; color: {TEXT_COLOR_DARK}; }}")
        return field

    def _step(self, title, note):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 20px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(heading)
        layout.addWidget(self._label(note))
        return page, layout

    def _build_steps(self):
        page, layout = self._step("Create your account", "Choose a sign-in method. You can continue as a local Buddy profile if you prefer.")
        providers = QVBoxLayout()
        providers.setSpacing(8)
        for label, url in (("Sign in with Google", "https://accounts.google.com"), ("Sign in with Hack Club", None), ("Sign in with GitHub", "https://github.com/login")):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            if url:
                button.clicked.connect(lambda _, target=url: QDesktopServices.openUrl(QUrl(target)))
            else:
                button.clicked.connect(self._open_hackclub_signin)
            button.setMinimumHeight(34)
            providers.addWidget(button)
        layout.addLayout(providers)
        self.email = self._field(self.profile.get("email"), "Email address")
        layout.addWidget(self.email)
        self.account_note = self._label("Choose a sign-in provider or enter an email address to create a local account. The remaining steps are optional.")
        layout.addWidget(self.account_note)
        self.pages.addWidget(page)

        page, layout = self._step("About you", "Optional. This helps Buddy tailor replies to you.")
        self.name = self._field(self.profile.get("name"), "Your name")
        self.age = self._field(self.profile.get("age"), "Age")
        self.pin = self._field("", "4-digit privacy PIN (optional)")
        self.pin.setMaxLength(4)
        layout.addWidget(self.name)
        layout.addWidget(self.age)
        layout.addWidget(self.pin)
        self.pages.addWidget(page)

        page, layout = self._step("Your interests", "Optional. Add a little context so Buddy can make better suggestions.")
        self.bio = QTextEdit(self.profile.get("bio") or "")
        self.bio.setPlaceholderText("About you")
        self.favorite_apps = self._field(self.profile.get("favorite_apps"), "Favorite apps, separated by commas")
        self.quick_links = self._field(self.profile.get("quick_links"), "Quick links, for example GitHub: https://github.com")
        for field in (self.bio, self.favorite_apps, self.quick_links):
            field.setStyleSheet(f"QTextEdit, QLineEdit {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 8px; color: {TEXT_COLOR_DARK}; }}")
            layout.addWidget(field)
        self.pages.addWidget(page)

        page, layout = self._step("Appearance", "Optional. You can always change these choices later in Settings.")
        self.color = QComboBox()
        self.color.addItems([label for _, label, _ in THEME_OPTIONS])
        current = self.profile.get("theme_color", "blue")
        for index, (key, _, _) in enumerate(THEME_OPTIONS):
            if key == current:
                self.color.setCurrentIndex(index)
        self.dark = QComboBox()
        self.dark.addItems(["Light mode", "Dark mode"])
        self.dark.setCurrentIndex(1 if self.profile.get("dark_mode") else 0)
        layout.addWidget(self._label("Accent color"))
        layout.addWidget(self.color)
        layout.addWidget(self.dark)
        self.pages.addWidget(page)

    def _build_navigation(self):
        nav = QHBoxLayout()
        self.back = QPushButton("← Back")
        self.back.clicked.connect(lambda: self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1)))
        nav.addWidget(self.back)
        nav.addStretch()
        skip = QPushButton("Skip")
        skip.clicked.connect(self._finish)
        nav.addWidget(skip)
        self.next = QPushButton("Save and continue")
        self.next.setStyleSheet(f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 8px; padding: 8px 14px; font-weight: 600; }} QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}")
        self.next.clicked.connect(self._next)
        nav.addWidget(self.next)
        self.main_layout.addLayout(nav)
        self.pages.currentChanged.connect(self._update_navigation)
        self._update_navigation(0)

    def _open_hackclub_signin(self):
        try:
            billing_client.open_hackclub_signin()
        except billing_client.BillingNotConfigured as error:
            QMessageBox.warning(self, "Hack Club setup", str(error))

    def _save_current(self):
        index = self.pages.currentIndex()
        if index == 0:
            email = self.email.text().strip()
            if not email and not self.profile.get("auth_provider"):
                QMessageBox.warning(self, "Account details needed", "Choose a sign-in method or enter your email address before continuing.")
                return False
            provider = self.profile.get("auth_provider") or ("email" if email else None)
            core.update_profile(email=email, auth_provider=provider)
            self.profile["email"] = email
            self.profile["auth_provider"] = provider
        elif index == 1:
            age = self.age.text().strip()
            core.update_profile(name=self.name.text().strip(), age=int(age) if age.isdigit() else None)
            pin = self.pin.text().strip()
            if pin:
                if len(pin) != 4 or not pin.isdigit():
                    QMessageBox.warning(self, "PIN", "The optional PIN must be exactly 4 digits.")
                    return False
                core.set_privacy_pin(pin)
        elif index == 2:
            core.update_profile(bio=self.bio.toPlainText().strip(), favorite_apps=self.favorite_apps.text().strip(), quick_links=self.quick_links.text().strip())
        elif index == 3:
            key = THEME_OPTIONS[self.color.currentIndex()][0]
            core.update_profile(theme_color=key, dark_mode=self.dark.currentIndex() == 1)
        return True

    def _next(self):
        if not self._save_current():
            return
        if self.pages.currentIndex() == self.pages.count() - 1:
            self._finish()
        else:
            self.pages.setCurrentIndex(self.pages.currentIndex() + 1)

    def _finish(self):
        if not self._save_current() and self.pages.currentIndex() == 0:
            return
        core.update_profile(onboarding_complete=True)
        if self.on_complete:
            self.on_complete()

    def _update_navigation(self, index):
        self.back.setEnabled(index > 0)
        self.next.setText("Save and finish" if index == self.pages.count() - 1 else "Save and continue")
