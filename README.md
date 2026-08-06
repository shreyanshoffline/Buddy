# Buddy v0.0.1

Buddy is a voice-of-Jarvis-style AI assistant for macOS, built by Shreyansh Patra ("Shrey") using [Hack Club's Hack AI](https://ai.hackclub.com/). It controls apps, browses the web, manages files, and operates the system — all through natural language in the terminal.

Buddy uses a **Manager/Worker architecture**: a cheap "Manager" model interprets what you want and writes a plan, and a "Worker" model executes that plan step-by-step using real tool calls against your Mac.

---

## How it works

```
User input
   │
   ▼
┌─────────────┐   RESPONSE:   ┌──────────────┐
│   Manager    │──────────────▶│ Reply to user│
│ (writes plan │               └──────────────┘
│  or replies) │
└──────┬───────┘
       │ PLAN:
       ▼
┌──────────────┐   tool calls   ┌───────────────┐
│    Worker     │───────────────▶│  tools.py      │
│ (executes plan│                │ (real actions  │
│  step by step)│◀───────────────│  on your Mac)  │
└──────┬────────┘   results      └───────────────┘
       │
       ▼
  finish_task(summary) ──▶ shown to user
```

1. **Manager** reads the conversation and either answers directly (`RESPONSE:`) or writes a numbered step-by-step plan (`PLAN:`).
2. **Worker** receives the plan and calls tools one at a time — opening apps, hitting URLs, moving the cursor, adjusting system settings, etc. — until it calls `finish_task` or hits the step limit.
3. If the Worker rejects a plan outright, the Manager gets one retry with the rejection reason fed back into its context.

---

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Orchestration loop — Manager/Worker phases, retries, conversation state |
| `models.py` | Thin wrapper around the OpenRouter client; owns API key and model calls |
| `tools.py` | Real implementations of every action Buddy can take (subprocess/AppleScript/pyautogui) |
| `tools_schema.py` | JSON-Schema tool definitions describing each tool to the models |
| `instruction.py` | System prompts for the Manager and Worker roles |
| `.env` | Local secrets (API key) — never committed |

---

## Setup

```bash
pip install python-dotenv pyautogui
```

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=sk-hc-v1-your-key-here
```

Run it:

```bash
python3 main.py
```

Type `quit` or `exit`, or press `Control + C`, to stop.

---

## What Buddy can do

- **Apps** — open, close, force-close, maximize, minimize, list installed/running apps
- **Web** — open URLs, manage tabs/windows, browser history, undo/redo (Chrome-first by policy)
- **Coding** — run/test Python scripts, open folders in VS Code, install/update/uninstall packages, create/delete files
- **System** — screenshots, screen recording, volume, dark mode, sleep/lock/restart/shutdown/log out (destructive actions require confirmation)
- **Input control** — move/click/drag the cursor, scroll, type text, copy/cut/paste, undo/redo, select all, save
- **Spotify** — play/pause/skip, and play saved playlists by name

The full list of callable tools lives in `tools_schema.py`; the logic behind each one is in `tools.py`.

---

## Known limitations

- **No live browser state.** Buddy can't see which tabs are actually open — "close tab" style commands work off a URL keyword guess, not real tab awareness. There's no `list_open_tabs` tool yet.
- **`close_tab` is single-browser.** Unlike most web tools, it doesn't take a `browser` argument.
- **Long plans can hit the step limit.** `MAX_WORKER_STEPS` caps how many tool calls one plan can make; hitting it doesn't currently preserve partial progress, so a follow-up "finish the rest" request may restart the plan from scratch.
- **A few tools are stubs.** `set_brightness`, `set_key_glow`, and `toggle_stage_manager` exist in `tools.py` but always return "not supported" — they're intentionally left out of `tools_schema.py` so the model doesn't try to call them.
- **Destructive actions require a confirmation flag** (`restart`, `shutdown`, `log_out`) — the Worker is expected to pass this along rather than assume consent.

---

## Config

Model choice, token limits, and retry/step limits are all defined as constants at the top of `main.py`:

```python
MANAGER_MODEL = "..."      # writes plans / replies
WORKER_MODEL = "..."       # executes tool calls
MANAGER_MAX_TOKENS = 750
WORKER_MAX_TOKENS = 500
MAX_PLAN_RETRIES = 1
MAX_WORKER_STEPS = 10
```

---

## Credits

Built by Shrey using Hack Club's Hack AI. Part of a series of maker projects including a custom QMK macropad ("The Anypad") and several 2D Python games.
