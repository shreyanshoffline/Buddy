# Buddy — Refactored + De-personalized (HackyBuddy-ready)

## Structure
```
buddy/
├── main.py                # entry point
├── models.py               # LLM client + embeddings; now supports BYOK
├── core/
│   ├── agent.py              # Manager/Worker pipeline
│   ├── conversations.py      # db-facing orchestration
│   └── instruction.py        # NOW a template system, not a static string
├── storage/db.py
├── tools/ (tools.py, tools_schema.py, gmail_tools.py stub)
└── gui/ (main_window.py, theme.py, icons.py, sidebar.py, pages/, widgets/)
```

## This session's fixes (in order)

### 1. "Buddy thinking forever" / can't pause — FIXED
Root cause: zero timeout on any OpenRouter call. A stuck connection blocked
the worker thread forever, and Stop could only interrupt between calls, not
during one. Added a 30s hard timeout to every model/embedding call, made
retry backoff cancellable (polls every 0.25s), and threaded cancel_check
through send AND redo (redo had no cancel support at all before).

### 2. Dead code from the original file split — FIXED
A full duplicate of FlowLayout's methods had leaked into chat_bubble.py
(orphaned, no class wrapper — harmless at runtime but a landmine). Removed.
Swept every other split file for the same pattern; nowhere else affected.

### 3. Redo was silently broken — FIXED
Clicking redo fed the assistant's own previous reply back in as the "user"
message instead of re-asking the original question — every redo, the whole
time. Also: redo was completely dead after closing and reopening a chat
(hardcoded `lambda: None`). Both fixed and tested against the real GUI
thread, not just unit-level.

### 4. No thread cleanup on quit — FIXED
Quitting while a send/redo was in flight could crash (`QThread: Destroyed
while thread still running`). Added a shutdown hook that signals the
worker and waits up to 3s. Verified under a real Qt event loop with a
deliberately slow in-flight call.

### 5. Tool execution log — ADDED
DevChamber now shows a full per-call breakdown (name, args, result,
duration), not just a flat list of tool names. Falls back gracefully for
old saved messages that predate this.

### 6. Private chat lock did nothing — FIXED
Was a cosmetic flag; clicking a "locked" chat opened it anyway. Now:
- Sidebar Recents fully excludes private chats.
- Opening one always requires confirmation — a PIN if you've set one in
  Settings (SHA-256 hashed, never exposed back out), otherwise an honest
  "this isn't actually protected, open anyway?" warning.
- Tested all 6 branches directly against the real dialog classes.

### 7. Nobody knew what the glasses/lock icons did — FIXED
Added a one-time "Welcome to Buddy" explainer shown on first-ever launch
(tracked via has_seen_intro_tip in the profile), plus the tooltips that
were already there. Verified it fires exactly once.

### 8. Settings fields didn't do anything — FIXED
- **API key**: was saved to the db and never read anywhere. Now models.py
  checks the user's own key first, falls back to the app default, rebuilds
  the client only when the key actually changes.
- Added **Favorite Apps** and **Quick Links** fields that feed directly
  into the system prompt's "open my usual stuff" behavior — omitted
  entirely if unset, never invented.
- Added a real **Privacy PIN** control (set/clear, tested both ways).
- Added a real **Clear All Chat History** button (destructive, confirmed,
  tested that Cancel actually preserves data).

### 9. Hardcoded to "Shrey" everywhere — FIXED (the big one)
core/instruction.py was a static string with Shrey's real age, birthday,
location, and personal Hack Club bookmarks baked in — every user's Buddy
would introduce itself with someone else's biography. Converted to
`build_manager_instruction(profile)` / `build_action_instruction(profile)`:
- Only mentions age/bio if the current user actually filled them in.
- Only shows App Defaults / Quick Links if the current user configured
  them — never leaks or invents another person's setup.
- Fixed gendered pronouns throughout.
- Kept "Creator: Shreyansh Patra" as a permanent, honest attribution —
  that's just true regardless of who's using it.
- Greeting on the chat screen now uses the real saved name, with a
  friendly generic fallback for a fresh install.

Tested against both an empty profile (fresh HackyBuddy install — verified
zero personal-info leakage, nothing invented) and a fully populated one.

## Known remaining gaps (not fixed this session, flagged honestly)
- `tools/gmail_tools.py` is still a stub.
- No real macOS-level testing of tools.py's pyautogui/AppleScript calls
  (needs a real Mac).
- Age field isn't validated as numeric — stored as whatever text is typed.
- Memory bank UI and embedding-model migration are still not started.

## Tested this session (real execution, not just syntax checks)
11-point full regression suite covering: GUI construction, incognito,
send+feedback, redo (fresh AND after reload), search, cancellation,
private-chat gate (both outcomes), sidebar exclusion, BYOK, and
personalization — all passing. Settings page has its own 7-point suite
covering every new field and the two destructive actions.
