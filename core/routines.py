"""Turns local activity history into helpful, honest suggestions.

Everything here is deterministic and offline: no model calls, no cost. A routine is suggested
only after it has really repeated (>= MIN_DAYS different days at about this time of day on the
same kind of day), so Buddy "slowly" earns its suggestions instead of guessing.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from storage import db

LOOKBACK_DAYS = 28
ELIGIBLE_DAYS = 21
WINDOW_MINUTES = 90
MIN_DAYS = 3
MIN_COVERAGE = 0.4

# (category, label, app keywords, domain keywords). First match wins; keywords are lowercase substrings.
CATEGORIES = (
    ("school", "school", ("canvas", "classroom", "notability", "anki", "quizlet", "goodnotes"),
     ("canvas", "instructure", "classroom.google", "khanacademy", "quizlet", "schoology", "blackboard", "powerschool",
      "clever", "desmos", "coursera", "edx", "studyisland", "ixl", "duolingo", ".edu")),
    ("maker", "maker", ("kicad", "arduino", "fusion", "prusa", "cura", "bambu", "freecad", "easyeda"),
     ("easyeda", "jlcpcb", "digikey", "mouser", "thingiverse", "printables", "hackclub", "kicad", "adafruit", "sparkfun")),
    ("coding", "coding", ("xcode", "visual studio code", "code", "terminal", "iterm", "pycharm", "cursor", "sublime", "docker", "warp"),
     ("github", "gitlab", "stackoverflow", "developer.apple", "docs.python", "replit", "codepen", "npmjs", "pypi", "vercel", "openrouter")),
    ("creative", "creative", ("figma", "photoshop", "illustrator", "final cut", "logic pro", "garageband", "blender", "pixelmator", "canva", "procreate"),
     ("figma", "canva", "behance", "dribbble")),
    ("work", "work", ("microsoft word", "microsoft excel", "microsoft powerpoint", "pages", "numbers", "keynote", "notion", "obsidian", "zoom", "teams", "calendar"),
     ("notion", "docs.google", "sheets.google", "slides.google", "drive.google", "zoom.us", "teams.microsoft", "office.com", "linear.app", "trello", "asana")),
    ("communication", "communication", ("messages", "slack", "discord", "whatsapp", "telegram", "mail", "outlook"),
     ("mail.google", "outlook", "discord", "slack", "web.whatsapp")),
    ("entertainment", "entertainment", ("spotify", "music", "tv", "vlc", "quicktime", "netflix", "steam"),
     ("netflix", "youtube", "twitch", "spotify", "disneyplus", "hulu", "reddit", "instagram", "tiktok", "x.com", "twitter")),
)


def categorize(app, domain):
    app_l, dom_l = (app or "").lower(), (domain or "").lower()
    for key, label, app_keys, dom_keys in CATEGORIES:
        if dom_l and any(k in dom_l for k in dom_keys):
            return key, label
        if not dom_l and any(app_l == k or app_l.startswith(k + " ") or k in app_l for k in app_keys if len(k) > 3 or app_l == k):
            return key, label
    return None, None


def _item(session):
    """A session is identified by its website when it has one, else by the app."""
    return ("site", session["domain"]) if session.get("domain") else ("app", session["app"])


def _local(ts):
    return datetime.fromtimestamp(ts)


def habits(sessions, now, window=WINDOW_MINUTES, min_days=MIN_DAYS):
    """Items regularly used around this time of day on this kind of day (weekday/weekend)."""
    weekend = now.weekday() >= 5
    target = now.hour * 60 + now.minute
    today = now.date()
    first = min((_local(s["start_ts"]).date() for s in sessions), default=today)
    start_day = max(first, today - timedelta(days=ELIGIBLE_DAYS))
    eligible = sum(1 for i in range((today - start_day).days)
                   if ((start_day + timedelta(days=i)).weekday() >= 5) == weekend)
    found = defaultdict(set)
    seconds = Counter()
    for s in sessions:
        start = _local(s["start_ts"])
        if start.date() == today or (start.weekday() >= 5) != weekend:
            continue
        minute = start.hour * 60 + start.minute
        if abs(minute - target) > window:
            continue
        key = _item(s)
        found[key].add(start.date())
        seconds[key] += max(0, s["end_ts"] - s["start_ts"])
    out = []
    for key, days in found.items():
        if len(days) >= min_days and eligible and len(days) / eligible >= MIN_COVERAGE:
            out.append({"item": key, "days": len(days), "coverage": len(days) / eligible, "seconds": seconds[key]})
    return sorted(out, key=lambda h: (-h["days"], -h["seconds"]))


def routine_suggestions(sessions, now):
    by_cat = defaultdict(list)
    for h in habits(sessions, now):
        kind, name = h["item"]
        cat, label = categorize(name if kind == "app" else "", name if kind == "site" else "")
        if cat:
            by_cat[(cat, label)].append(h)
    out = []
    for (cat, label), items in by_cat.items():
        if len(items) < 2 and items[0]["days"] < 5:
            continue  # one weak signal isn't a routine yet
        top = items[:4]
        parts = [("https://" + n) if k == "site" else n for k, n in (i["item"] for i in top)]
        days = max(i["days"] for i in top)
        kind_of_day = "weekends" if now.weekday() >= 5 else "weekdays"
        out.append({
            "kind": "routine",
            "label": "Start my %s setup" % label,
            "prompt": "Open my usual %s setup: %s." % (label, ", ".join(parts)),
            "reason": "You usually do this around now on %s (seen %d days)." % (kind_of_day, days),
            "score": days * 10 + len(top),
        })
    return sorted(out, key=lambda s: -s["score"])


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (text or "").lower())).strip()


def repeated_prompt_suggestions(prompts, min_count=3):
    counts = Counter()
    original = {}
    for p in prompts:
        n = _norm(p)
        if 6 <= len(n) <= 80 and len(p) <= 120:
            counts[n] += 1
            original.setdefault(n, p.strip())
    out = []
    for n, c in counts.most_common(3):
        if c >= min_count:
            text = original[n]
            out.append({"kind": "repeat", "label": text if len(text) <= 38 else text[:36].rstrip() + "…",
                        "prompt": text, "reason": "You've asked this %d times." % c, "score": c})
    return out


def time_defaults(now, connected=(), has_location=False):
    h = now.hour
    cal = bool({"google", "microsoft"} & set(connected))
    out = []
    if 5 <= h < 11:
        out.append(("What's on my schedule today?" if cal else "Help me plan my day", "Plan my day"))
    if 11 <= h < 14 and has_location:
        out.append(("Find good lunch spots near me", "Lunch near me"))
    if 12 <= h < 18 and "google" in connected:
        out.append(("Summarize my unread emails", "Catch up on email"))
    if h >= 17 or h < 5:
        out.append(("Help me plan tomorrow", "Plan tomorrow"))
    out += [("Help me get focused: what should I do first?", "Help me focus"),
            ("What can you do on my Mac?", "What can you do?")]
    # Keep the new-chat surface useful and stable throughout the day.  The
    # time/location branches above are optional, so add one neutral third chip
    # when none of them applied.
    if len(out) < 3:
        out.append(("Help me plan my day", "Plan my day"))
    return [{"kind": "default", "label": label, "prompt": prompt, "reason": "", "score": 0} for prompt, label in out]


def build_suggestions(now=None, limit=3, connected=(), has_location=False, sessions=None, prompts=None):
    now = now or datetime.now()
    if sessions is None:
        sessions = db.list_activity((now - timedelta(days=LOOKBACK_DAYS)).timestamp())
    if prompts is None:
        prompts = db.recent_user_prompts((now - timedelta(days=45)).timestamp())
    chosen = routine_suggestions(sessions, now)[:2]
    chosen += repeated_prompt_suggestions(prompts)[:1]
    seen = {s["label"] for s in chosen}
    for d in time_defaults(now, connected, has_location):
        if len(chosen) >= limit:
            break
        if d["label"] not in seen:
            chosen.append(d)
            seen.add(d["label"])
    return chosen[:limit]


def context_line(now=None, sessions=None):
    """One short line for the model: what this user usually does around now. '' when unknown."""
    now = now or datetime.now()
    if sessions is None:
        sessions = db.list_activity((now - timedelta(days=LOOKBACK_DAYS)).timestamp())
    hs = habits(sessions, now)
    if not hs:
        return ""
    names = ", ".join(n for _, n in (h["item"] for h in hs[:4]))
    return "Routine: around %s on %s this user usually uses %s." % (
        now.strftime("%-I:%M %p"), "weekends" if now.weekday() >= 5 else "weekdays", names)
