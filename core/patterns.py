"""
core/patterns.py — lightweight local usage-pattern tracker for Buddy.

Everything lives at ~/.buddy/patterns.db, on disk, on this machine only.
Nothing here is uploaded anywhere — matches the roadmap's own rule
("Friend builds log spend locally; nothing uploads chats"). This is
what lets Buddy say "you usually check email around now" instead of
starting cold every session.

Deliberately conservative: it won't say anything until a pattern has
actually repeated enough times to be real, and it never claims a
pattern it can't back with a count. That's the same "every visible
control is a promise" rule applied to a proactive nudge instead of a
button.
"""

import os
import sqlite3
import time
from collections import Counter
from datetime import datetime
from typing import Optional

DB_PATH = os.path.expanduser("~/.buddy/patterns.db")

# Map raw logged action names to plain-English phrasing. Extend this as
# you log more actions elsewhere in the codebase — anything missing
# just falls back to showing the raw action string (honest, if ugly,
# rather than silently invisible).
ACTION_LABELS = {
    "gmail.summarize": "check your email",
    "gmail.read_unread": "check your email",
    "calendar.today": "look at today's calendar",
    "apple.reminders.list": "check your reminders",
    "apple.notes.find": "look something up in Notes",
}


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,      -- e.g. "gmail.summarize", "app.open:VS Code"
            ts REAL NOT NULL,          -- unix timestamp
            hour INTEGER NOT NULL,     -- 0-23, local time
            weekday INTEGER NOT NULL   -- 0=Monday .. 6=Sunday
        )
    """)
    return con


def log_action(action: str) -> None:
    """Call this once, right after a tool call actually succeeds.
    Log the ACTION NAME only — 'gmail.read_unread', never the email
    contents or any data the action touched. One line at the single
    choke point where your agent loop dispatches a matched tool call
    is enough; don't scatter this call into every individual tool
    function."""
    now = datetime.now()
    con = _connect()
    con.execute(
        "INSERT INTO events (action, ts, hour, weekday) VALUES (?, ?, ?, ?)",
        (action, time.time(), now.hour, now.weekday()),
    )
    con.commit()
    con.close()


def _recent_events(days: int = 30):
    cutoff = time.time() - days * 86400
    con = _connect()
    rows = con.execute(
        "SELECT action, hour, weekday FROM events WHERE ts >= ?", (cutoff,)
    ).fetchall()
    con.close()
    return rows


def top_actions(limit: int = 5, days: int = 30):
    """[(action, count), ...] most frequent actions in the window."""
    rows = _recent_events(days)
    return Counter(a for a, _, _ in rows).most_common(limit)


def app_open_frequency(days: int = 30):
    """[('VS Code', 12), ('Slack', 8), ...] — feed into onboarding or
    the capability card as 'apps you use most'. Requires you to log
    app opens as 'app.open:<Name>' wherever open_app() succeeds."""
    rows = _recent_events(days)
    counts = Counter()
    for action, _, _ in rows:
        if action.startswith("app.open:"):
            counts[action.split(":", 1)[1]] += 1
    return counts.most_common(10)


def get_proactive_suggestion(min_occurrences: int = 4, hour_window: int = 1) -> Optional[str]:
    """
    Returns ONE suggestion string if the current hour matches a real,
    repeated pattern — else None. Call this once per new session
    (not every turn) and surface the result as an opener, not a nag.

    min_occurrences guards against a 1-2-time coincidence being read
    as a "pattern." Raise it if Buddy feels presumptuous; lower it if
    it never says anything.
    """
    now = datetime.now()
    rows = _recent_events(days=30)
    if len(rows) < min_occurrences:
        return None

    matches = Counter()
    for action, hour, _ in rows:
        if abs(hour - now.hour) <= hour_window:
            matches[action] += 1

    if not matches:
        return None

    action, count = matches.most_common(1)[0]
    if count < min_occurrences:
        return None

    label = ACTION_LABELS.get(action, action)
    return f"I've noticed you often {label} around this time ({count}x in the last 30 days) — want me to go ahead?"


def forget_all() -> str:
    """User-facing 'forget my patterns' control — wire this to a button
    in Settings, don't make it something only you can trigger from a
    terminal. Matches the roadmap's 'data deletion control' item."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        return "Cleared all recorded usage patterns."
    return "Nothing recorded yet."