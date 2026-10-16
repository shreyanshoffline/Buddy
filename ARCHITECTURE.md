# Buddy code map

## Runtime source

Run Buddy from the repository root with `python3 main.py`.

- `main.py` starts the application.
- `backend/runtime.py` starts one local backend in a daemon thread when the desktop app launches.
- `backend/app.py` owns backend routes and billing/OAuth persistence; it can also be deployed independently.
- `gui/` contains the active PySide6 window and pages.
- `gui/pages/memory_page.py` is the active memory control surface; the experimental model workflow lives only under `future/model_workflow/`.
- `core/` contains conversation orchestration, plugin gating, and updates.
- `storage/` owns the SQLite database and migrations.
- `tools/platform_support.py` is the shared OS boundary for opening apps, URLs, paths, and listing processes.
- `tools/` contains provider clients and OS-specific tools. `tools/apple_tools.py` is macOS-only and gated by Plugins.
- `tests/` contains offline regression tests.

## Data

User data belongs in the OS-specific application data directory, not in the source tree:

- macOS: `~/Library/Application Support/Buddy/`
- Windows: `%APPDATA%/Buddy/`
- Linux/ChromeOS: `$XDG_DATA_HOME/Buddy/` or `~/.local/share/Buddy/`

This includes the database, OAuth caches, and local provider settings.

## Project hygiene

The repository keeps one active runtime tree. New production code belongs in
the active directories listed above. Historical snapshots and generated local
artifacts are intentionally excluded so there is one obvious place to edit.

## Runtime flow

```text
python3 main.py
  ├─ start_local_backend()   -> http://127.0.0.1:5000 (optional, one process)
  ├─ start QApplication       -> shared PySide6 UI
  ├─ chat -> core -> tools   -> model/provider/OS adapter
  ├─ Memory -> storage/db    -> category preferences + local facts/lessons
  └─ quit -> stop backend + activity tracking
```

`BUDDY_START_BACKEND=0` disables the local service. `BUDDY_BACKEND_HOST` and
`BUDDY_BACKEND_PORT` customize its bind address for local testing.
