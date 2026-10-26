"""Instruction guides Buddy reads before doing unfamiliar work (knowledge/*.md).

Guides are split into '## ' sections so Buddy loads only what it needs.
"""
import re as _re
import sys as _sys
from pathlib import Path as _Path

from tools.paths import app_root as _app_root


def _dirs():
    out = []
    if getattr(_sys, "_MEIPASS", None):
        out.append(_Path(_sys._MEIPASS) / "knowledge")
    out += [_app_root() / "knowledge", _Path(__file__).resolve().parent.parent / "knowledge"]
    return [d for d in out if d.is_dir()]


def _files():
    seen = {}
    for d in _dirs():
        for f in sorted(d.glob("*.md")):
            seen.setdefault(f.stem, f)
    return seen


def _sections(text):
    parts = _re.split(r"(?m)^## ", text)
    return parts[0], ["## " + p for p in parts[1:]]


def list_guides() -> str:
    """Lists the instruction guides available (capabilities, coding, macos, browser, web_search, google_workspace, microsoft, slack, computer_control)."""
    files = _files()
    if not files:
        return "No guides found."
    lines = []
    for name, f in files.items():
        first = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        lines.append("%s — %s" % (name, first))
    return "\n".join(lines)


def read_guide(topic: str, section: str = "") -> str:
    """Reads a guide. Pass section (a keyword from a '##' heading) to load only that part; omit for the outline."""
    files = _files()
    key = (topic or "").lower().strip().replace(" ", "_").replace("-", "_")
    match = next((n for n in files if n == key or key in n), None)
    if not match:
        return "No guide named '%s'. Available: %s" % (topic, ", ".join(files) or "none")
    head, secs = _sections(files[match].read_text(encoding="utf-8"))
    if not section:
        titles = [s.splitlines()[0][3:] for s in secs]
        return head.strip() + "\n\nSections (call read_guide again with section=<keyword>):\n- " + "\n- ".join(titles)
    hits = [s for s in secs if section.lower() in s.splitlines()[0].lower()] or [
        s for s in secs if section.lower() in s.lower()
    ]
    return "\n\n".join(hits[:3]) if hits else "No section matching '%s' in %s." % (section, match)


def search_guides(query: str) -> str:
    """Searches every guide for a keyword/phrase and returns the matching sections."""
    q = (query or "").lower().split()
    scored = []
    for name, f in _files().items():
        for s in _sections(f.read_text(encoding="utf-8"))[1]:
            score = sum(s.lower().count(w) for w in q)
            if score:
                scored.append((score, name, s))
    scored.sort(key=lambda t: t[0], reverse=True)
    if not scored:
        return "Nothing in the guides matches '%s'." % query
    return "\n\n".join("[%s]\n%s" % (n, s[:1200]) for _, n, s in scored[:3])
