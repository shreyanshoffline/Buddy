"""Show tool calls the way a developer would read them: full function name and parameters."""
import json

_NEVER_CUT = {"path", "folder", "command", "name", "url", "query", "pattern", "file_glob", "packages", "app", "channel", "to", "subject"}


def _size(text):
    n = len(text.encode("utf-8", errors="ignore"))
    return "%d B" % n if n < 1024 else "%.1f KB" % (n / 1024)


def format_value(key, value, limit=120):
    if isinstance(value, str):
        if key in _NEVER_CUT and len(value) <= 500 and "\n" not in value:
            return json.dumps(value, ensure_ascii=False)
        lines = len(value.splitlines()) or 1
        if len(value) <= limit and lines == 1:
            return json.dumps(value, ensure_ascii=False)
        head = value[:limit].replace("\n", "⏎")
        return '"%s…" <%d line%s, %s>' % (head, lines, "" if lines == 1 else "s", _size(value))
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False)
        return text if len(text) <= limit else text[:limit] + "…" + " <%s>" % _size(text)
    return json.dumps(value)


def format_call(name, args, limit=120):
    """code_write(path="/Users/me/game.py", content="import pygame…" <214 lines, 6.1 KB>)"""
    args = args or {}
    inner = ", ".join("%s=%s" % (k, format_value(k, v, limit)) for k, v in args.items())
    return "%s(%s)" % (name, inner)


def format_result(result, limit=240):
    text = " ".join(str(result).split())
    return text if len(text) <= limit else text[:limit] + "…"
