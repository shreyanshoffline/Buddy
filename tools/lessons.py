"""Things the user taught Buddy once, so they never have to teach it twice.

Stored in ~/Library/Application Support/Buddy/lessons.json (survives updates).
Relevant lessons are injected into every turn by storage.memory; lessons with
topic "always" are injected on every turn. Public functions are agent tools
(imports and helpers are underscore-prefixed because core.agent.execute_tool
discovers tools via dir(module)).
"""
import json as _json
import os as _os
import re as _re
import tempfile as _tempfile
import time as _time

from tools.paths import data_file as _data_file

_MAX_LESSONS = 200
_STOP = set("the a an and or to of in on for with my is it that this do how when i you be as at by from are was".split())


def _path():
    return _data_file("lessons.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = _json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(items):
    path = _path()
    fd, tmp = _tempfile.mkstemp(dir=_os.path.dirname(path), suffix=".tmp")
    with _os.fdopen(fd, "w", encoding="utf-8") as fh:
        _json.dump(items[-_MAX_LESSONS:], fh, indent=1)
    _os.replace(tmp, path)  # atomic: a crash can't corrupt the file


def _words(text):
    return {w for w in _re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 2}


def save_lesson(lesson: str, topic: str = "general") -> str:
    """Saves something the user taught or corrected so it is never asked again.
    topic: short keyword like 'slack', 'email', 'formatting', or 'always' for rules that apply to everything."""
    lesson = (lesson or "").strip()
    if not lesson:
        return "Nothing to save."
    try:
        from storage import db
        if not db.memory_category_enabled("work_patterns"):
            return "Work-pattern memory is turned off, so I did not save that lesson."
    except Exception:
        pass
    items = _load()
    new_words = _words(lesson)
    for item in items:
        old = _words(item["lesson"])
        if old and new_words and len(old & new_words) / max(1, len(old | new_words)) > 0.6:
            item.update({"lesson": lesson, "topic": topic, "updated": _time.time()})
            _save(items)
            return "Updated an existing lesson instead of duplicating it."
    items.append({"lesson": lesson, "topic": (topic or "general").lower(), "created": _time.time(), "updated": _time.time(), "uses": 0})
    _save(items)
    return "Learned. I won't need to be told this again."


def list_lessons() -> str:
    """Lists everything the user has taught Buddy."""
    items = _load()
    if not items:
        return "No lessons saved yet."
    return "\n".join("%d. [%s] %s" % (i + 1, it.get("topic", "general"), it["lesson"]) for i, it in enumerate(items))


def list_lesson_items():
    """Return lessons in the shape needed by the Memory page."""
    return [
        {
            "number": index + 1,
            "lesson": item.get("lesson", ""),
            "topic": item.get("topic", "general"),
            "updated": item.get("updated", item.get("created", 0)),
        }
        for index, item in enumerate(_load())
    ]


def update_lesson(number: int, lesson: str) -> bool:
    items = _load()
    try:
        index = int(number) - 1
        text = (lesson or "").strip()
        if index < 0 or index >= len(items) or not text:
            return False
        items[index].update({"lesson": text, "updated": _time.time()})
    except (TypeError, ValueError):
        return False
    _save(items)
    return True


def delete_lesson(number: int) -> bool:
    items = _load()
    try:
        index = int(number) - 1
        if index < 0 or index >= len(items):
            return False
        items.pop(index)
    except (TypeError, ValueError):
        return False
    _save(items)
    return True


def forget_lesson(number: int) -> str:
    """Deletes lesson number N (from list_lessons)."""
    items = _load()
    try:
        removed = items.pop(int(number) - 1)
    except (IndexError, ValueError):
        return "No lesson with that number."
    _save(items)
    return "Forgot: " + removed["lesson"]


def _relevant(query, limit=5):
    """Lessons to inject for this user message (not a tool)."""
    try:
        from storage import db
        if not db.memory_category_enabled("work_patterns"):
            return []
    except Exception:
        pass
    items = _load()
    q = _words(query)
    always = [it for it in items if it.get("topic") == "always"][:4]
    scored = []
    for it in items:
        if it in always:
            continue
        score = len(q & (_words(it["lesson"]) | _words(it.get("topic", ""))))
        if score:
            scored.append((score, it.get("updated", 0), it))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [it["lesson"] for it in always] + [s[2]["lesson"] for s in scored[:limit]]
