# Buddy code map

## Runtime source

Run Buddy from the repository root with `python3 main.py`.

- `main.py` starts the application.
- `gui/` contains the active PySide6 window and pages.
- `core/` contains conversation orchestration, plugin gating, and updates.
- `storage/` owns the SQLite database and migrations.
- `tools/` contains provider clients and local Mac tools.
- `tests/` contains offline regression tests.

## Data

User data belongs in macOS Application Support, not in the source tree:

`~/Library/Application Support/Buddy/`

This includes the database, OAuth caches, and local provider settings.

## Project hygiene

The repository keeps one active runtime tree. New production code belongs in
the active directories listed above. Historical snapshots and generated local
artifacts are intentionally excluded so there is one obvious place to edit.