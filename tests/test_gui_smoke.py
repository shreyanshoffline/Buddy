"""Offscreen smoke test of the new UI pieces (skipped when PySide6 isn't installed)."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    """One window for the whole module: BuddyWindow installs an app-level event filter,
    so creating and discarding several windows in one process isn't safe."""
    from PySide6.QtWidgets import QApplication
    from storage import db
    from core import activity_watcher
    tmp_path = tmp_path_factory.mktemp("gui")
    db._DB_PATH = str(tmp_path / "t.db")
    activity_watcher.CONSENT_FLAG_PATH = str(tmp_path / "consent")
    app = QApplication.instance() or QApplication([])
    import core
    core.update_profile(name="Tester", onboarding_complete=1)
    from gui.main_window import BuddyWindow
    w = BuddyWindow()
    w.resize(1000, 700)
    w.show()
    w.show_chat_view()
    app.processEvents()
    yield w, app
    w._screen_glow.stop()
    db._DB_PATH = None


def test_new_chat_shows_three_chips_and_opt_in_note(window):
    w, app = window
    labels = w.suggestion_bar.labels()
    assert len(labels) == 3 and all(l.strip() for l in labels)
    assert not w.suggestion_bar._note.isHidden()                      # not learning yet: offers to start, never assumes


def test_clicking_a_chip_sends_its_prompt(window, monkeypatch):
    w, _ = window
    sent = []
    monkeypatch.setattr(w, "handle_send", lambda text=None: sent.append(text))
    w.suggestion_bar._buttons[0].click()
    assert sent and isinstance(sent[0], str) and len(sent[0]) > 5


def test_live_action_log_shows_full_call_and_result(window):
    from gui.widgets.chat_bubble import ChatBubble
    w, app = window
    w.scroll_area.setVisible(True)
    w._thinking_bubble = ChatBubble(is_user=False, is_thinking=True)
    w.chat_layout.insertWidget(w.chat_layout.count() - 1, w._thinking_bubble)
    w._screen_glow.start()
    call = 'code_run(folder="/p", command="python3 -m pytest -q", timeout=60, headless=true)'
    w._on_send_progress({"type": "step_start", "label": "5/5", "tier": "medium", "model": "anthropic/claude-haiku-5.5", "title": "Verify"})
    w._on_send_progress({"type": "tool_call", "name": "code_run", "call": call, "tier": "medium"})
    assert call in w._thinking_bubble.thinking_current_label.text().replace("&quot;", '"')
    w._on_send_progress({"type": "tool_done", "name": "code_run", "call": call, "ok": False, "duration": 2.5, "result": "exit code 1 · 1 failed", "tier": "medium"})
    app.processEvents()
    texts = [w._thinking_bubble.thinking_history_layout.itemAt(i).widget().text() for i in range(w._thinking_bubble.thinking_history_layout.count())]
    joined = " ".join(texts)
    assert "Step 5/5" in joined and "Medium" in joined and "headless=true" in joined and "exit code 1" in joined and "2.5s" in joined
    assert w._screen_glow._flash is not None                           # failure flashes red


def test_glow_modes_and_finish(window):
    w, app = window
    g = w._screen_glow
    g.start()
    g.set_mode("working", "heavy")
    assert g._target == (168, 85, 247)
    g.set_mode("working", "easy")
    assert g._target == (20, 184, 166)
    g.finish(True)
    assert g._flash is not None and g._fading
