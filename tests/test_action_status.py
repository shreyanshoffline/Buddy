import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "core" / "action_status.py"
spec = importlib.util.spec_from_file_location("buddy_action_status", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ActionStatusTests(unittest.TestCase):
    def test_lifecycle_and_retry_flag(self):
        store = mod.ActionStatusStore()
        store.start("a1", "Send message")
        self.assertEqual(store.get("a1").status, mod.WORKING)
        store.fail("a1", "offline")
        self.assertEqual(store.get("a1").status, mod.FAILED)
        self.assertTrue(store.get("a1").retryable)
        store.complete("a1", "ok")
        self.assertEqual(store.get("a1").status, mod.COMPLETE)
        store.cancel("a1")
        self.assertEqual(store.get("a1").status, mod.CANCELLED)

    def test_module_store_exists(self):
        self.assertTrue(hasattr(mod.STORE, "start"))


if __name__ == "__main__":
    unittest.main()
