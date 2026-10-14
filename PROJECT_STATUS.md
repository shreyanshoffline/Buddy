# Buddy Project Status

## Runtime layout

- `main.py` starts the app.
- `gui/` contains the active PySide6 interface.
- `core/` contains agent orchestration, prompts, plugin gates, and updates.
- `storage/` owns SQLite and migrations.
- `tools/` contains provider clients and local Mac tools.
- `tests/` contains offline regression tests.
- `knowledge/` contains focused provider and Mac guides.

User data belongs in `~/Library/Application Support/Buddy/`, not the source tree.

## Current release checklist

Before publishing a macOS release:

- Run `python3 -m pytest -q tests`.
- Run `python3 -m tools.release_manager check`.
- Run `bash packaging/build_mac.sh` on macOS.
- Open `dist/Buddy.app` and test chat, Plugins, Talk, Settings, updates, and memory preservation.
- Verify microphone, Files & Folders, and Full Disk Access behavior in the packaged app.
- Test Google, Microsoft, Slack, GitHub, and Gmail with real credentials where configured.
- Confirm the update replaces the app without deleting `~/Library/Application Support/Buddy/`.

The free build is ad-hoc signed. Developer ID signing and notarization are optional and require Apple credentials.

## Implemented foundations

- SQLite schema migrations and recovery.
- Persistent conversations, memories, profile, plugin settings, and confirmed location.
- Explicit provider errors instead of hidden retries or unrelated Terminal workarounds.
- GitHub Releases update checks, release preflight, and free GitHub Actions packaging.
- Dedicated Software Version settings and startup update hint.
- User-confirmed location for nearby searches.
- Concise voice-mode replies and free macOS system speech.
- Google, Microsoft, Slack, GitHub, and Gmail connection surfaces.
- Modern macOS Messages attributed-body reading for unread group messages.
- Coding mode (`core/coding_agent.py`, `tools/code_agent.py`, `knowledge/coding.md`): build, test, fix, and upgrade software autonomously (60 steps, 8000 tokens/step, 20 min, real execution feedback, undo without git). Needs Files & Folders and Terminal enabled in Plugins. Reference output: `examples/space_invaders/`.

## Known gaps

- The voice pipeline is still record, transcribe, generate, and speak rather than fully streaming.
- Real signed-app permission and provider tests require a packaged build and live accounts.
- macOS may warn on first launch because the free build is not notarized.
- Qt stylesheet warnings and full accessibility review still need a real GUI run.
- `tools/tools.py` and the generated tool schema remain large and deserve future modularization.

- Coding mode has been verified with a scripted model and the real tools (21 tests), not yet with a live model run on a Mac. Try: "build me a space invaders game" and "go into ~/path/to/project and add type hints and error handling".

## Useful commands

```bash
python3 -m pytest -q tests
python3 -m tools.release_manager check
bash packaging/build_mac.sh
python3 main.py
```

Historical source snapshots were removed from the repository. New production changes belong in the active runtime directories above.
