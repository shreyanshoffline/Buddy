"""Drives the real coding loop + real code_* tools with a scripted fake model:
build Space Invaders (logic + tests), hit a failing test, fix it with code_edit, pass, finish."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.agent  # noqa: E402,F401  (import before tests change HOME)
from core.coding_agent import run_coding_agent  # noqa: E402
from tools.tools_schema import tools_schema  # noqa: E402
EX = Path(__file__).resolve().parent.parent / "examples" / "space_invaders"


def _call(i, _tool, **args):
    return NS(id="c%d" % i, function=NS(name=_tool, arguments=json.dumps(args)))


def _resp(*calls, text=""):
    msg = NS(tool_calls=list(calls) or None, content=text)
    return NS(choices=[NS(message=msg, finish_reason="stop")], usage=NS(prompt_tokens=10, completion_tokens=5))


def test_agent_builds_fixes_and_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    from core.agent import execute_tool
    import core.plugins as plugins
    enabled = plugins.default_plugins()
    enabled["system"]["folder_access"] = True          # the user switched on Files & Folders in Plugins
    monkeypatch.setattr(plugins, "load_plugins", lambda: enabled)

    project = tmp_path / "BuddyProjects" / "space-invaders"
    game_src = (EX / "game.py").read_text()
    buggy = game_src.replace("        self.hiscore = max(self.hiscore, self.score)\n", "")
    assert buggy != game_src
    seen = []
    script = [
        _resp(_call(1, "code_new_project", name="space invaders")),
        _resp(_call(2, "code_write", path=str(project / "game.py"), content=buggy)),
        _resp(_call(3, "code_write", path=str(project / "tests" / "test_game.py"), content=(EX / "tests" / "test_game.py").read_text())),
        _resp(_call(4, "code_check", path=str(project))),
        _resp(_call(5, "code_test", folder=str(project))),                       # fails: hiscore never updates
        _resp(_call(6, "code_edit", path=str(project / "game.py"),
                    old_text="        self.score += pts\n",
                    new_text="        self.score += pts\n        self.hiscore = max(self.hiscore, self.score)\n")),
        _resp(_call(7, "code_test", folder=str(project))),                       # passes
        _resp(_call(8, "finish_task", summary="Built Space Invaders in %s; 11 tests pass." % project)),
    ]
    it = iter(script)

    def step_fn(history, max_tokens, tools, timeout_ms):
        seen.append(list(history))
        assert max_tokens >= 4000 and timeout_ms >= 60_000          # room to write whole files
        assert any(t["function"]["name"] == "code_edit" for t in tools)
        return next(it)

    out = run_coding_agent("build me a space invaders game", [], step_fn, execute_tool, tools_schema)
    assert out["status"] == "success", out
    assert "11 tests pass" in out["summary"]
    results = [m["content"] for m in seen[-1] if isinstance(m, dict) and m.get("role") == "tool"]
    assert any("exit code" in r and ("failed" in r.lower() or "error" in r.lower()) for r in results), results   # saw the failure
    assert "passed" in results[-1] or "OK" in results[-1]                                                 # then the pass
    assert (project / "game.py").exists() and "self.hiscore = max" in (project / "game.py").read_text()


def test_tool_failure_is_feedback_not_abort(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    script = iter([_resp(_call(1, "boom")), _resp(_call(2, "finish_task", summary="recovered"))])

    def execute(name, args):
        raise RuntimeError("tool exploded")

    out = run_coding_agent("fix my code", [], lambda *a: next(script), execute, tools_schema)
    assert out["status"] == "success" and out["summary"] == "recovered"


def test_blocked_plugin_stops_and_explains(tmp_path):
    script = iter([_resp(_call(1, "code_run", folder="/x", command="ls"))])
    out = run_coding_agent("build an app", [], lambda *a: next(script),
                           lambda n, a: "This plugin is turned off in Plugins.", tools_schema)
    assert out["status"] == "failed" and "turned off" in out["message"]


def test_truncated_tool_call_gets_retry_hint(tmp_path):
    bad = NS(id="c1", function=NS(name="code_write", arguments='{"path": "a.py", "content": "print('))
    script = iter([_resp(bad), _resp(_call(2, "finish_task", summary="ok"))])
    hist = []

    def step(h, *a):
        hist.append(list(h))
        return next(script)

    out = run_coding_agent("write a script", [], step, lambda n, a: "x", tools_schema)
    assert out["status"] == "success"
    assert any("cut off" in m["content"] for m in hist[-1] if isinstance(m, dict) and m.get("role") == "tool")


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


def test_file_tools_blocked_until_user_enables_access(tmp_path, monkeypatch):
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
