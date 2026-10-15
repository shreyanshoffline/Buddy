"""Local-only activity learning: which app (and website NAME) you use, and when.

Runs only while the user has opted in (Settings > Activity Tracking; off by default).
Privacy design (keep it this way):
- Records only app names, website host names (e.g. "canvas.school.edu"), and timestamps.
- Never window titles, page content, URLs paths/queries, keystrokes, screenshots, or file names.
- Skips password managers/keychains and sensitive sites; skips when you are idle.
- Everything stays in Buddy's local database. Settings can turn it off and wipe it.
"""
import re
import subprocess
import threading
import time
from urllib.parse import urlparse

from storage import db

SAMPLE_INTERVAL = 20          # seconds between looks at the frontmost app
IDLE_LIMIT = 300              # no keyboard/mouse for 5 min = not "using" anything
GAP_SECONDS = 90              # samples closer than this extend one session
RETENTION_DAYS = 90

SKIP_APPS = {
    "loginwindow", "ScreenSaverEngine", "Keychain Access", "Passwords", "1Password", "1Password 7",
    "Bitwarden", "LastPass", "Dashlane", "Buddy", "Python", "Electron",
}
BROWSERS = {
    "Google Chrome": 'URL of active tab of front window',
    "Brave Browser": 'URL of active tab of front window',
    "Microsoft Edge": 'URL of active tab of front window',
    "Arc": 'URL of active tab of front window',
    "Safari": 'URL of current tab of front window',
}
SENSITIVE_DOMAIN_HINTS = (
    "bank", "chase.", "wellsfargo", "paypal", "venmo", "cash.app", "schwab", "fidelity", "robinhood", "coinbase",
    "mychart", "health", "medical", "patient", "pharmacy", "irs.gov", "ssa.gov", "login.", "accounts.", "auth.",
    "1password", "bitwarden", "lastpass", "dashlane",
)


def is_enabled():
    """One consent switch for all activity learning: the existing opt-in flag (off by default)."""
    from core import activity_watcher
    return activity_watcher.is_enabled()


def set_enabled(flag):
    from core import activity_watcher
    return activity_watcher.set_enabled(bool(flag))


def clear_all():
    db.clear_activity()


def clean_domain(url):
    """'https://www.canvas.school.edu/courses/12?x=1' -> 'canvas.school.edu'; None if not a normal site."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    if any(h in host for h in SENSITIVE_DOMAIN_HINTS) or re.fullmatch(r"[\d.]+|localhost", host):
        return None
    return host


def _osascript(script, timeout=3):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _idle_seconds():
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else 0
    except (OSError, subprocess.SubprocessError):
        return 0


def default_sampler():
    """{'app','domain','idle'} for what is in front right now (macOS)."""
    app = _osascript('tell application "System Events" to get name of first application process whose frontmost is true')
    domain = None
    if app in BROWSERS:
        domain = clean_domain(_osascript('tell application "%s" to get %s' % (app, BROWSERS[app])))
    return {"app": app, "domain": domain, "idle": _idle_seconds()}


def record_sample(sample, now=None):
    """Store one sample if it is allowed. Returns True when recorded."""
    now = time.time() if now is None else now
    app = (sample.get("app") or "").strip()
    if not app or app in SKIP_APPS or (sample.get("idle") or 0) > IDLE_LIMIT:
        return False
    db.add_activity_sample(app, sample.get("domain"), now, GAP_SECONDS)
    return True


class ActivityTracker(threading.Thread):
    def __init__(self, sampler=default_sampler, interval=SAMPLE_INTERVAL, clock=time.time):
        super().__init__(daemon=True, name="buddy-activity")
        self.sampler, self.interval, self.clock = sampler, interval, clock
        self._halt = threading.Event()
        self._last_prune = 0.0

    def run(self):
        while not self._halt.wait(self.interval):
            try:
                if is_enabled():
                    record_sample(self.sampler(), self.clock())
                    if self.clock() - self._last_prune > 86400:
                        db.prune_activity(self.clock() - RETENTION_DAYS * 86400)
                        self._last_prune = self.clock()
            except Exception:
                pass  # learning must never disturb the app

    def stop(self):
        self._halt.set()


_tracker = None


def start_tracking():
    global _tracker
    if _tracker is None or not _tracker.is_alive():
        _tracker = ActivityTracker()
        _tracker.start()
    return _tracker


def stop_tracking():
    global _tracker
    if _tracker:
        _tracker.stop()
        _tracker = None
