"""Regression tests for the v0.9.8 fixes: token budget, tool relevance, compaction,
Notes/Calendar scripts, iMessage decoding, and final-answer formatting. All offline."""
import os
import sqlite3
import sys
import time
import types
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import budget, report
from tools.tools_schema import tools_schema


def _names(tools):
    return [t["function"]["name"] for t in tools]


class ToolRelevanceTests(unittest.TestCase):
    def test_full_schema_is_huge_selection_is_small(self):
        self.assertGreater(budget.est_tokens(tools_schema), 10_000)
        for prompt in ("make a new note called Groceries", "text my mom on iMessage",
                       "read my unread iMessages", "turn on dark mode", "what's the weather"):
            self.assertLess(budget.est_tokens(budget.select_tools(tools_schema, prompt)), 2500, prompt)

    def test_notes_request_gets_notes_tools_and_not_legacy_duplicate(self):
        names = _names(budget.select_tools(tools_schema, "can you make a new note in notes titled X"))
        self.assertIn("notes_create", names)
        self.assertNotIn("create_note", names)

    def test_calendar_typo_still_finds_calendar_tools(self):
        names = _names(budget.select_tools(tools_schema, "create a new calandar event on the 14th"))
        self.assertIn("apple_calendar_create_event", names)
        self.assertNotIn("create_calendar_event", names)

    def test_imessage_family_comes_together(self):
        names = _names(budget.select_tools(tools_schema, "reply on my way to my mom on iMessage"))
        for n in ("send_imessage", "lookup_contact_number", "get_unread_messages"):
            self.assertIn(n, names)

    def test_find_tools_lookup_and_signature(self):
        found = budget.select_tools(tools_schema, "spotify playlist", limit=budget.FIND_TOOLS_LIMIT, always=())
        self.assertTrue(any("spotify" in n for n in _names(found)))
        self.assertIn("notes_create(title", budget.tools_note(
            budget.select_tools(tools_schema, "make a note")))


class ResultAndHistoryTests(unittest.TestCase):
    def test_trim_result_keeps_head_and_tail(self):
        text = "A" * 20000 + "Z" * 2000
        out = budget.trim_result(text, limit=500)
        self.assertLess(len(out), 2300)
        self.assertTrue(out.startswith("A") and out.endswith("Z"))
        self.assertIn("trimmed", out)

    def _history(self, n):
        h = [{"role": "system", "content": "SYSTEM PROMPT"}]
        for i in range(n):
            h.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i} " + "word " * 300})
        return h

    def test_short_history_untouched(self):
        h = self._history(4)
        new, note = budget.compact_history(h, conversation_id="a", summarize=lambda t: "x")
        self.assertIs(new, h)
        self.assertIsNone(note)

    def test_long_history_is_compacted_and_recent_kept(self):
        budget._SUMMARY_CACHE.clear()
        h = self._history(20)
        calls = []
        new, note = budget.compact_history(h, conversation_id="c1", summarize=lambda t: calls.append(t) or "mom = Mama")
        self.assertIn("Compacted", note)
        self.assertEqual(new[0]["content"], "SYSTEM PROMPT")
        self.assertIn("mom = Mama", new[1]["content"])
        self.assertEqual(new[-budget.KEEP_RECENT:], h[-budget.KEEP_RECENT:])
        self.assertLess(budget.est_messages(new), budget.est_messages(h) / 2)

    def test_summary_is_incremental(self):
        budget._SUMMARY_CACHE.clear()
        seen = []
        h = self._history(20)
        budget.compact_history(h, conversation_id="c2", summarize=lambda t: seen.append(t) or "S1")
        h2 = h + [{"role": "user", "content": "extra " * 300}, {"role": "assistant", "content": "ok " * 300}]
        budget.compact_history(h2, conversation_id="c2", summarize=lambda t: seen.append(t) or "S2")
        self.assertIn("S1", seen[1])               # reuses the cached summary
        self.assertNotIn("message 0 ", seen[1])    # does not re-send what was already summarized

    def test_summarizer_failure_never_breaks_the_turn(self):
        budget._SUMMARY_CACHE.clear()
        def boom(_):
            raise RuntimeError("api down")
        new, note = budget.compact_history(self._history(20), conversation_id="c3", summarize=boom)
        self.assertIn("dropped", new[1]["content"])

    def test_budget_gate(self):
        msgs = [{"role": "user", "content": "x" * 40000}]
        self.assertFalse(budget.fits_budget(msgs, [], used=15000, cap=20000))
        self.assertTrue(budget.fits_budget(msgs[:0], [], used=100, cap=20000))


class ReportTests(unittest.TestCase):
    ROWS = [{"text": "dinner at 7?", "sender": "+1555", "chat_name": "Gaming GC", "timestamp": "2026-10-25T20:09:45"}]

    def test_unread_messages_are_shown(self):
        shown = report.format_for_user("get_unread_messages", self.ROWS)
        self.assertIn("Gaming GC", shown)
        self.assertIn("dinner at 7?", shown)

    def test_generic_summary_is_replaced_by_the_data(self):
        shown = report.format_for_user("get_unread_messages", self.ROWS)
        self.assertEqual(report.compose("Task successfully completed.", [("get_unread_messages", shown)]), shown)

    def test_real_summary_with_action_tool_untouched(self):
        self.assertEqual(report.compose("Sent it to Mama.", []), "Sent it to Mama.")
        self.assertIsNone(report.format_for_user("send_imessage", {"success": True}))


class AppleScriptGenerationTests(unittest.TestCase):
    def setUp(self):
        from tools import apple_tools
        self.apple = apple_tools
        self.scripts = []
        patcher = mock.patch.object(apple_tools, "_run_applescript",
                                    side_effect=lambda s, timeout=15: self.scripts.append(s) or "Home")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_notes_create_never_uses_default_folder(self):
        out = self.apple.notes_create("Haven Columbus Event")
        self.assertIn("Created note", out)
        self.assertNotIn("default folder", self.scripts[0])
        self.assertIn("<h1>Haven Columbus Event</h1>", self.scripts[0])

    def test_notes_escape_quotes_and_newlines(self):
        self.apple.notes_create('Say "hi"', "line1\nline2")
        self.assertIn("<br>", self.scripts[0])
        self.assertIn("&quot;hi&quot;", self.scripts[0])      # quotes can never break out of the AppleScript string
        self.assertNotIn('Say "hi"', self.scripts[0])

    def test_calendar_dates_are_built_from_numbers_not_locale_strings(self):
        out = self.apple.apple_calendar_create_event("Haven Columbus", "2026-11-14T07:00:00", "2026-11-14T20:00:00")
        script = self.scripts[0]
        self.assertIn("set year of startDate to 2026", script)
        self.assertIn("set month of startDate to 11", script)
        self.assertIn("set hours of endDate to 20", script)
        self.assertIn("whose writable is true", script)
        self.assertNotIn('date "', script)
        self.assertIn("Created", out)

    def test_calendar_rejects_bad_input_honestly(self):
        self.assertTrue(self.apple.apple_calendar_create_event("x", "tomorrow", "later").startswith("ERROR"))
        self.assertTrue(self.apple.apple_calendar_create_event("x", "2026-11-14T09:00", "2026-11-14T08:00").startswith("ERROR"))
        self.assertEqual(self.scripts, [])

    def test_terminal_cannot_script_native_apps(self):
        from tools import tools as t
        out = t.run_terminal_command("osascript -e 'tell application \"Calendar\" to make new event'")
        self.assertTrue(out.startswith("BLOCKED"))
        self.assertIn("apple_calendar_create_event", out)


class MessagesDecodeTests(unittest.TestCase):
    def blob(self, text):
        raw = text.encode()
        length = bytes([len(raw)]) if len(raw) < 0x80 else b"\x81" + len(raw).to_bytes(2, "little")
        return b"\x04\x0bstreamtyped\x84\x01@\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + length + raw + b"\x86\x84"

    def test_decoder(self):
        from tools import tools as t
        self.assertEqual(t._message_text_from_attributed_body(self.blob("hello")), "hello")
        self.assertEqual(t._message_text_from_attributed_body(self.blob("ok 👍")), "ok 👍")
        long = "y" * 300
        self.assertEqual(t._message_text_from_attributed_body(self.blob(long)), long)
        self.assertEqual(t._message_text_from_attributed_body(self.blob("\ufffc")), "[attachment]")

    def test_unread_reader_end_to_end(self):
        import tempfile
        from tools import tools as t
        home = tempfile.mkdtemp()
        os.makedirs(f"{home}/Library/Messages")
        con = sqlite3.connect(f"{home}/Library/Messages/chat.db")
        con.executescript("""
            CREATE TABLE message(ROWID INTEGER PRIMARY KEY, text, attributedBody, date, is_from_me, is_read,
                                 item_type, associated_message_type, handle_id);
            CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id);
            CREATE TABLE chat(ROWID INTEGER PRIMARY KEY, display_name, chat_identifier, style);
            CREATE TABLE chat_message_join(chat_id, message_id);
            INSERT INTO handle VALUES (1, '+15551234');
            INSERT INTO chat VALUES (1, 'Gaming GC', 'chat1', 43);
        """)
        now = int((time.time() - 978307200) * 1e9)
        old = int((time.time() - 90 * 86400 - 978307200) * 1e9)
        rows = [(1, None, self.blob("are we playing?"), now, 0, 0, 0, 0, 1),
                (2, "Liked a message", None, now, 0, 0, 0, 2000, 1),
                (3, "ancient", None, old, 0, 0, 0, 0, 1),
                (4, "plain text", None, now, 0, 0, 0, 0, 1)]
        con.executemany("INSERT INTO message VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO chat_message_join VALUES (1, ?)", [(i,) for i in (1, 2, 3, 4)])
        con.commit()
        con.close()
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):   # Windows reads USERPROFILE
            out = t.get_unread_messages()
        texts = sorted(r["text"] for r in out)
        self.assertEqual(texts, ["are we playing?", "plain text"])


class WorkerLoopTests(unittest.TestCase):
    """run_worker with a fake model: checks the schema it is offered, find_tools, the token cap,
    and that read results reach the final reply."""

    def _call(self, name, args, cid):
        return types.SimpleNamespace(id=cid, function=types.SimpleNamespace(name=name, arguments=__import__("json").dumps(args)))

    def _resp(self, content=None, calls=None):
        msg = types.SimpleNamespace(content=content, tool_calls=calls, images=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)],
                                     usage=types.SimpleNamespace(prompt_tokens=1000, completion_tokens=50))

    def _run(self, script, user_input, **kw):
        from core import agent
        seen = []

        def fake_step(model, history, max_tokens, schema, cancel_check=None, timeout_ms=None):
            seen.append(_names(schema))
            return script.pop(0)

        with mock.patch.object(agent, "run_action_step", fake_step), \
             mock.patch.object(agent, "active_tools_schema", lambda *a, **k: tools_schema), \
             mock.patch.object(agent.db, "get_profile", lambda: {}), \
             mock.patch.object(agent, "execute_tool", kw.pop("execute", lambda n, a: "ok")):
            return agent.run_worker("1. do it", "m", user_input=user_input, **kw), seen

    def test_worker_only_sees_relevant_tools(self):
        out, seen = self._run([self._resp(calls=[self._call("finish_task", {"summary": "done"}, "1")])],
                              "make a note titled X")
        self.assertLess(len(seen[0]), 25)
        self.assertIn("notes_create", seen[0])
        self.assertIn("find_tools", seen[0])
        self.assertNotIn("github_push", seen[0])

    def test_find_tools_loads_more(self):
        script = [self._resp(calls=[self._call("find_tools", {"query": "spotify playlist"}, "1")]),
                  self._resp(calls=[self._call("finish_task", {"summary": "ok"}, "2")])]
        out, seen = self._run(script, "make a note titled X")
        self.assertNotIn("play_spotify_playlist", seen[0])
        self.assertIn("play_spotify_playlist", seen[1])

    def test_read_result_replaces_bare_task_completed(self):
        rows = [{"text": "dinner at 7?", "sender": "+1555", "chat_name": "Gaming GC", "timestamp": "2026-10-25T20:09:45"}]
        script = [self._resp(calls=[self._call("get_unread_messages", {}, "1")]),
                  self._resp(calls=[self._call("finish_task", {"summary": "Task successfully completed."}, "2")])]
        out, _ = self._run(script, "read my unread imessages", execute=lambda n, a: rows)
        self.assertEqual(out["status"], "success")
        self.assertIn("dinner at 7?", out["summary"])
        self.assertNotEqual(out["summary"].strip(), "Task successfully completed.")

    def test_token_cap_stops_instead_of_burning_tokens(self):
        out, seen = self._run([self._resp(content="never reached")], "make a note", token_budget=10)
        self.assertEqual(out["status"], "incomplete")
        self.assertIn("token budget", out["message"])
        self.assertEqual(seen, [])

    def test_big_tool_output_is_trimmed_for_the_model_but_kept_in_the_log(self):
        big = "L" * 60000
        script = [self._resp(calls=[self._call("read_file_content", {"path": "x"}, "1")]),
                  self._resp(calls=[self._call("finish_task", {"summary": "read it"}, "2")])]
        out, _ = self._run(script, "read the file x", execute=lambda n, a: big)
        self.assertEqual(len(out["tool_log"][0]["result"]), 60000)


if __name__ == "__main__":
    unittest.main()
