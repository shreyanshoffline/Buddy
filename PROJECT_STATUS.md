# Buddy Project Status

## Runtime layout

- `main.py` starts the app.
- `backend/` contains the optional local Flask service; `main.py` starts and stops it automatically.
- `gui/` contains the active PySide6 interface.
- `core/` contains agent orchestration, prompts, plugin gates, and updates.
- `storage/` owns SQLite and migrations.
- `tools/` contains provider clients, shared desktop adapters, and Apple-only tools.
- `future/model_workflow/` preserves the removed experimental model workflow without importing it into the active app.
- `tests/` contains offline regression tests.
- `knowledge/` contains focused provider and Mac guides.

User data belongs in the OS-specific application-data directory, not the source tree.

## Current release checklist

Before publishing a macOS release:

- Run `python3 -m pytest -q tests`.
- Run `python3 -m tools.release_manager check`.
- Run `python3 packaging/build_nuitka.py` on macOS, Windows, or Linux.
- Open `dist/Buddy.app` and test chat, Plugins, Talk, Settings, updates, and memory preservation.
- Verify microphone, Files & Folders, and Full Disk Access behavior in the packaged app.
- Test Google, Microsoft, Slack, GitHub, and Gmail with real credentials where configured.
- Confirm the update replaces the app without deleting `~/Library/Application Support/Buddy/`.

The free build is ad-hoc signed. Developer ID signing and notarization are optional and require Apple credentials.

## Next steps until the testing stage

1. Run the shared offline suite on a clean Python 3.12 environment:

   ```bash
   python3 -m pytest -q tests
   ```

2. Smoke-test one-command startup on macOS, Windows, Linux, and ChromeOS Linux:

   ```bash
   python3 main.py
   ```

   Confirm the window opens, the local backend health check responds, and the app exits without leaving a backend process behind.

3. Build each release target:

   - macOS/Windows/Linux: `python packaging/build_nuitka.py`
   - ChromeOS: run the Linux build inside the Linux development environment.

4. Test one real workflow per capability family: chat, attachment preview, image creation, browser navigation, a Google or Microsoft action, Slack read/post with confirmation, local file action, and software update discovery.

5. Record platform-specific gaps instead of silently treating them as failures. Apple-only actions should be unavailable with an explanation; common browser, file, web, provider, and memory workflows should behave the same.

6. Before publishing, rotate any local credentials that were ever shared, confirm ignored files are absent from Git, create a version tag from `version.py`, and verify every uploaded ZIP opens on its target platform.

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
- Tiered execution (`core/tiers.py`, `core/staged.py`): big jobs are split into easy/medium/heavy steps; each step runs on its selected model with a short brief, so the heavy model is billed only for writing real code or long text. Coding mode plans with a cheap model first; failed verify steps escalate to heavy for the fix. Manager plans can tag steps `[easy_task]/[medium_task]/[heavy_task]`. Long-form writing (essays, stories) uses the heavy model with a real token budget. Stats show calls per tier and an estimated cost (price table in `core/tiers.py` is an estimate; edit it).
- Live action log: the thinking bubble shows every observable step, tool call, full available parameters, result, and timing while Buddy works. Completed replies keep the full selectable work log open by default. Screen-edge glow covers the full virtual desktop: calm blue while thinking, tier colour + travelling light while working, green/red flash on finish.
- Memory controls: the Memory tab exposes five local categories, category switches, learned work rules, fact editing, and confirmation-protected deletion.
- Routine learning (`core/activity.py`, `core/routines.py`): when the user has opted in (existing Settings switch, off by default) Buddy records app names, website host names and times only, then shows 3 chips on a new chat (e.g. "Start my school setup") once a routine has repeated on 3+ days. Deterministic, no model cost. Skips idle time, password managers, banking/health/login sites. "Forget my activity data" wipes it. A one-line routine summary is also given to the model.
- Coding mode (`core/coding_agent.py`, `tools/code_agent.py`, `knowledge/coding.md`): build, test, fix, and upgrade software autonomously (60 steps, 8000 tokens/step, 20 min, real execution feedback, undo without git). Needs Files & Folders and Terminal enabled in Plugins. Reference output: `examples/space_invaders/`.
- Provider boundary (`models.py`): OpenRouter remains the default, while `BUDDY_AI_PROVIDER=self_hosted` can route the same chat, manager, tool, and coding pipelines to an OpenAI-compatible model server. Image generation remains separately configurable, and memory falls back to local keyword retrieval when no self-hosted embedding model exists.

## Known gaps

- The voice pipeline is still record, transcribe, generate, and speak rather than fully streaming.
- Real signed-app permission and provider tests require a packaged build and live accounts.
- macOS may warn on first launch because the free build is not notarized.
- Qt stylesheet warnings and full accessibility review still need a real GUI run.
- `tools/tools.py` and the generated tool schema remain large and deserve future modularization.
- The archived model workflow is intentionally not part of the current UI; it needs a clearer product purpose before returning.
- Non-macOS native automation is intentionally limited to shared desktop operations until dedicated OS adapters are tested.

- Coding mode has been verified with a scripted model and the real tools (21 tests), not yet with a live model run on a Mac. Try: "build me a space invaders game" and "go into ~/path/to/project and add type hints and error handling".
- Self-hosted provider evaluation is still required before changing the public default: benchmark response quality, tool-call reliability, coding completion, CPU speed, memory use, rate limiting, and recovery on the target Nest VM.
- Nuitka release packaging is wired into `.github/workflows/release.yml` with `--standalone` and the PySide6 plugin. PyInstaller remains the local fallback.

## Useful commands

```bash
python3 -m pytest -q tests
python3 -m tools.release_manager check
python3 packaging/build_nuitka.py
python3 main.py
```

Historical source snapshots were removed from the repository. New production changes belong in the active runtime directories above.
