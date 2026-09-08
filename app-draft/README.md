# Buddy app draft

This folder is an isolated first-pass UI revision for the Buddy desktop app.
The original app in the parent folder was not modified.

## What is in this draft

- A `Plugins` page in the sidebar with sections for Universal plugins, Mac apps, Websites, and System permissions.
- Thinking-level controls: Low, Medium, High, Extra, and MAX. Medium is selected by default.
- Voice-chat selectors for Listening (`Gemini 2.5 Flash` or `Whisper · Replicate / Hack Club AI`) and Speaking (`System voice · macOS` or `Inworld`).
- Visual toggles and website management so the direction can be reviewed before wiring permissions, storage, or tools.

## Run the draft

From this folder, use the same environment as the main app:

```bash
python main.py
```

This revision is intentionally UI-only for the new controls. It does not change macOS permissions, connect new plugins, or route model calls differently yet.
