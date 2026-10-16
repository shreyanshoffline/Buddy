"""Memory categories stay local, editable, and enforce their privacy switches."""

from storage import db


def test_memory_category_switch_controls_save_update_and_retrieval(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", str(tmp_path / "buddy.db"))
    monkeypatch.setattr(db, "_safe_embed", lambda _texts: None)
    db.init_db()

    fact_id = db.save_memory_fact("The user prefers concise project updates.", "communication")
    assert fact_id is not None
    assert db.find_relevant_facts("project updates", limit=5)

    db.set_memory_preference("communication", False)
    assert db.save_memory_fact("Use a different tone.", "communication") is None
    assert db.find_relevant_facts("project updates", limit=5) == []
    assert db.update_memory_fact(fact_id, "Updated preference.")

    db.set_memory_preference("communication", True)
    assert db.delete_memory_fact(fact_id)
    assert db.list_memory_facts() == []
