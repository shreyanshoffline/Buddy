# Buddy Roadmap to the First macOS Release

This roadmap assumes the first release is a signed, notarized macOS beta that a normal person can install and understand without reading documentation.

## Product rule

Every visible word, icon, switch, and button is a promise. If a five-year-old can reasonably infer that a control does something, the control must do exactly that thing, show its current state, and explain what happens when access or an internet connection is missing.

## Priority order

### 0. Truth pass — immediate

Make the current product honest before adding more surface area.

- Replace fake or ahead-of-wiring integration toggles with real `Connect`, `Connected`, `Disconnect`, or `Unavailable` states.
- Separate “Buddy feature enabled” from “macOS permission granted.” A switch cannot become on until the OS check succeeds.
- Decide whether voice chats are private until saved or automatically saved, then make the copy and Library behavior match.
- Remove dead buttons, “coming later” actions, unexplained symbols, and labels that describe behavior Buddy does not have.
- Fix all Qt stylesheet parser warnings.
- Add one short explanation beside every permission: what Buddy can do, what it cannot do, and how to turn it off.

Definition of done: a control audit can trace every clickable item to a working handler and a truthful state.

### 1. Reliable foundation

Make the core dependable before making it clever.

- Replace the current broad end-to-end harness with isolated tests using a temporary database and deterministic fake providers.
- Add database migrations, schema checks, rollback handling, and a recovery path when a local database is damaged or deleted.
- Make network timeouts and offline states visible in plain language.
- Add a single action-status model: queued, working, waiting for permission, complete, cancelled, or failed.
- Add a “Try again” action that retries only the failed operation.
- Keep every destructive action behind a clear confirmation and provide undo where practical.

Definition of done: deleting local chat data cannot make the app crash or silently lose unrelated profile/settings data.

### 2. Permissions that actually mean permission

Build a small native macOS permission layer and test it on the signed app.

- Check the real process identity, not just a Buddy-local preference.
- Request Microphone and Camera access through the native APIs where available.
- Open the exact System Settings destination for Full Disk Access and Files & Folders.
- After the user returns from Settings, re-check access and keep the Buddy switch off if access was refused.
- For protected file operations, perform a harmless capability probe before enabling the tool.
- Show “Waiting for macOS approval” during the round trip and “Granted” only after verification.
- Explain that access granted to Terminal, VS Code, Python, or another app does not grant access to Buddy.
- Add a first-run capability map so the user chooses access one item at a time.

Definition of done: a signed Buddy.app appears as Buddy in macOS Privacy & Security, and every protected feature passes a grant/refuse/revoke test.

### 3. Real integrations, one at a time

Only expose a service after its connection flow and status check work end to end.

- Gmail: official OAuth, account identity, read-only status check, draft creation, and disconnect.
- GitHub: Device Flow or browser authorization, identity check, repository read access first, and explicit confirmation for writes.
- Web search and weather: real provider calls, timeout handling, source/date display when appropriate, and a clear offline message.
- Slack: connect, show workspace identity, read-only first, then user-confirmed message sending.
- Hack Club: official sign-in/authenticator flow, verified account state, and clear explanation of what the Hack Club connection enables.
- Common app discovery: refresh installed apps from known locations and show “Found” only after the app is actually present.
- Keep provider tokens in macOS Keychain or the provider’s supported secure storage; never put secrets in the regular app database.

Definition of done: each integration has a real Connect button, a real verification result, a visible account/workspace name, and a working Disconnect button.

### 4. Voice as a conversation

Turn the current clip pipeline into a small, explicit state machine:

`Idle → Listening → Thinking → Speaking → Listening`, with `Paused`, `Interrupted`, and `Error` paths.

- Keep the mic available while Buddy speaks so the user can interrupt.
- Add a large, obvious Pause/Resume button and a separate Stop speaking action when those are the current promises.
- Add voice activity detection and a short end-of-utterance delay so the user does not need to tap for every sentence.
- Stream partial transcription so the user can see that Buddy heard them.
- Stream the response and speech where the providers support it.
- Cancel the active TTS process immediately on barge-in.
- Preserve the unsent transcript when a network call fails.
- Add an explicit End voice chat action.
- Make saving a voice conversation an explicit choice if privacy-by-default is selected.
- Tie the blue Buddy animation to measured microphone input and speaker output amplitude; idle must be still and subtle.
- Test interruption latency; target under 300 ms from detected user speech to stopped playback.

Definition of done: a user can naturally speak, interrupt Buddy, pause, resume, end the session, and understand the current state without guessing.

### 5. Thinking and feedback that feel alive

Make waiting understandable without pretending that fake progress is real.

- Show a small blue Buddy that gently thinks while a model request is active.
- Label the current step in plain language: “Listening,” “Thinking,” “Opening Gmail,” “Waiting for permission,” or “Done.”
- Show a compact action receipt after tool use: what Buddy did, where, and whether it succeeded.
- Let the user expand details, but keep the default view simple.
- Add a Cancel button for any operation that can take more than a moment.
- Never show a spinner for work that has already stopped.

Definition of done: every wait has a reason, every long action can be cancelled when safe, and every result has a clear outcome.

### 6. Responsive and accessible interface

Make layout change shape instead of squeezing.

- Wide window: related cards may sit side by side.
- Narrow window or open sidebar: cards stack one per row, labels wrap, and controls remain comfortably tappable.
- Keep horizontal scrolling disabled everywhere except content that is intentionally tabular and has an explicit alternative.
- Add keyboard focus, visible focus rings, sensible tab order, and accessible names to every button, switch, icon, menu, and status.
- Make icon-only buttons show a tooltip and accessible label.
- Use one consistent symbol for each action; do not use a symbol whose meaning changes by page.
- Test 360 px, 480 px, 768 px, and full-width desktop layouts with the sidebar both open and closed.

Definition of done: screenshots and accessibility checks show no clipped labels, hidden controls, or ambiguous icons at supported sizes.

### 7. macOS release engineering

Package the product as a real Mac app, not just a source folder.

- Create a stable `Buddy.app` bundle with a stable bundle identifier.
- Add required privacy usage descriptions and entitlements.
- Sign with Developer ID and notarize the release.
- Test install, first launch, update, uninstall, and relaunch after a crash.
- Add an opt-in crash report path that never uploads private chat content by default.
- Add a privacy page, permissions explanation, and data deletion controls.
- Add a release doctor that checks app identity, database health, provider configuration, microphone availability, and update readiness.
- Produce a small beta checklist and a rollback build before inviting outside testers.

Definition of done: a new user can download, install, authorize only what they choose, chat, use voice, connect an integration, revoke access, and remove their data.

## Ideas added to the roadmap

- Permission ledger: one place that shows what macOS granted, what Buddy is using it for, and how to revoke it.
- Truth audit: a development check that clicks every control and compares the visible state with the underlying state.
- Voice interruption as a first-class action instead of an edge case.
- Buddy status dot: a tiny always-clear indicator for idle, listening, thinking, speaking, paused, and error.
- Action receipts: a friendly “I did this” record for tool use.
- Recovery and undo for local changes.
- First-run capability map instead of a wall of settings.
- Release doctor for the signed app and its permissions.

## First-release gate

Do not ship the first macOS release until all of these are true:

- No visible control is fake, decorative, or mislabeled.
- Permission switches reflect verified macOS access, not local preference alone.
- Voice supports interruption, pause/resume, clear state, and truthful saving behavior.
- Gmail and GitHub either work end to end or are clearly marked unavailable and hidden from the primary path.
- The app survives deleted chats, missing databases, offline mode, provider timeouts, and revoked permissions.
- The signed app is the identity granted access in macOS settings.
- The narrow and wide layouts have no accidental horizontal scroll.
- Every important action has a keyboard and accessible path.
- A fresh install passes the full release checklist on a clean Mac user account.
