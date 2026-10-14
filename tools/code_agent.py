"""Buddy's coding toolkit: understand a project, edit it surgically, run it, test it, undo it.

Design (what makes a coding agent work):
- Read before edit; edit with exact-match replacements (cheap in tokens, safe).
- Every change is backed up first, so code_undo always works, even in non-git folders.
- Python edits that break syntax are auto-reverted and reported.
- code_run returns the real output + exit code so the model can verify its own work.
  Test failures are normal results, not tool errors: the model reads them and fixes the code.

Public functions are agent tools (core.agent.execute_tool discovers them via dir(module)),
so imports and helpers are underscore-prefixed.
"""
import ast as _ast
import fnmatch as _fnmatch
import json as _json
import os as _os
import re as _re
import shutil as _shutil
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import time as _time
from pathlib import Path as _Path

from tools.paths import data_dir as _data_dir

_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build",
                ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".DS_Store", "Pods", "DerivedData"}
_TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md", ".txt", ".toml",
             ".yml", ".yaml", ".sh", ".c", ".h", ".cpp", ".hpp", ".ino", ".swift", ".java", ".kt",
             ".go", ".rs", ".rb", ".php", ".sql", ".cfg", ".ini", ".xml", ".plist", ".env.example"}
_DENY_PARTS = ("/.ssh", "/.gnupg", "/.aws", "/Library/Keychains", "/.config/gh")
_DENY_PREFIX = ("/System", "/usr", "/bin", "/sbin", "/etc", "/private/etc", "/Library", "/Applications")
_DENY_HOME_FILES = (".zshrc", ".bashrc", ".bash_profile", ".zprofile", ".gitconfig", ".netrc")
_PROJECTS = "~/BuddyProjects"
_MAX_OUT = 6000
_SESSION = {"changed": {}}  # abs path -> number of edits this run


# ----------------------------------------------------------------- helpers
def _safe(path):
    p = _Path(_os.path.expanduser(path or "")).resolve()
    s = str(p)
    home = str(_Path.home())
    if any(s.startswith(d) for d in _DENY_PREFIX) or any(part in s for part in _DENY_PARTS):
        raise PermissionError("Buddy won't touch %s (system or credential location)." % s)
    if _os.path.dirname(s) == home and _os.path.basename(s) in _DENY_HOME_FILES:
        raise PermissionError("Buddy won't edit %s (shell/git config)." % s)
    return p


def _backup_root():
    return _data_dir("code-backups")


def _backup(p):
    """Copy the current file aside before changing it. Returns backup path or None (new file)."""
    if not p.exists() or not p.is_file():
        return None
    key = _re.sub(r"[^A-Za-z0-9]+", "_", str(p))[-120:]
    folder = _backup_root() / key
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / ("%d.bak" % int(_time.time() * 1000))
    _shutil.copy2(p, dest)
    for old in sorted(folder.glob("*.bak"))[:-20]:  # keep the last 20 versions per file
        old.unlink(missing_ok=True)
    return dest


def _latest_backup(p):
    key = _re.sub(r"[^A-Za-z0-9]+", "_", str(p))[-120:]
    files = sorted((_backup_root() / key).glob("*.bak"))
    return files[-1] if files else None


def _syntax_problem(p, text):
    if p.suffix == ".py":
        try:
            _ast.parse(text)
        except SyntaxError as e:
            return "Python syntax error line %s: %s" % (e.lineno, e.msg)
    elif p.suffix == ".json":
        try:
            _json.loads(text)
        except ValueError as e:
            return "Invalid JSON: %s" % e
    return ""


def _is_text(p):
    return p.suffix.lower() in _TEXT_EXT or p.name in ("Makefile", "Dockerfile", "README", "LICENSE", ".gitignore")


def _walk(root):
    for dirpath, dirs, files in _os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".git"))
        for f in sorted(files):
            yield _Path(dirpath) / f


def _tail(text, limit=_MAX_OUT):
    text = text or ""
    return text if len(text) <= limit else "…[earlier output cut]…\n" + text[-limit:]


def _env(folder, headless):
    env = dict(_os.environ, PYTHONUNBUFFERED="1")
    venv_bin = folder / ".venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = str(venv_bin) + _os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(folder / ".venv")
    if headless:
        env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1")
    return env


def _guard_command(command):
    low = command.lower()
    if _re.search(r"\bsudo\b", low):
        return "Not allowed: sudo. Buddy never runs commands as administrator."
    try:
        from tools import tools as _t
        if _t._is_dangerous_command(command):
            if not _t._confirm("Buddy wants to run a command", command[:300]):
                return "Command cancelled by user (dangerous pattern detected)."
    except Exception:
        pass
    return ""


# ----------------------------------------------------------------- understand
def code_overview(folder: str, depth: int = 3) -> str:
    """Maps a project folder: file tree, languages, entry points, and README/config files. Start here before editing unfamiliar code."""
    root = _safe(folder)
    if not root.is_dir():
        return "Not a folder: %s" % root
    files = list(_walk(root))
    exts = {}
    for f in files:
        exts[f.suffix.lower() or f.name] = exts.get(f.suffix.lower() or f.name, 0) + 1
    lines = ["%s — %d files" % (root, len(files)),
             "Types: " + ", ".join("%s×%d" % kv for kv in sorted(exts.items(), key=lambda kv: -kv[1])[:8])]
    notable = [f.name for f in files if f.parent == root and f.name.lower() in (
        "readme.md", "package.json", "requirements.txt", "pyproject.toml", "main.py", "app.py", "index.html",
        "makefile", "setup.py", "cargo.toml", "go.mod", "platformio.ini")]
    if notable:
        lines.append("Key files: " + ", ".join(notable))
    lines.append("Tree:")
    shown = 0
    for f in files:
        rel = f.relative_to(root)
        if len(rel.parts) > depth:
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue
        lines.append("  %s (%s)" % (rel, ("%dB" % size) if size < 2048 else ("%dKB" % (size // 1024))))
        shown += 1
        if shown >= 120:
            lines.append("  … more files; narrow with code_search")
            break
    return "\n".join(lines)


def code_read(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Reads a source file with line numbers. Use start_line/end_line to read just the part you need (default first 250 lines)."""
    p = _safe(path)
    if not p.is_file():
        return "No such file: %s" % p
    if not _is_text(p) and p.stat().st_size > 2_000_000:
        return "Not a readable text file: %s" % p
    text = p.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(start_line))
    end = int(end_line) or min(len(text), start + 249)
    end = min(end, len(text), start + 399)
    body = "\n".join("%d\t%s" % (i + 1, text[i]) for i in range(start - 1, end))
    more = "\n… %d more lines (use start_line=%d)" % (len(text) - end, end + 1) if end < len(text) else ""
    return "%s (%d lines)\n%s%s" % (p, len(text), _tail(body, 14000), more)


def code_search(folder: str, pattern: str, file_glob: str = "") -> str:
    """Searches a project with a regular expression (case-insensitive). Optional file_glob like '*.py'. Returns file:line: text."""
    root = _safe(folder)
    try:
        rx = _re.compile(pattern, _re.I)
    except _re.error:
        rx = _re.compile(_re.escape(pattern), _re.I)
    hits = []
    for f in _walk(root):
        if not _is_text(f) or (file_glob and not _fnmatch.fnmatch(f.name, file_glob)):
            continue
        try:
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append("%s:%d: %s" % (f.relative_to(root), n, line.strip()[:160]))
                    if len(hits) >= 60:
                        return "\n".join(hits) + "\n… (60 shown; refine the pattern)"
        except OSError:
            continue
    return "\n".join(hits) or "No matches."


# ----------------------------------------------------------------- change
def code_new_project(name: str) -> str:
    """Creates a fresh project folder under ~/BuddyProjects/<name> and returns its path. Use for any new app, game, or script."""
    slug = _re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-") or "project"
    root = _Path(_os.path.expanduser(_PROJECTS)) / slug
    n = 2
    while root.exists() and any(root.iterdir()):
        root = _Path(_os.path.expanduser(_PROJECTS)) / ("%s-%d" % (slug, n))
        n += 1
    root.mkdir(parents=True, exist_ok=True)
    return "Created project folder: %s" % root


def code_write(path: str, content: str) -> str:
    """Creates or fully overwrites a file (folders are created automatically). Use code_edit for small changes to existing files."""
    p = _safe(path)
    existed = p.exists()
    _backup(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _SESSION["changed"][str(p)] = _SESSION["changed"].get(str(p), 0) + 1
    problem = _syntax_problem(p, content)
    note = ("\nWARNING: %s — fix it with code_edit." % problem) if problem else ""
    return "%s %s (%d lines).%s" % ("Overwrote" if existed else "Created", p, content.count("\n") + 1, note)


def code_edit(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """Replaces exact text in a file. old_text must match exactly once (include enough surrounding lines to be unique), or set replace_all. Python edits that break syntax are auto-reverted."""
    p = _safe(path)
    if not p.is_file():
        return "No such file: %s (use code_write to create it)." % p
    text = p.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count == 0:
        first = old_text.strip().splitlines()[0][:60] if old_text.strip() else ""
        near = [str(i + 1) for i, l in enumerate(text.splitlines()) if first and first in l][:3]
        hint = (" A similar line exists at line(s) %s — re-read with code_read and copy exact text." % ", ".join(near)) if near else ""
        return "old_text not found in %s.%s" % (p.name, hint)
    if count > 1 and not replace_all:
        return "old_text matches %d places in %s; add surrounding lines to make it unique, or pass replace_all=true." % (count, p.name)
    updated = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
    problem = _syntax_problem(p, updated)
    if problem and not _syntax_problem(p, text):
        return "Edit NOT applied: it would cause a %s. Fix the replacement text and retry." % problem
    _backup(p)
    p.write_text(updated, encoding="utf-8")
    _SESSION["changed"][str(p)] = _SESSION["changed"].get(str(p), 0) + 1
    line = text[: text.index(old_text)].count("\n") + 1
    return "Edited %s at line %d (%d replacement%s)." % (p.name, line, count if replace_all else 1, "s" if replace_all and count > 1 else "")


def code_undo(path: str) -> str:
    """Restores the previous version of a file Buddy changed (works without git). Call again to step back further."""
    p = _safe(path)
    b = _latest_backup(p)
    if not b:
        return "No earlier version saved for %s." % p
    _shutil.copy2(b, p)
    b.unlink(missing_ok=True)
    return "Restored the previous version of %s." % p.name


def code_changes() -> str:
    """Lists the files Buddy created or edited in this session (for a final summary or review)."""
    if not _SESSION["changed"]:
        return "No files changed yet."
    return "\n".join("%s (%d edit%s)" % (k, v, "" if v == 1 else "s") for k, v in _SESSION["changed"].items())


# ----------------------------------------------------------------- verify
def code_check(path: str) -> str:
    """Checks a file or whole folder for syntax errors (Python, JSON, JavaScript if Node is installed). Fast; run after big changes."""
    root = _safe(path)
    files = [root] if root.is_file() else [f for f in _walk(root) if f.suffix in (".py", ".json", ".js")]
    problems = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        issue = _syntax_problem(f, text)
        if not issue and f.suffix == ".js" and _shutil.which("node"):
            r = _subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=20)
            if r.returncode:
                issue = (r.stderr.strip().splitlines() or ["JS syntax error"])[-1]
        if issue:
            problems.append("%s: %s" % (f.name, issue))
    return "\n".join(problems) if problems else "OK: %d file(s) checked, no syntax errors." % len(files)


def code_setup_env(folder: str, packages: str = "") -> str:
    """Creates a private Python virtual environment (.venv) in the project and installs space-separated packages (e.g. 'pygame'). Later code_run calls use it automatically."""
    root = _safe(folder)
    root.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv"
    if not venv.exists():
        r = _subprocess.run([_sys.executable if not getattr(_sys, "frozen", False) else "python3", "-m", "venv", str(venv)],
                            capture_output=True, text=True, timeout=180)
        if r.returncode:
            return "venv creation failed: " + _tail(r.stderr, 1500)
    pkgs = packages.split()
    if not pkgs:
        return "Environment ready at %s" % venv
    r = _subprocess.run([str(venv / "bin" / "pip"), "install", "-q", *pkgs], capture_output=True, text=True, timeout=600)
    if r.returncode:
        return "pip install failed:\n" + _tail(r.stderr or r.stdout, 2500)
    return "Installed %s into %s" % (", ".join(pkgs), venv)


def code_run(folder: str, command: str, timeout: int = 60, headless: bool = False) -> str:
    """Runs a shell command inside a project folder and returns its output and exit code. Use it to run scripts and tests. headless=true makes pygame/SDL use a dummy display so games can be tested without a window. Killed after `timeout` seconds."""
    root = _safe(folder)
    if not root.is_dir():
        return "Folder does not exist: %s" % root
    blocked = _guard_command(command)
    if blocked:
        return blocked
    timeout = max(5, min(int(timeout), 600))
    proc = _subprocess.Popen(command, shell=True, cwd=str(root), env=_env(root, headless), text=True,
                             stdout=_subprocess.PIPE, stderr=_subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return "exit code %d\n%s" % (proc.returncode, _tail(out))
    except _subprocess.TimeoutExpired:
        try:
            _os.killpg(proc.pid, _signal.SIGKILL)
        except OSError:
            proc.kill()
        out, _ = proc.communicate()
        return ("TIMED OUT after %ds and was stopped (a game or server that never exits does this — "
                "verify it with a headless test instead).\n%s" % (timeout, _tail(out)))


def code_test(folder: str) -> str:
    """Auto-detects and runs the project's tests (pytest, unittest, or npm test) and returns the results."""
    root = _safe(folder)
    if (root / "package.json").exists() and '"test"' in (root / "package.json").read_text(errors="ignore"):
        return code_run(str(root), "npm test --silent", 180)
    has_tests = any(f.name.startswith("test_") or f.name.endswith("_test.py") for f in _walk(root))
    if not has_tests:
        return "No tests found. Write tests (test_*.py) first, then run code_test."
    py = "python3"
    if (root / ".venv" / "bin" / "python").exists():
        py = ".venv/bin/python"
    probe = _subprocess.run([py, "-c", "import pytest"], cwd=str(root), capture_output=True)
    cmd = "%s -m pytest -q -x --tb=short" % py if probe.returncode == 0 else "%s -m unittest discover -v" % py
    return code_run(str(root), cmd, 180, headless=True)


def code_launch(folder: str, command: str) -> str:
    """Starts a program (such as a finished game) in the background so the user can use it, and returns immediately. Only after tests pass."""
    root = _safe(folder)
    blocked = _guard_command(command)
    if blocked:
        return blocked
    _subprocess.Popen(command, shell=True, cwd=str(root), env=_env(root, False), start_new_session=True,
                      stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    return "Launched: %s (in %s). It runs on its own; the user can close its window when done." % (command, root)
