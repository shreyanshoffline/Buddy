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


def test_narrow_chat_keeps_wrapped_greeting_and_chips_inside_page(window):
    w, app = window
    w.resize(380, 520)
    w.show_chat_view()
    w.greeting.setText("Hi, how can I help you Shreyansh Petra?")
    items = list(w.suggestion_bar._items)
    for _ in range(8):
        w.suggestion_bar.set_suggestions(items, show_opt_in=True)
    app.processEvents()

    assert w.content_stack.graphicsEffect() is None
    assert w.content_stack.rect().contains(w.chat_page.geometry())
    assert w.chat_page.rect().contains(w.composer.geometry())
    assert abs(w.greeting.width() - (w.chat_page.contentsRect().width() - 32)) <= 2    # font metrics differ per OS
    assert w.greeting.height() + 2 >= w.greeting.heightForWidth(w.greeting.width())  # tall enough for the wrapped text
    assert w.suggestion_bar._note.geometry().bottom() <= w.suggestion_bar.height()
    assert all(w.suggestion_bar.rect().contains(button.geometry()) for button in w.suggestion_bar._buttons)
    assert all(
        button in w.suggestion_bar._buttons or button is w.suggestion_bar._opt or not button.isVisible()
        for button in w.suggestion_bar.findChildren(type(w.suggestion_bar._buttons[0]))
    )
    assert all(
        w.suggestion_bar.rect().contains(button.geometry())
        for button in w.suggestion_bar.findChildren(type(w.suggestion_bar._buttons[0]))
        if button.isVisible()
    )

    # Hovering must not cause a chip to be reparented or left with its
    # unlaid-out default geometry.
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    for button in w.suggestion_bar._buttons:
        QTest.mouseMove(button, QPoint(2, 2))
        app.processEvents()
        assert button.isVisible()
        assert w.suggestion_bar.rect().contains(button.geometry())
    w.resize(1000, 700)
    app.processEvents()


def test_clicking_a_chip_sends_its_prompt(window, monkeypatch):
    w, _ = window
    sent = []
    monkeypatch.setattr(w, "handle_send", lambda text=None: sent.append(text))
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(w.suggestion_bar._buttons[0], Qt.LeftButton)
    assert sent and isinstance(sent[0], str) and len(sent[0]) > 5
    assert w._screen_glow._interaction is not None


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
    g.pulse()
    assert g._interaction is not None
    g.stop()
    g.start()
    g.set_mode("working", "heavy")
    assert g._target == (168, 85, 247)
    g.set_mode("working", "easy")
    assert g._target == (20, 184, 166)
    g.finish(True)
    assert g._flash is not None and g._fading


def test_memory_page_replaces_model_workflow(window):
    w, app = window
    assert hasattr(w.sidebar, "btn_memory")
    assert not hasattr(w.sidebar, "btn_models")
    w.show_memory_view()
    app.processEvents()
    assert w.content_stack.currentWidget() is w.memory_page
    assert set(w.memory_page._category_widgets) >= {
        "relationships", "work_patterns", "preferences", "important", "communication"
    }
    w.show_chat_view()


def test_finished_work_log_is_closed_with_a_dropdown_per_tool_call(window):
    from gui.widgets.chat_bubble import DevChamber, _Fold
    from PySide6.QtWidgets import QLabel
    w, app = window
    long_result = "all details " * 120
    chamber = DevChamber(
        plan_text="1. Do the work",
        tool_log=[{"name": "inspect", "args": {"path": "/tmp/example"}, "result": long_result, "duration": "0.4s"}],
    )
    w.chat_layout.insertWidget(w.chat_layout.count() - 1, chamber)
    app.processEvents()
    assert not chamber.toggle_btn.isChecked()            # closed by default
    folds = chamber.findChildren(_Fold)
    assert len(folds) == 2                               # one for the plan, one per tool call
    call = folds[1]
    assert not call.body.isVisible()
    assert "inspect" in call.btn.text() and call.btn.text().startswith("▸")
    call.btn.click()                                     # opening it reveals call + result
    assert call.btn.text().startswith("▾")
    assert any("all details" in label.text() for label in call.body.findChildren(QLabel)) or "all details" in call.body.text()
    chamber.deleteLater()
