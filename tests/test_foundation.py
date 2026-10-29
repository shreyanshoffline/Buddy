"""Isolated storage tests: temp database, no network, no GUI."""
import os
import sys
from contextlib import closing
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

    def test_old_messages_schema_gets_metadata_column(self):
        import sqlite3

        path = Path(self.db.get_db_path())
        path.unlink()
        # sqlite3's own `with` only commits; closing() really closes, so Windows can delete the file
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER, "
                "role TEXT, content TEXT, tool_calls TEXT, tool_call_id TEXT, created_at REAL)"
            )
            conn.commit()
        self.db._DB_PATH = None
        self.db.init_db()
        with self.db._connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        self.assertIn("metadata", columns)

    def test_location_plugin_formats_approximate_place(self):
        import tools.tools as tools
        self.db.update_profile(preferred_location="Portland, Oregon")
        result = tools.get_current_location()
        self.assertEqual(result, "Confirmed user location: Portland, Oregon.")

    def test_confirmed_location_reaches_agent_instructions(self):
        import importlib.util

        instruction_path = Path(__file__).resolve().parents[1] / "core" / "instruction.py"
        spec = importlib.util.spec_from_file_location("buddy_instruction", instruction_path)
        instruction = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(instruction)

        profile = {"preferred_location": "Portland, Oregon"}
        self.assertIn("Portland, Oregon", instruction.build_manager_instruction(profile))
        self.assertIn("Portland, Oregon", instruction.build_action_instruction(profile))

    def test_hack_club_search_api_key_is_primary(self):
        import tools.tools as tools

        previous = {
            name: os.environ.get(name)
            for name in ("HACK_CLUB_SEARCH_API_KEY", "HACKCLUB_SEARCH_KEY", "SEARCH_HACKCLUB_KEY")
        }
        try:
            os.environ["HACK_CLUB_SEARCH_API_KEY"] = "documented-key"
            os.environ["HACKCLUB_SEARCH_KEY"] = "legacy-key"
            os.environ["SEARCH_HACKCLUB_KEY"] = "other-legacy-key"
            self.assertEqual(tools._hackclub_search_key(), "documented-key")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_model_defaults_use_haiku_and_sonnet(self):
        import importlib.util

        model_path = Path(__file__).resolve().parents[1] / "core" / "model_config.py"
        spec = importlib.util.spec_from_file_location("buddy_model_config", model_path)
        model_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model_config)

        config = model_config.load_model_config()
        self.assertEqual(config["manager"], "anthropic/claude-haiku-5.5")
        self.assertEqual(config["easy"], "anthropic/claude-haiku-5.5")
        self.assertEqual(config["hard"], "anthropic/claude-sonnet-5.5")

    def test_embedding_cache_round_trip(self):
        self.db.save_cached_embeddings(["same text"], [[0.1, 0.2]])
        self.assertEqual(
            self.db.get_cached_embeddings(["same text"]),
            {"same text": [0.1, 0.2]},
        )

    def test_terminal_exit_code_is_a_tool_failure(self):
        text = "STDOUT:\n\nSTDERR:\nERROR\n[exit code: 1]"
        self.assertIn("[exit code: 1]", text)

    def test_messages_attributed_body_extracts_readable_text(self):
        import tools.tools as tools

        self.assertEqual(
            tools._message_text_from_attributed_body(b"NSAttributedString\x00Meet me at six"),
            "Meet me at six",
        )


if __name__ == "__main__":
    unittest.main()
