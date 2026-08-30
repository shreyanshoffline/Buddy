# Buddy — Refactored Structure

This is a full reorganization of the codebase. Structure:

```
buddy/
├── main.py                # NEW entry point (was gui_main.py's __main__ block)
├── models.py               # LLM client + embeddings (shared, top-level on purpose —
│                            #   both core/ and storage/ depend on it; keeping it
│                            #   outside both avoids a circular package dependency)
├── core/                   # the "brain" — orchestration only
│   ├── agent.py             # Manager/Worker pipeline (was most of core.py)
│   ├── conversations.py     # db-facing orchestration (was the rest of core.py)
│   └── instruction.py       # unchanged
├── storage/
│   └── db.py                # was storage.py
├── tools/
│   ├── tools.py              # renamed from mac_tools.py
│   ├── tools_schema.py       # renamed from mac_tools_schema.py
│   └── gmail_tools.py        # ⚠️ STUB — was never uploaded, core/agent.py imports
│                              #   get_recent_emails/get_unread_emails/create_draft/
│                              #   list_drafts/modify_draft from it. Replace this file.
└── gui/                     # PySide6 + other gui/ files + `core` ONLY. No storage,
    │                        # no tools, no models imports anywhere in here now.
    ├── main_window.py        # BuddyWindow, SendWorker, RedoWorker (was gui_main.py)
    ├── theme.py               # was settings.py
    ├── icons.py               # was utils.py
    ├── sidebar.py
    ├── pages/                 # NEW home for page classes
    │   ├── card_page.py, settings_page.py, library_page.py
    └── widgets/               # NEW home for reusable chat widgets
        ├── chat_bubble.py, chat_input.py, feedback_dialog.py
```

## What changed behaviorally (bug fixes found while testing this)
1. **`init_db()` ordering bug** (pre-existing, not introduced by this refactor):
   the migration step tried to `ALTER TABLE attachment_chunks` before that
   table was created, on a fresh database. Fixed by moving the migration
   check after the `CREATE TABLE` calls. This same fix was ported back to
   your existing flat `storage.py` too, in case you're not switching to this
   structure right away.
2. `SettingsPage` no longer imports `storage` directly — added
   `core.get_profile()` / `core.update_profile()` wrappers so **every** GUI
   file now only imports PySide6, other `gui/` files, and `core`. Verified
   with a grep pass — zero `storage`/`tools`/`models` imports left in `gui/`.

## How `import core` still works unchanged
`core/__init__.py` re-exports every public function
(`core.process_message`, `core.send_and_save_message`, etc.) so `gui/`
code didn't need any call-site rewrites beyond the file moves themselves.

## To run
```
cd buddy
pip install -r requirements.txt   # PySide6, pypdf, python-dotenv, openrouter
python main.py
```

## Tested (offscreen, mocked model calls — see conversation for exact commands)
- Full package import chain (`import core`, `from gui import BuddyWindow`)
- BuddyWindow construction + page switching (chat/library/settings)
- Incognito pipeline (in-memory, verified nothing hits the db)
- Full db round trip: create conversation → send message → get message_id →
  set feedback → verify persisted → search by content → toggle privacy
- NOT tested: actual PySide6 rendering/visual layout (no display in this
  sandbox), actual OpenRouter/embeddings network calls (mocked), tools.py's
  real OS-level functions (pyautogui etc. — these need a real Mac to test)
