"""
core/activity_watcher.py

Periodically (every 5-10 min while Buddy is running) records what app
is frontmost, purely locally, and ONLY if the user has explicitly
turned this on. After enough days of data, it asks Buddy's own model
(via process_message_incognito — same free Hack Club AI pipeline
already used for chat, no new API/key needed) to turn the raw log
into a plain-English list of habits: favorite apps, usual hours,
recurring routines. Never sends anything anywhere except that local
model call, and never logs window titles, file contents, or anything
besides the app's name and timestamp.

Consent lives in a single flag file, not buried in a settings blob —
easy to check, easy to delete, easy to show truthfully in the UI.
"""

import os
import time
from datetime import datetime, timedelta

try:
    from PySide6.QtCore import QObject, QTimer
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    QObject = object  # fallback so the class below can still be defined/imported

import core
from core import patterns

CONSENT_FLAG_PATH = os.path.expanduser("~/.buddy/activity_watch_enabled")
SUMMARY_PATH = os.path.expanduser("~/.buddy/activity_summary.txt")
LAST_SUMMARY_META_PATH = os.path.expanduser("~/.buddy/activity_summary_last_run")


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    return os.path.exists(CONSENT_FLAG_PATH)


def set_enabled(on: bool) -> str:
    os.makedirs(os.path.dirname(CONSENT_FLAG_PATH), exist_ok=True)
    if on:
        with open(CONSENT_FLAG_PATH, "w") as f:
            f.write(f"enabled at {datetime.now().isoformat()}\n")
        return ("Background activity tracking is ON. Buddy will note which app is frontmost "
                "every 5-10 minutes while it's running, and after about a week can summarize "
                "your habits. Nothing leaves this machine. Turn off any time in Settings.")
    else:
        if os.path.exists(CONSENT_FLAG_PATH):
            os.remove(CONSENT_FLAG_PATH)
        return "Background activity tracking is OFF."


def forget_everything() -> str:
    """Real delete control — wire to a 'Forget my activity' button, not just
    the on/off toggle. Removes the raw log AND the derived summary."""
    removed = []
    if os.path.exists(SUMMARY_PATH):
        os.remove(SUMMARY_PATH)
        removed.append("summary")
    if os.path.exists(LAST_SUMMARY_META_PATH):
        os.remove(LAST_SUMMARY_META_PATH)
    patterns.forget_all()
    removed.append("activity log")
    return "Cleared: " + ", ".join(removed) if removed else "Nothing recorded yet."


# ---------------------------------------------------------------------------
# The periodic snapshot itself
# ---------------------------------------------------------------------------

def _capture_snapshot():
    if not is_enabled():
        return
    try:
        from tools.tools import get_frontmost_app
        app_name = get_frontmost_app()
    except Exception:
        app_name = None
    if app_name and not app_name.startswith("Error"):
        patterns.log_action(f"active_app:{app_name.strip()}")


class ActivityWatcher(QObject):
    """Instantiate ONCE in main_window.__init__:

        self._activity_watcher = ActivityWatcher()
        self._activity_watcher.start()

    Fires roughly every 7 minutes while the app is open. Does nothing
    at all unless the user has turned tracking on in Settings — safe
    to construct and start unconditionally."""

    def __init__(self, interval_minutes: float = 7.0, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            raise RuntimeError("PySide6 not available — ActivityWatcher only runs inside the GUI process.")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._interval_ms = int(interval_minutes * 60 * 1000)

    def start(self):
        self._timer.start(self._interval_ms)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        _capture_snapshot()
        _maybe_run_weekly_summary()


# ---------------------------------------------------------------------------
# Turning the raw log into plain-English habits, using Buddy's own model
# ---------------------------------------------------------------------------

def _maybe_run_weekly_summary(min_days_of_data: int = 6, rerun_every_hours: int = 24):
    """Called from the same timer tick as the snapshot — cheap to check,
    only actually calls the model once a day at most, and only once
    there's enough real history to say anything true."""
    if not is_enabled():
        return
    if os.path.exists(LAST_SUMMARY_META_PATH):
        last_run = os.path.getmtime(LAST_SUMMARY_META_PATH)
        if time.time() - last_run < rerun_every_hours * 3600:
            return

    rows = patterns._recent_events(days=30)
    if not rows:
        return
    # Simple proxy for "enough real history": at a ~7-minute cadence,
    # collecting fewer than 20 snapshots means tracking was just turned
    # on — not enough to say anything true yet.
    if len(rows) < 20:
        return

    summarize_now()


def summarize_now() -> str:
    """Can also be called directly from a 'Summarize my habits' button in
    Settings, not just the automatic timer."""
    top = patterns.top_actions(limit=15, days=30)
    apps = patterns.app_open_frequency(days=30)
    if not top and not apps:
        return "Not enough recorded activity yet to summarize."

    lines = []
    for action, count in top:
        lines.append(f"- {action}: {count} times in the last 30 days")
    for app, count in apps:
        lines.append(f"- opened app '{app}': {count} times")
    raw_summary = "\n".join(lines)

    prompt = (
        "Here is a local log of app usage frequency for one user, gathered over the last 30 days. "
        "Turn it into a short, plain-English list of the user's habits: favorite apps, times of day "
        "patterns tend to cluster (if inferable from the counts alone — if not inferable, don't guess "
        "at specific hours), and anything that looks like a recurring routine. 4-6 bullet points max. "
        "Do not invent anything not supported by the data below.\n\n" + raw_summary
    )

    try:
        result = core.process_message_incognito(prompt, message_history=[])
        response_text = (result or {}).get("reply", "").strip()
        if not response_text:
            response_text = raw_summary  # fall back to raw counts if the model returned nothing
    except Exception as e:
        response_text = f"(Model summary unavailable: {e})\n\nRaw activity counts:\n{raw_summary}"

    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w") as f:
        f.write(response_text)
    with open(LAST_SUMMARY_META_PATH, "w") as f:
        f.write(str(time.time()))

    return response_text


def get_latest_summary() -> str:
    if os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH, "r") as f:
            return f.read()
    return "No summary yet — needs about a week of activity with tracking turned on."
