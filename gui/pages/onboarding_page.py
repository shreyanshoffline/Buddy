"""First-run account and personalization wizard."""
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton,
    QStackedWidget, QWidget, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal as QtSignal

import core
from backend import client as billing_client
from .card_page import CardPage
from ..theme import (
    CARD_TEXT_COLOR, CARD_SUBTITLE_COLOR, PRIMARY_COLOR, PRIMARY_COLOR_DARK,
    ON_PRIMARY_TEXT, BORDER_COLOR, INPUT_BG, HOVER_BG_COLOR, TEXT_COLOR_DARK,
    THEME_OPTIONS, combo_box_style,
)
from ..widgets import ModernComboBox


class _GoogleSignInWorker(QThread):
    done = QtSignal(dict)  # {"ok": bool, "email": str, "name": str, "error": str}

    def run(self):
        try:
            from tools import google_workspace_tools as gwt
            gwt._get_credentials()
            info = gwt.get_userinfo()
            core.set_plugin_connection("google", "connected", info.get("email"))
            self.done.emit({"ok": True, "email": info.get("email", ""), "name": info.get("name", "")})
        except Exception as e:
            self.done.emit({"ok": False, "error": str(e)})


class _MicrosoftSignInWorker(QThread):
    done = QtSignal(dict)

    def run(self):
        try:
            from tools import msgraph_tools as mst
            mst._get_token()
            info = mst.get_userinfo()
            email = info.get("mail") or info.get("userPrincipalName", "")
            core.set_plugin_connection("microsoft", "connected", email)
            self.done.emit({"ok": True, "email": email, "name": info.get("displayName", "")})
        except Exception as e:
            self.done.emit({"ok": False, "error": str(e)})


# Rounded, brand-tinted pill buttons instead of flat stock QPushButtons.
# icon_glyph is a short text/emoji placeholder — swap in a real QIcon(path)
# per provider once you drop official logo assets (from each brand's own
# press kit — Google/Microsoft/Apple all publish one) into GUI/assets/.
def _provider_button(text, icon_glyph, accent, text_color="#1a1a1a"):
    btn = QPushButton(f"  {icon_glyph}   {text}")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(46)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: #ffffff;
            color: {text_color};
            border: 2px solid {accent};
            border-radius: 23px;
            padding: 6px 18px;
            font-size: 13px;
            font-weight: 600;
            text-align: left;
        }}
        QPushButton:hover {{ background: {accent}; color: #ffffff; }}
        QPushButton:disabled {{ border-color: {BORDER_COLOR}; color: {CARD_SUBTITLE_COLOR}; background: {HOVER_BG_COLOR}; }}
    """)
    return btn


class OnboardingPage(CardPage):
    def __init__(self, parent=None, close_callback=None, on_complete=None):
        super().__init__("Hey! I'm Buddy 👋", "Let's get you set up — two minutes, tops. Everything here can change later in Settings.", parent, close_callback)
        self.on_complete = on_complete
        self.profile = core.get_profile()
        self.buddy_user_id = core.get_or_create_buddy_user_id()
        self.pages = QStackedWidget()
        self.main_layout.addWidget(self.pages)
        self._hackclub_poll_timer = QTimer(self)
        self._hackclub_poll_timer.timeout.connect(self._poll_hackclub_once)
        self._hackclub_poll_elapsed_ms = 0
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
        heading.setStyleSheet(f"color: {CARD_TEXT_COLOR}; font-size: 19px; font-weight: 800; background: transparent; border: none;")
        layout.addWidget(heading)
        layout.addWidget(self._label(note))
        return page, layout

    def _build_steps(self):
        page, layout = self._step("✨ Create your account", "Pick a sign-in method, or just go local — no pressure.")
        providers = QVBoxLayout()
        providers.setSpacing(10)

        self.hackclub_button = _provider_button("Sign in with Hack Club", "🚩", "#EC3750")
        self.hackclub_button.clicked.connect(self._open_hackclub_signin)
        providers.addWidget(self.hackclub_button)

        self.google_button = _provider_button("Sign in with Google", "🇬", "#4285F4")
        self.google_button.clicked.connect(self._on_google_button)
        providers.addWidget(self.google_button)

        self.microsoft_button = _provider_button("Sign in with Microsoft", "⊞", "#00A4EF")
        self.microsoft_button.clicked.connect(self._on_microsoft_button)
        providers.addWidget(self.microsoft_button)

        self.apple_button = _provider_button("Sign in with Apple", "", "#000000")
        self.apple_button.clicked.connect(self._on_apple_button)
        providers.addWidget(self.apple_button)

        layout.addLayout(providers)
        self.email = self._field(self.profile.get("email"), "Email address")
        layout.addWidget(self.email)
        self.account_note = self._label("Or just drop your email for a local profile — no account needed.")
        layout.addWidget(self.account_note)
        self.pages.addWidget(page)

        page, layout = self._step("👋 About you", "Optional. This helps Buddy tailor replies to you.")
        self.name = self._field(self.profile.get("name"), "Your name")
        self.age = self._field(self.profile.get("age"), "Age")
        layout.addWidget(self._label("Name is what Buddy calls you. Age is optional."))
        self.pin = self._field("", "Private-chat PIN, 4 digits — not your birth year")
        self.pin.setMaxLength(4)
        layout.addWidget(self.name)
        layout.addWidget(self.age)
        layout.addWidget(self.pin)
        layout.addWidget(self._label("PIN is only if you want locked chats. Leave it blank if you are not sure."))
        self.pages.addWidget(page)

        page, layout = self._step("🎯 Your interests", "Optional. Add a little context so Buddy can make better suggestions.")
        self.bio = QTextEdit(self.profile.get("bio") or "")
        self.bio.setPlaceholderText("About you")
        self.favorite_apps = self._field(self.profile.get("favorite_apps"), "Favorite apps, separated by commas")
        self.quick_links = self._field(self.profile.get("quick_links"), "Quick links, for example GitHub: https://github.com")
        for field in (self.bio, self.favorite_apps, self.quick_links):
            field.setStyleSheet(f"QTextEdit, QLineEdit {{ background: {INPUT_BG}; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 8px; color: {TEXT_COLOR_DARK}; }}")
            layout.addWidget(field)
        self.pages.addWidget(page)

        page, layout = self._step("🎨 Make it yours", "Optional. You can always change these choices later in Settings.")
        self.color = ModernComboBox()
        self.color.setCursor(Qt.PointingHandCursor)
        self.color.setStyleSheet(combo_box_style(font_size=11, padding="7px 10px"))
        self.color.addItems([label for _, label, _ in THEME_OPTIONS])
        current = self.profile.get("theme_color", "blue")
        for index, (key, _, _) in enumerate(THEME_OPTIONS):
            if key == current:
                self.color.setCurrentIndex(index)
        self.dark = ModernComboBox()
        self.dark.setCursor(Qt.PointingHandCursor)
        self.dark.setStyleSheet(combo_box_style(font_size=11, padding="7px 10px"))
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
        self.next.setStyleSheet(f"QPushButton {{ background: {PRIMARY_COLOR}; color: {ON_PRIMARY_TEXT}; border: none; border-radius: 20px; padding: 10px 20px; font-weight: 700; }} QPushButton:hover {{ background: {PRIMARY_COLOR_DARK}; }}")
        self.next.clicked.connect(self._next)
        nav.addWidget(self.next)
        self.main_layout.addLayout(nav)
        self.pages.currentChanged.connect(self._update_navigation)
        self._update_navigation(0)

    # --- Hack Club (existing, unchanged) ------------------------------------

    def _open_hackclub_signin(self):
        try:
            billing_client.open_hackclub_signin(self.buddy_user_id)
        except billing_client.BillingNotConfigured as error:
            QMessageBox.warning(self, "Hack Club setup", str(error))
            return
        self.hackclub_button.setText("  🚩   Waiting for Hack Club…")
        self.hackclub_button.setEnabled(False)
        self.account_note.setText("Finish sign-in in the browser, then return here. Buddy will pick it up automatically.")
        self._hackclub_poll_elapsed_ms = 0
        self._hackclub_poll_timer.start(2500)

    def _poll_hackclub_once(self):
        self._hackclub_poll_elapsed_ms += 2500
        if self._hackclub_poll_elapsed_ms >= 120_000:
            self._hackclub_poll_timer.stop()
            self.hackclub_button.setText("  🚩   Sign in with Hack Club")
            self.hackclub_button.setEnabled(True)
            self.account_note.setText("Sign-in timed out. Start the backend and try again.")
            return
        result = billing_client.poll_hackclub_status(self.buddy_user_id)
        if not result.get("signed_in"):
            return
        self._hackclub_poll_timer.stop()
        core.update_profile(
            email=result.get("email") or None,
            name=result.get("name") or None,
            auth_provider="hackclub",
            hackclub_verified=bool(result.get("verified")),
            hackclub_verification_status=result.get("verification_status"),
            hackclub_identity_id=result.get("identity_id"),
            hackclub_slack_id=result.get("slack_id"),
            hackclub_ysws_eligible=bool(result.get("ysws_eligible")),
        )
        self.profile = core.get_profile()
        if result.get("email"):
            self.email.setText(result["email"])
        if hasattr(self, "name") and result.get("name"):
            self.name.setText(result["name"])
        self.hackclub_button.setText("  🚩   Signed in with Hack Club")
        status = result.get("verification_status") or "signed in"
        self.account_note.setText(f"Hack Club connected ({status}). You can continue setup.")

    # --- Google ---------------------------------------------------------

    def _on_google_button(self):
        self.google_button.setEnabled(False)
        self.google_button.setText("  🇬   Connecting…")
        self._google_worker = _GoogleSignInWorker()
        self._google_worker.done.connect(self._on_google_done)
        self._google_worker.start()

    def _on_google_done(self, result):
        self.google_button.setEnabled(True)
        if not result.get("ok"):
            self.google_button.setText("  🇬   Sign in with Google")
            QMessageBox.warning(self, "Google sign-in", f"Couldn't sign in: {result.get('error')}")
            return
        self.google_button.setText(f"  🇬   Signed in as {result.get('email', 'Google')}")
        self.email.setText(result.get("email", ""))
        core.update_profile(email=result.get("email"), name=result.get("name") or None, auth_provider="google")
        self.profile = core.get_profile()
        self.account_note.setText("Google connected. You can continue setup.")

    # --- Microsoft --------------------------------------------------------

    def _on_microsoft_button(self):
        self.microsoft_button.setEnabled(False)
        self.microsoft_button.setText("  ⊞   Check the terminal for your code…")
        self._ms_worker = _MicrosoftSignInWorker()
        self._ms_worker.done.connect(self._on_microsoft_done)
        self._ms_worker.start()

    def _on_microsoft_done(self, result):
        self.microsoft_button.setEnabled(True)
        if not result.get("ok"):
            self.microsoft_button.setText("  ⊞   Sign in with Microsoft")
            QMessageBox.warning(self, "Microsoft sign-in", f"Couldn't sign in: {result.get('error')}")
            return
        self.microsoft_button.setText(f"  ⊞   Signed in as {result.get('email', 'Microsoft')}")
        self.email.setText(result.get("email", ""))
        core.update_profile(email=result.get("email"), name=result.get("name") or None, auth_provider="microsoft")
        self.profile = core.get_profile()
        self.account_note.setText("Microsoft connected. You can continue setup.")

    # --- Apple ------------------------------------------------------------

    def _on_apple_button(self):
        QMessageBox.information(
            self, "Sign in with Apple",
            "Not wired up yet — and not because of effort, because of a real requirement: "
            "Apple's sign-in flow refuses localhost or IP redirect URLs entirely. It needs a "
            "real HTTPS domain Buddy's backend is deployed to, plus a paid Apple Developer "
            "Program membership ($99/year — same fee whether or not you ever ship to the App "
            "Store). Once Buddy has a real domain for the backend, this becomes buildable.",
        )

    # --- Save / navigation (unchanged) -------------------------------------

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
        email = self.email.text().strip()
        age = self.age.text().strip()
        pin = self.pin.text().strip()
        if pin and (len(pin) != 4 or not pin.isdigit()):
            QMessageBox.warning(self, "PIN", "Leave the PIN blank, or use exactly 4 digits. It is not your birth year.")
            self.pages.setCurrentIndex(1)
            return
        core.update_profile(
            email=email or None,
            name=self.name.text().strip() or None,
            age=int(age) if age.isdigit() else None,
            auth_provider=self.profile.get("auth_provider") or ("email" if email else "local"),
            bio=self.bio.toPlainText().strip(),
            favorite_apps=self.favorite_apps.text().strip(),
            quick_links=self.quick_links.text().strip(),
            theme_color=THEME_OPTIONS[self.color.currentIndex()][0],
            dark_mode=self.dark.currentIndex() == 1,
            onboarding_complete=True,
        )
        if pin:
            core.set_privacy_pin(pin)
        if self.on_complete:
            self.on_complete()

    def _update_navigation(self, index):
        self.back.setEnabled(index > 0)
        self.next.setText("Save and finish" if index == self.pages.count() - 1 else "Save and continue")
