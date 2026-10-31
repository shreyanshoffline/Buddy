"""Plan switching and AI-key handling: regression tests for 'can't go back to Free' and
'Missing Authentication header' on a fresh install."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import models  # noqa: E402


class FakeOpenRouter:
    instances = []

    def __init__(self, api_key=None, server_url=None):
        self.api_key, self.server_url = api_key, server_url
        FakeOpenRouter.instances.append(self)


class ServerAndKeyTests(unittest.TestCase):
    def setUp(self):
        models._client_cache.update({"key": None, "client": None})
        FakeOpenRouter.instances.clear()
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for name in ("API_KEY", "SERVER_URL"):
            os.environ.pop(name, None)
        self.addCleanup(self.env.stop)

    def profile(self, **fields):
        return mock.patch("storage.db.get_profile", lambda: fields)

    def test_server_depends_on_the_key(self):
        self.assertEqual(models.server_url_for("sk-hc-v1-abc"), "https://ai.hackclub.com/proxy/v1")
        self.assertEqual(models.server_url_for("sk-or-v1-abc"), "https://openrouter.ai/api/v1")
        self.assertEqual(models.server_url_for(None), models.DEFAULT_SERVER_URL)

    def test_env_server_url_always_wins(self):
        os.environ["SERVER_URL"] = "https://example.test/v1"
        self.assertEqual(models.server_url_for("sk-or-x"), "https://example.test/v1")

    def test_fresh_install_with_no_key_says_what_to_do(self):
        with self.profile(), mock.patch.object(models, "OpenRouter", FakeOpenRouter):
            with self.assertRaises(models.ProviderConfigurationError) as ctx:
                models._get_openrouter_client()
        self.assertIn("ai.hackclub.com", str(ctx.exception))
        self.assertEqual(FakeOpenRouter.instances, [])       # no request was ever prepared without a key

    def test_saved_hack_club_key_goes_to_hack_club_ai(self):
        with self.profile(byo_api_key="  sk-hc-v1-mykey "), mock.patch.object(models, "OpenRouter", FakeOpenRouter):
            client = models._get_openrouter_client()
        self.assertEqual((client.api_key, client.server_url), ("sk-hc-v1-mykey", "https://ai.hackclub.com/proxy/v1"))

    def test_saved_openrouter_key_still_goes_to_openrouter(self):
        with self.profile(byo_api_key="sk-or-v1-mykey"), mock.patch.object(models, "OpenRouter", FakeOpenRouter):
            client = models._get_openrouter_client()
        self.assertEqual(client.server_url, "https://openrouter.ai/api/v1")

    def test_saved_key_beats_the_env_default(self):
        os.environ["API_KEY"] = "sk-hc-v1-shared"
        with self.profile(byo_api_key="sk-hc-v1-mine"), mock.patch.object(models, "OpenRouter", FakeOpenRouter):
            self.assertEqual(models._get_openrouter_client().api_key, "sk-hc-v1-mine")

    def test_provider_auth_errors_become_a_clear_message_and_are_not_retried(self):
        calls = []

        def fn():
            calls.append(1)
            raise RuntimeError("Status 401: Missing Authentication header")

        with self.assertRaises(models.ProviderConfigurationError) as ctx:
            models._with_retry(fn)
        self.assertEqual(len(calls), 1)
        self.assertIn("Settings > API Key", str(ctx.exception))
        self.assertNotIn("Missing Authentication header", str(ctx.exception))

    def test_other_errors_are_untouched(self):
        with self.assertRaises(RuntimeError) as ctx:
            models._with_retry(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(str(ctx.exception), "boom")

    def test_validate_key_outcomes(self):
        class Rejecting(FakeOpenRouter):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.chat = mock.Mock(send=mock.Mock(side_effect=RuntimeError("401 Missing Authentication header")))

        class RateLimited(FakeOpenRouter):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.chat = mock.Mock(send=mock.Mock(side_effect=RuntimeError("429 too many requests")))

        class Fine(FakeOpenRouter):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.chat = mock.Mock(send=mock.Mock(return_value={}))

        for cls, expected in ((Rejecting, False), (RateLimited, True), (Fine, True)):
            with mock.patch.object(models, "OpenRouter", cls):
                ok, message = models.validate_api_key("sk-hc-v1-x")
            self.assertEqual(ok, expected, message)
        self.assertEqual(models.validate_api_key("   ")[0], False)


class PlanSwitchingTests(unittest.TestCase):
    """Drives the real BillingPage: Free -> Hacky -> Free must work, and stay Free after a status refresh."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import core
        from PySide6.QtWidgets import QMessageBox
        self.core = core
        self.saved = {k: core.get_profile().get(k) for k in ("subscription_tier", "byo_api_key")}
        core.update_profile(subscription_tier="free", byo_api_key="")
        for name in ("information", "warning", "critical", "question"):
            patcher = mock.patch.object(QMessageBox, name, return_value=QMessageBox.StandardButton.Yes)
            patcher.start()
            self.addCleanup(patcher.stop)
        from backend import client as billing_client
        for name, value in (("fetch_subscription_tier", "free"), ("poll_hackclub_status", {})):
            patcher = mock.patch.object(billing_client, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        from gui.pages.billing_page import BillingPage
        self.page = BillingPage()
        self.addCleanup(self.page.deleteLater)

    def tearDown(self):
        self.core.update_profile(subscription_tier=self.saved["subscription_tier"] or "free",
                                 byo_api_key=self.saved["byo_api_key"] or "")

    def tier(self):
        return (self.core.get_profile().get("subscription_tier") or "free").lower()

    def test_hacky_then_back_to_free(self):
        page = self.page
        self.assertEqual(page.plan_detail_buttons["free"].text(), "Selected")
        page._finish_hacky_key_save("sk-hc-v1-test", True, "ok")
        self.assertEqual((page.selected_plan, self.tier()), ("hacky", "hacky"))
        # the Free page's button was built when Free was selected; it must not be stale
        self.assertEqual(page.plan_detail_buttons["free"].text(), "Select plan")
        page.plan_detail_buttons["free"].click()
        self.assertEqual((page.selected_plan, self.tier()), ("free", "free"))
        self.assertEqual(page.plan_detail_buttons["free"].text(), "Selected")

    def test_status_refresh_does_not_force_hacky_back(self):
        page = self.page
        page._finish_hacky_key_save("sk-hc-v1-test", True, "ok")
        page._select_plan("free")
        page._on_status_loaded("free")           # what the periodic/startup refresh does
        self.assertEqual((page.selected_plan, self.tier()), ("free", "free"))

    def test_saved_key_alone_never_switches_you_to_hacky(self):
        self.core.update_profile(byo_api_key="sk-hc-v1-test", subscription_tier="free")
        self.page._on_status_loaded("free")
        self.assertEqual(self.tier(), "free")

    def test_hacky_survives_a_refresh_when_it_was_chosen(self):
        self.page._finish_hacky_key_save("sk-hc-v1-test", True, "ok")
        self.page._on_status_loaded("free")
        self.assertEqual(self.tier(), "hacky")

    def test_bad_key_changes_nothing(self):
        self.page._finish_hacky_key_save("sk-hc-v1-bad", False, "That key was rejected.")
        self.assertEqual(self.tier(), "free")
        self.assertFalse(self.core.get_profile().get("byo_api_key"))

    def test_key_field_needs_no_oauth_sign_in(self):
        # on other people's computers the Hack Club sign-in backend has no secrets; the key must still be pasteable
        self.assertFalse(self.page.hacky_api_field.isHidden())
        self.assertFalse(self.page.hacky_api_save_button.isHidden())

    def test_empty_field_reuses_the_saved_key(self):
        self.core.update_profile(byo_api_key="sk-hc-v1-saved", subscription_tier="free")
        self.page._save_hacky_api_key()          # field is empty, key already saved -> switch to Hacky
        self.assertEqual(self.tier(), "hacky")


if __name__ == "__main__":
    unittest.main()
