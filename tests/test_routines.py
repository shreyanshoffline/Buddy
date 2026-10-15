"""Activity learning: privacy filters, session merging, and pattern -> suggestion rules."""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.agent  # noqa: E402,F401
from core import activity, routines  # noqa: E402
from storage import db  # noqa: E402

WED = datetime(2026, 10, 14, 6, 5)      # a Wednesday morning
SAT = datetime(2026, 10, 17, 6, 5)


import pytest  # noqa: E402
from core import activity_watcher  # noqa: E402


@pytest.fixture(autouse=True)
def consent_flag(tmp_path, monkeypatch):
    """Learning is opt-in: point the consent flag at a temp file; tests opt in explicitly."""
    monkeypatch.setattr(activity_watcher, "CONSENT_FLAG_PATH", str(tmp_path / "consent"))
    monkeypatch.setattr(db, "_DB_PATH", str(tmp_path / "t.db"))


def _school_sessions(days_back, hour=6, minute=0):
    """Weekday morning school routine on the previous `days_back` weekdays before WED."""
    out, d, got = [], WED.date(), 0
    while got < days_back:
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        got += 1
        t = datetime(d.year, d.month, d.day, hour, minute)
        for i, (app, dom) in enumerate([("Google Chrome", "canvas.myschool.edu"), ("Google Chrome", "quizlet.com"), ("Notability", None)]):
            s = t + timedelta(minutes=10 * i)
            out.append({"app": app, "domain": dom, "start_ts": s.timestamp(), "end_ts": (s + timedelta(minutes=9)).timestamp()})
    return out


def test_routine_appears_only_after_it_repeats():
    assert routines.routine_suggestions(_school_sessions(2), WED) == []                       # too early: stays quiet
    got = routines.routine_suggestions(_school_sessions(3), WED)
    assert got and got[0]["label"] == "Start my school setup"
    assert "https://canvas.myschool.edu" in got[0]["prompt"] and "Notability" in got[0]["prompt"]
    assert "weekdays" in got[0]["reason"]


def test_weekday_routine_is_not_suggested_on_weekend_or_wrong_hour():
    s = _school_sessions(8)
    assert routines.routine_suggestions(s, SAT) == []
    assert routines.routine_suggestions(s, datetime(2026, 10, 14, 15, 0)) == []              # 3 PM is not 6 AM
    assert routines.routine_suggestions(s, datetime(2026, 10, 14, 6, 50))                    # inside the +-90 min window


def test_todays_own_usage_does_not_create_the_habit():
    today = [{"app": "Notability", "domain": None, "start_ts": WED.replace(hour=5).timestamp(), "end_ts": WED.replace(hour=5, minute=30).timestamp()}]
    assert routines.habits(today, WED) == []


def test_build_suggestions_mixes_routine_repeat_and_defaults():
    prompts = ["summarize my unread emails"] * 4 + ["something else entirely different"]
    out = routines.build_suggestions(WED, sessions=_school_sessions(6), prompts=prompts, connected={"gmail", "google"})
    assert len(out) == 3
    assert out[0]["kind"] == "routine" and any(o["kind"] == "repeat" for o in out)
    cold = routines.build_suggestions(WED, sessions=[], prompts=[], connected=set(), has_location=False)
    assert len(cold) == 3 and all(c["kind"] == "default" for c in cold)                        # new user still gets useful chips
    lunch = routines.build_suggestions(datetime(2026, 10, 14, 12, 0), sessions=[], prompts=[], has_location=True)
    assert any("lunch" in s["label"].lower() for s in lunch)


def test_context_line_for_the_model():
    line = routines.context_line(WED, _school_sessions(6))
    assert line.startswith("Routine:") and "canvas.myschool.edu" in line and len(line) < 300
    assert routines.context_line(WED, []) == ""


def test_domain_and_app_privacy_filters(tmp_path, monkeypatch):
    assert activity.clean_domain("https://www.canvas.myschool.edu/courses/1?token=abc") == "canvas.myschool.edu"   # no path/query kept
    for bad in ("https://secure.chase.com/x", "https://mychart.hospital.org", "http://localhost:8000", "http://192.168.1.1", "file:///etc/passwd"):
        assert activity.clean_domain(bad) is None
    assert not activity.record_sample({"app": "1Password", "domain": None, "idle": 0}, 1000)
    assert not activity.record_sample({"app": "Notability", "domain": None, "idle": 999}, 1000)    # idle
    assert activity.record_sample({"app": "Notability", "domain": None, "idle": 1}, 1000)


def test_sessions_merge_and_can_be_wiped(tmp_path, monkeypatch):
    t = time.time()
    for i in range(5):
        activity.record_sample({"app": "Xcode", "domain": None, "idle": 0}, t + i * 20)
    activity.record_sample({"app": "Safari", "domain": "github.com", "idle": 0}, t + 100)
    rows = db.list_activity(0)
    assert len(rows) == 2 and rows[0]["end_ts"] - rows[0]["start_ts"] == 80                     # merged into one session
    assert "path" not in rows[0] and set(rows[0]) == {"app", "domain", "start_ts", "end_ts"}   # nothing but names + times
    activity.clear_all()
    assert db.list_activity(0) == []


def test_tracker_thread_records_and_respects_toggle(tmp_path, monkeypatch):
    tr = activity.ActivityTracker(sampler=lambda: {"app": "Notes", "domain": None, "idle": 0}, interval=0.05)
    tr.start()
    time.sleep(0.25)
    assert db.list_activity(0) == []                                                           # no consent -> nothing recorded
    activity.set_enabled(True)
    time.sleep(0.3)
    assert db.list_activity(0)                                                                 # opted in -> learning starts
    activity.set_enabled(False)
    activity.clear_all()
    time.sleep(0.25)
    assert db.list_activity(0) == []                                                           # opted out -> stops
    tr.stop()
    tr.join(1)


def test_forget_button_wipes_sessions_too(tmp_path):
    activity.set_enabled(True)
    activity.record_sample({"app": "Notes", "domain": None, "idle": 0}, time.time())
    assert db.list_activity(0)
    assert "app/website sessions" in activity_watcher.forget_everything()
    assert db.list_activity(0) == []
