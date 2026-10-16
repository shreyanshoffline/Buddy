"""Tests for lessons, guides, schema generation, speech cleanup (no network, temp data dir)."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _lessons(tmp_path, monkeypatch):
    from tools import lessons
    monkeypatch.setattr(lessons, "_path", lambda: str(tmp_path / "lessons.json"))
    return lessons


def test_lessons_save_dedupe_recall_forget(tmp_path, monkeypatch):
    L = _lessons(tmp_path, monkeypatch)
    L.save_lesson("Post Hack Club updates in the #hackpad Slack channel", "slack")
    assert "Updated" in L.save_lesson("Post Hack Club updates in the #hackpad Slack channel.", "slack")
    L.save_lesson("Always answer in short sentences", "always")
    got = L._relevant("send a slack message about hack club")
    assert any("#hackpad" in g for g in got) and any("short sentences" in g for g in got)
    assert "Forgot" in L.forget_lesson(1)


def test_guides_outline_and_section():
    from tools import guides
    assert "slack" in guides.list_guides()
    assert "Sections" in guides.read_guide("slack")
    assert "xoxb" in guides.read_guide("slack", section="Connect")
    assert "No guide" in guides.read_guide("nonexistent")


def test_extra_schema_matches_functions():
    from tools.extra_schema import build_extra_schema
    names = {e["function"]["name"] for e in build_extra_schema()}
    assert {"web_open", "web_click", "save_lesson", "read_guide", "tasks_add", "excel_read_range"} <= names
    click = next(e for e in build_extra_schema() if e["function"]["name"] == "web_click")
    assert click["function"]["parameters"]["properties"]["ref"]["type"] == "integer"


def test_clean_for_speech():
    import voice_client
    out = voice_client.clean_for_speech("## Hi\n- **One** [link](http://a.b) `x`. Two. Three. Four.")
    assert "*" not in out and "http" not in out and "The rest is in the chat." in out


def test_alive_rejects_non_buddy_server(monkeypatch):
    from backend import client as b

    class R:
        ok = True
        status_code = 403
        def json(self): return {}
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: R())
    assert b._alive("http://127.0.0.1:5000") is False
