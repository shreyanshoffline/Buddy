"""Regression tests for the pre-release fixes (Slack wiring, capabilities, packaging helpers, DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_every_schema_tool_has_an_implementation():
    """Slack tools were in the schema but missing from the dispatcher, so they never ran."""
    from core import agent
    from tools.tools_schema import tools_schema

    names = [tool["function"]["name"] for tool in tools_schema]
    missing = [n for n in names if not any(hasattr(m, n) for m in agent.TOOL_MODULES)]
    assert missing == []
    assert all(hasattr(agent.slack_tools, n) for n in ("slack_list_channels", "slack_recent_messages", "slack_send_message"))


def test_slack_errors_are_specific():
    from tools import slack_tools

    assert "invite" in slack_tools._explain("not_in_channel").lower()
    assert "Reconnect" in slack_tools._explain("invalid_auth")
    assert slack_tools._explain("weird_code") == "Slack error: weird_code"


def test_capabilities_guide_is_readable_and_honest():
    from tools import guides

    assert "capabilities" in guides.list_guides()
    text = guides.read_guide("capabilities", "Limits")
    assert "Cannot send email" in text and "schedule" in text


def test_manager_prompt_points_to_capabilities_guide():
    from core.instruction import build_manager_instruction

    assert 'read_guide("capabilities")' in build_manager_instruction({})


def test_permission_probes_do_not_touch_multimedia_off_macos(monkeypatch):
    from tools import macos_permissions as perms

    monkeypatch.setattr(perms, "is_macos", lambda: False)
    assert perms.probe("microphone") is False
    assert perms.probe("camera") is False


def test_python_executable_is_real_python_when_packaged(monkeypatch):
    import tools.paths as paths

    assert paths.python_executable() == sys.executable
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.is_packaged()
    assert "buddy" not in Path(paths.python_executable()).name.lower()


def test_attachments_roundtrip_without_holding_lock(tmp_path, monkeypatch):
    from storage import db

    monkeypatch.setattr(db, "_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(db, "_safe_embed", lambda texts: None)
    conv = db.create_conversation()
    ids = db.save_conversation_attachments(conv, None, [{"name": "a.txt", "extension": "txt", "contents": "hello world " * 400}])
    assert len(ids) == 1
    assert db.find_relevant_chunks(conv, "hello")
