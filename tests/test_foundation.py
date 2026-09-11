"""Isolated storage tests: temp database, no network, no GUI."""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# storage.db imports models only for embeddings. Stub it so tests stay offline.
if "models" not in sys.modules:
    stub = types.ModuleType("models")
    stub.embed_texts = lambda texts: None
    sys.modules["models"] = stub
if "openrouter" not in sys.modules:
    sys.modules["openrouter"] = types.ModuleType("openrouter")
    sys.modules["openrouter"].OpenRouter = object


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "buddy.db")
        os.environ["BUDDY_DB_PATH"] = self.db_path
        import storage.db as db
        db._DB_PATH = None
        db.init_db()
        self.db = db

    def tearDown(self):
        self.db._DB_PATH = None
        self.tmp.cleanup()

    def test_profile_survives_missing_conversations_rebuild(self):
        self.db.update_profile(name="Ada")
        self.db.create_conversation(title="Keep me")
        report = self.db.check_schema()
        self.assertTrue(report["ok"])
        self.assertEqual(self.db.get_profile()["name"], "Ada")

    def test_corrupt_database_recovers_without_raising(self):
        path = Path(self.db.get_db_path())
        path.write_bytes(b"this is not sqlite")
        self.db._DB_PATH = None
        recovered = self.db.recover_database()
        self.assertTrue(recovered["recovered"])
        profile = self.db.get_profile()
        self.assertIn("subscription_tier", profile)

    def test_delete_conversation_does_not_wipe_profile(self):
        self.db.update_profile(name="Lin")
        conv_id = self.db.create_conversation(title="throwaway")
        self.db.delete_conversation(conv_id)
        self.assertEqual(self.db.get_profile()["name"], "Lin")


if __name__ == "__main__":
    unittest.main()
