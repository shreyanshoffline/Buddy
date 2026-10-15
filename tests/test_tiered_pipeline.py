"""Through the real process_message: tiered manager plans, coding mode, and the long-form essay route."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core  # noqa: E402
import core.agent as agent  # noqa: E402
from storage import db  # noqa: E402


def _resp(*calls, text="", t_in=80, t_out=40):
    msg = NS(tool_calls=list(calls) or None, content=text)
    return NS(choices=[NS(message=msg, finish_reason="stop")], usage=NS(prompt_tokens=t_in, completion_tokens=t_out))


def _call(i, tool, **args):
    return NS(id="c%d" % i, function=NS(name=tool, arguments=json.dumps(args)))


def _tier(history):
    sys_prompt = history[0]["content"]
    return next((t for t in ("easy", "medium", "heavy") if "the %s worker" % t.upper() in sys_prompt), "other")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    import core.plugins as plugins
    enabled = plugins.default_plugins()
    enabled["system"]["folder_access"] = True
    monkeypatch.setattr(plugins, "load_plugins", lambda: enabled)


def test_manager_plan_with_tier_tags_runs_each_step_on_its_tier(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    plan = ("PLAN: [moderate_task]\n1. [easy_task] Open the Notes app.\n"
            "2. [heavy_task] Write a 300 word summary of how volcanoes form.\n3. [medium_task] Save the summary to a note.")
    monkeypatch.setattr(agent, "route_first_pass", lambda *a, **k: ("action", "", None))
    monkeypatch.setattr(agent, "get_manager_output", lambda *a, **k: (plan, None))
    queues = {"easy": [_resp(_call(1, "finish_task", summary="Notes is open."))],
              "heavy": [_resp(text="Volcanoes form where magma rises through the crust...")],
              "medium": [_resp(_call(2, "finish_task", summary="Saved to a new note."))]}
    seen = []

    def step(model, history, max_tokens, tools, cancel_check=None, timeout_ms=None):
        t = _tier(history)
        seen.append((t, model, max_tokens))
        return queues[t].pop(0)

    monkeypatch.setattr(agent, "run_action_step", step)
    monkeypatch.setattr(agent, "execute_tool", lambda n, a: "ok")
    events = []
    out = agent.process_message_incognito("write a summary of volcanoes and save it to notes", core.new_message_history(),
                                          on_event=events.append)
    assert [s[0] for s in seen] == ["easy", "heavy", "medium"]
    assert seen[1][1].endswith("sonnet-5.5") and seen[0][1].endswith("haiku-5.5")             # heavy only for the writing
    assert "Volcanoes form where magma rises" in out["reply"] and "Saved to a new note." in out["reply"]
    assert out["stats"]["Calls by tier"] == "Easy×1, Medium×1, Heavy×1"
    assert "Plan (by tier)" in out["plan_text"] and "[Heavy]" in out["plan_text"]
    assert [e["type"] for e in events if e["type"] in ("step_start", "step_done")].count("step_start") == 3


def test_coding_request_plans_then_stages(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    plan = json.dumps({"steps": [
        {"tier": "easy", "title": "Create folder", "instruction": "code_new_project('flappy_bird')"},
        {"tier": "heavy", "title": "Write game", "instruction": "game.py"},
        {"tier": "medium", "title": "Verify", "verify": True, "instruction": "code_check then finish"}]})
    monkeypatch.setattr(agent, "run_manager_step", lambda model, h, mt, cancel_check=None: _resp(text=plan, t_in=500, t_out=300))
    project = tmp_path / "BuddyProjects" / "flappy-bird"
    queues = {"easy": [_resp(_call(1, "code_new_project", name="flappy bird")), _resp(_call(2, "finish_task", summary="Folder ready."))],
              "heavy": [_resp(_call(3, "code_write", path=str(project / "game.py"), content="print('hi')\n")),
                        _resp(_call(4, "finish_task", summary="Wrote game.py."))],
              "medium": [_resp(_call(5, "code_check", path=str(project))), _resp(_call(6, "finish_task", summary="Checked. Run: python3 game.py"))]}
    monkeypatch.setattr(agent, "run_action_step", lambda model, h, mt, tools, cancel_check=None, timeout_ms=None: queues[_tier(h)].pop(0))
    events = []
    out = agent.process_message_incognito("create flappy bird in python", core.new_message_history(), on_event=events.append)
    assert "python3 game.py" in out["reply"] and (project / "game.py").exists()
    assert "Coding mode" in out["plan_text"] and "[Heavy] Write game" in out["plan_text"]
    assert out["stats"]["Calls by tier"].startswith("Easy×2")
    calls = [e for e in events if e["type"] == "tool_call"]
    assert any(e["call"].startswith('code_write(path="%s"' % (project / "game.py")) for e in calls)   # full function + parameters
    assert all("call" in e and "tier" in e for e in calls)


def test_long_form_writing_uses_heavy_model_and_room_to_finish(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "route_first_pass", lambda *a, **k: ("chat", "", None))
    captured = {}

    def fake_manager(history, cancel_check=None, model=None, max_tokens=None):
        captured.update(model=model, max_tokens=max_tokens)
        return "Rome began as a small settlement...", None

    monkeypatch.setattr(agent, "get_manager_output", fake_manager)
    out = agent.process_message_incognito("write a 500 word essay on the fall of rome", core.new_message_history())
    assert captured["model"].endswith("sonnet-5.5") and captured["max_tokens"] >= 4000          # was capped at 600 tokens before
    assert out["reply"].startswith("Rome began")
    captured.clear()
    agent.process_message_incognito("what is the capital of france", core.new_message_history())
    assert not captured or captured["max_tokens"] <= 1500
