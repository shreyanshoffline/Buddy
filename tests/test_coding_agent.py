"""Coding mode end to end with a scripted fake model: tiered planning, cheap/heavy routing,
context isolation, escalation, fallbacks, permissions, and the real code_* tools."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.agent  # noqa: E402,F401  (import before tests change HOME)
from core.coding_agent import run_coding_agent, parse_plan  # noqa: E402
from core.staged import run_steps  # noqa: E402
from core.tiers import CostTracker, parse_tiered_plan, looks_like_long_form  # noqa: E402
from core.call_format import format_call  # noqa: E402
from tools.tools_schema import tools_schema  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODELS = {"easy": "anthropic/claude-haiku-5.5", "medium": "anthropic/claude-haiku-5.5", "heavy": "anthropic/claude-sonnet-5.5"}
E, M, H = "easy", "medium", "heavy"


def _call(i, _tool, **args):
    return NS(id="c%d" % i, function=NS(name=_tool, arguments=json.dumps(args)))


def _resp(*calls, text="", t_in=100, t_out=50):
    msg = NS(tool_calls=list(calls) or None, content=text)
    return NS(choices=[NS(message=msg, finish_reason="stop")], usage=NS(prompt_tokens=t_in, completion_tokens=t_out))


def _enable_files(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    import core.plugins as plugins
    enabled = plugins.default_plugins()
    enabled["system"]["folder_access"] = True
    monkeypatch.setattr(plugins, "load_plugins", lambda: enabled)


class FakeModels:
    """Scripted model: one queue of responses per tier; records every call."""
    def __init__(self, scripts):
        self.q = {MODELS[t] + "|" + t: list(v) for t, v in scripts.items()}
        self.calls = []

    def step_fn(self, tier_of):
        def step(model, history, max_tokens, tools, timeout_ms):
            tier = tier_of(model, history)
            self.calls.append({"tier": tier, "history": list(history), "tools": {t["function"]["name"] for t in tools}, "max_tokens": max_tokens})
            return self.q[MODELS[tier] + "|" + tier].pop(0)
        return step


def _tier_from_system(model, history):
    return next(t for t in ("easy", "medium", "heavy") if "the %s worker" % t.upper() in history[0]["content"])


def _plan_json(project):
    return json.dumps({"project_name": "si", "steps": [
        {"tier": "easy", "title": "Create project folder", "instruction": "Call code_new_project('space invaders')."},
        {"tier": "heavy", "title": "Write game logic and tests", "instruction": "game.py and tests/test_game.py"},
        {"tier": "medium", "title": "Verify and fix", "verify": True, "instruction": "code_test; fix small errors; finish with the run command."},
    ]})


def test_tiered_build_routes_by_tier_and_isolates_context(tmp_path, monkeypatch):
    _enable_files(monkeypatch, tmp_path)
    from core.agent import execute_tool
    project = tmp_path / "BuddyProjects" / "space-invaders"
    game = (FIXTURES / "space_invaders_game.py.txt").read_text()
    tests = (FIXTURES / "space_invaders_test.py.txt").read_text()
    fm = FakeModels({
        E: [_resp(_call(1, "code_new_project", name="space invaders")), _resp(_call(2, "finish_task", summary="Created folder."))],
        H: [_resp(_call(3, "code_write", path=str(project / "game.py"), content=game, ),
                  _call(4, "code_write", path=str(project / "tests" / "test_game.py"), content=tests), t_in=3000, t_out=4000),
            _resp(_call(5, "finish_task", summary="Wrote game.py (Game class) and tests/test_game.py."), t_in=3500, t_out=60)],
        M: [_resp(_call(6, "code_test", folder=str(project))), _resp(_call(7, "finish_task", summary="All 11 tests pass. Run: python3 main.py"))],
    })
    planner_calls = []

    def plan_fn(model, history, max_tokens):
        planner_calls.append(model)
        return _resp(text="Here is the plan:\n" + _plan_json(project), t_in=600, t_out=400)

    out = run_coding_agent("build me a space invaders game", [], fm.step_fn(_tier_from_system), execute_tool, tools_schema,
                           plan_fn=plan_fn, models=MODELS)
    assert out["status"] == "success", out
    assert planner_calls == [MODELS["medium"]]                                     # planner is NOT the heavy model
    tiers = [c["tier"] for c in fm.calls]
    assert tiers == ["easy", "easy", "heavy", "heavy", "medium", "medium"]
    heavy_tools = next(c for c in fm.calls if c["tier"] == "heavy")["tools"]
    assert {"code_write", "code_edit", "code_read"} <= heavy_tools
    assert not heavy_tools & {"code_run", "code_test", "code_new_project", "code_setup_env"}   # heavy only writes
    first_heavy = next(c for c in fm.calls if c["tier"] == "heavy")
    assert not any(isinstance(m, dict) and m.get("role") == "tool" for m in first_heavy["history"])  # no earlier transcript carried
    assert str(project) in first_heavy["history"][0]["content"]                    # but it knows the project folder
    assert "Project folder" in out["summary"] and "python3 main.py" in out["summary"]
    assert out["plan_text"].splitlines()[1].startswith("2. [Heavy]")
    stats = out["extra_stats"]
    assert "Heavy×2" in stats["Calls by tier"] and "Est. cost" in stats and "all-heavy" in stats["Est. cost"]
    est = float(stats["Est. cost"].split("$")[1].split(" ")[0])
    allheavy = float(stats["Est. cost"].split("$")[2].rstrip(")"))
    assert est < allheavy                                                          # cheaper than running everything on heavy
    assert (project / "game.py").exists()


def test_failed_verify_escalates_to_heavy_then_retries(tmp_path, monkeypatch):
    _enable_files(monkeypatch, tmp_path)
    from core.agent import execute_tool
    project = tmp_path / "BuddyProjects" / "calc"
    project.mkdir(parents=True)
    (project / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (project / "test_calc.py").write_text("from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    plan = json.dumps({"steps": [{"tier": "medium", "title": "Verify and fix", "verify": True, "instruction": "run tests"}]})
    fm = FakeModels({
        M: [_resp(_call(1, "code_test", folder=str(project))),
            _resp(_call(2, "finish_task", summary="BLOCKED: test_add fails, add() subtracts (calc.py line 2)")),
            _resp(_call(3, "code_test", folder=str(project))), _resp(_call(4, "finish_task", summary="Tests pass."))],
        H: [_resp(_call(5, "code_edit", path=str(project / "calc.py"), old_text="a - b", new_text="a + b")),
            _resp(_call(6, "finish_task", summary="Fixed add()."))],
    })
    out = run_coding_agent("fix the bug in my python project", [], fm.step_fn(_tier_from_system), execute_tool, tools_schema,
                           plan_fn=lambda *a: _resp(text=plan), models=MODELS)
    assert out["status"] == "success", out
    assert [c["tier"] for c in fm.calls] == ["medium", "medium", "heavy", "heavy", "medium", "medium"]
    heavy_brief = next(c for c in fm.calls if c["tier"] == "heavy")["history"]
    assert "add() subtracts" in heavy_brief[1]["content"]                          # heavy got the exact problem report
    assert "a + b" in (project / "calc.py").read_text()


def test_unusable_plan_falls_back_to_single_full_loop(tmp_path, monkeypatch):
    _enable_files(monkeypatch, tmp_path)
    from core.agent import execute_tool
    seen = {}
    fm = FakeModels({H: [_resp(_call(1, "code_new_project", name="x")), _resp(_call(2, "finish_task", summary="done"))]})

    def step(model, history, mt, tools, tm):
        seen["tools"] = {t["function"]["name"] for t in tools}
        seen["max_tokens"] = mt
        return fm.q[MODELS["heavy"] + "|heavy"].pop(0)

    out = run_coding_agent("build an app", [], step, execute_tool, tools_schema,
                           plan_fn=lambda *a: _resp(text="sorry, no json"), models=MODELS)
    assert out["status"] == "success" and {"code_run", "code_test", "code_write"} <= seen["tools"] and seen["max_tokens"] == 8000


def test_planner_parsing():
    assert parse_plan('x {"steps": [{"tier": "heavy_task", "title": "t", "instruction": "i"}]} y')[0]["tier"] == "heavy"
    assert parse_plan("no json") is None and parse_plan('{"steps": []}') is None


def test_generic_staged_plan_collects_heavy_text(tmp_path):
    plan = "1. [easy_task] Open Pages.\n2. [heavy_task] Write the essay on volcanoes.\n3. [medium_task] Save it to Documents."
    steps = parse_tiered_plan(plan)
    assert [s["tier"] for s in steps] == ["easy", "heavy", "medium"]
    scripts = {E: [_resp(_call(1, "finish_task", summary="Pages open."))],
               H: [_resp(text="Volcanoes form where magma reaches the surface...")],
               M: [_resp(_call(2, "finish_task", summary="Saved to Documents/volcanoes.txt."))]}
    fm = FakeModels(scripts)
    out = run_steps(steps, goal="essay on volcanoes", step_fn=fm.step_fn(lambda m, h: next(t for t in MODELS if f"the {t.upper()} worker" in h[0]["content"])),
                    execute=lambda n, a: "ok", schema=tools_schema, models=MODELS, tracker=CostTracker(MODELS["heavy"]), kind="general")
    assert out["status"] == "success" and out["heavy_text"] == ["Volcanoes form where magma reaches the surface..."]
    assert [c["tier"] for c in fm.calls] == ["easy", "heavy", "medium"]
    assert len(next(c for c in fm.calls if c["tier"] == "heavy")["tools"]) > 50          # general plans keep all tools


def test_tiers_and_formatting():
    exact = ("1. Create a folder in examples and name it flappy_bird. (easy_task)\n"
             "2. Create the necessary files and folders. (medium_task)\n"
             "3. Insert the lines of code the game needs. (Heavy_task)\n"
             "4. Install the required dependencies (easy_task)\n5. Test it and clean up and correct (medium_task)")
    assert [s["tier"] for s in parse_tiered_plan(exact)] == ["easy", "medium", "heavy", "easy", "medium"]
    assert parse_tiered_plan("1. Open Chrome\n2. Go to the site") is None
    assert looks_like_long_form("write a 500 word essay on rome") and not looks_like_long_form("open spotify")
    call = format_call("code_run", {"folder": "/a/b", "command": "python3 -m pytest -q", "timeout": 60, "headless": True})
    assert call == 'code_run(folder="/a/b", command="python3 -m pytest -q", timeout=60, headless=true)'
    big = format_call("code_write", {"path": "/a/x.py", "content": "line\n" * 300})
    assert 'path="/a/x.py"' in big and "300 lines" in big and len(big) < 400


def test_blocked_plugin_stops_and_explains(tmp_path):
    script = iter([_resp(_call(1, "code_run", folder="/x", command="ls"))])
    out = run_coding_agent("build an app", [], lambda *a: next(script), lambda n, a: "This plugin is turned off in Plugins.",
                           tools_schema, models=MODELS)
    assert out["status"] == "failed" and "turned off" in out["message"]


def test_truncated_tool_call_gets_retry_hint(tmp_path):
    bad = NS(id="c1", function=NS(name="code_write", arguments='{"path": "a.py", "content": "print('))
    script = iter([_resp(bad), _resp(_call(2, "finish_task", summary="ok"))])
    hist = []

    def step(model, h, *a):
        hist.append(list(h))
        return next(script)

    out = run_coding_agent("write a script", [], step, lambda n, a: "x", tools_schema, models=MODELS)
    assert out["status"] == "success"
    assert any("cut off" in m["content"] for m in hist[-1] if isinstance(m, dict) and m.get("role") == "tool")


def test_tool_crash_is_feedback_not_abort(tmp_path):
    script = iter([_resp(_call(1, "code_read", path="/x")), _resp(_call(2, "finish_task", summary="recovered"))])

    def execute(name, args):
        raise RuntimeError("tool exploded")

    out = run_coding_agent("fix my code", [], lambda *a: next(script), execute, tools_schema, models=MODELS)
    assert out["status"] == "success" and out["summary"] == "recovered"


def test_file_tools_blocked_until_user_enables_access(tmp_path, monkeypatch):
    from core.agent import execute_tool
    import core.plugins as plugins
    monkeypatch.setattr(plugins, "load_plugins", plugins.default_plugins)
    script = iter([_resp(_call(1, "code_new_project", name="x"))])
    out = run_coding_agent("build a game", [], lambda *a: next(script), execute_tool, tools_schema, models=MODELS)
    assert out["status"] == "failed" and "Files & Folders" in out["message"]


def test_code_tools_safety_and_undo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    from tools import code_agent as c
    f = tmp_path / "a.py"
    assert "Created" in c.code_write(str(f), "x = 1\n")
    assert "Edited" in c.code_edit(str(f), "x = 1", "x = 2")
    assert "NOT applied" in c.code_edit(str(f), "x = 2", "x = (")          # syntax-breaking edit is refused
    assert f.read_text() == "x = 2\n"
    assert "matches 2" in (c.code_write(str(f), "y=1\ny=1\n"), c.code_edit(str(f), "y=1", "y=2"))[1]
    assert "Restored" in c.code_undo(str(f)) and f.read_text() == "x = 2\n"
    assert "won't touch" in _perm(c.code_write, "/etc/hosts", "x")
    assert "sudo" in c.code_run(str(tmp_path), "sudo ls")
    assert c.code_run(str(tmp_path), "sleep 30", timeout=5).startswith("TIMED OUT")
    assert "exit code 0" in c.code_run(str(tmp_path), "echo hi")


def _perm(fn, *a):
    try:
        return fn(*a)
    except PermissionError as e:
        return str(e)


def test_file_tools_blocked_until_user_enables_access_default_models(tmp_path, monkeypatch):
    """Truthful permissions: with Files & Folders off, coding mode stops and says what to enable."""
    from core.agent import execute_tool
    import core.plugins as plugins
    monkeypatch.setattr(plugins, "load_plugins", plugins.default_plugins)
    script = iter([_resp(_call(1, "code_new_project", name="x"))])
    out = run_coding_agent("build a game", [], lambda *a: next(script), execute_tool, tools_schema)
    assert out["status"] == "failed" and "Files & Folders" in out["message"]


def test_upgrade_workflow_tools_on_existing_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    from tools import code_agent as c
    proj = tmp_path / "old_project"
    (proj / "pkg").mkdir(parents=True)
    (proj / ".git").mkdir()
    (proj / "pkg" / "util.py").write_text("def add(a,b):\n    return a+b\n\ndef risky(path):\n    return open(path).read()\n")
    (proj / "test_util.py").write_text("from pkg.util import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    assert "util.py" in c.code_overview(str(proj)) and ".git" not in c.code_overview(str(proj)).split("Tree:")[1]
    assert "pkg/util.py:4" in c.code_search(str(proj), r"def risky", "*.py")
    assert "return open(path)" in c.code_read(str(proj / "pkg" / "util.py"), 4, 5)
    c.code_edit(str(proj / "pkg" / "util.py"), "    return open(path).read()\n",
                "    try:\n        with open(path) as fh:\n            return fh.read()\n    except OSError:\n        return ''\n")
    assert c.code_check(str(proj)).startswith("OK")
    assert "passed" in c.code_test(str(proj))
    assert "util.py" in c.code_changes()
