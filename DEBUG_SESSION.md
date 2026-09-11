# Buddy macOS Debugging Session

Date: 2026-09-09  
Scope: current Buddy desktop build, with emphasis on truthfulness, voice, permissions, responsive layout, and release readiness.

Follow-up: the `macos_release_pack` was merged on 2026-09-10. The results below include the post-merge validation.

## What was checked

- Parsed all 43 Python files successfully.
- Ran the existing end-to-end harness in an isolated temporary database.
- Constructed Buddy’s Billing, Plugins, and Talk to Buddy pages offscreen.
- Captured narrow and wide layouts at 360×700 and 960×760.
- Checked billing and plugin pages for horizontal scrolling at narrow and wide sizes.
- Exercised the local plugin gates for file access and terminal access.
- Exercised the weather tool path. The sandbox blocked DNS, so the live provider response could not be verified here.
- Confirmed that Buddy is not currently running as a native packaged app, so macOS TCC behavior could not be verified from this session.

## Passing checks

The current end-to-end harness passed:

1. Regular conversation
2. Feedback storage
3. Conversation search
4. Privacy toggle
5. In-memory incognito conversation
6. GUI construction and page availability

Billing and Plugins also stayed within their viewport with no horizontal scrollbar in the tested sizes. Billing changes to one plan column when narrow and two when wide.

## Release blockers

### P0 — Voice still needs signed-app testing

The release pack now adds the intended live-conversation state machine and controls:

- Idle, Listening, Thinking, Speaking, Paused, Interrupted, and Error states;
- Pause/Resume, Stop speaking, End chat, and Delete chat actions;
- microphone monitoring while Buddy speaks, including interruption detection;
- end-of-utterance timing and level-reactive waveform animation.

The controls now behave correctly in offscreen tests, but actual microphone permission, speech recognition, TTS cancellation, and interruption latency still need testing on a signed Buddy.app.

Acceptance test: while Buddy is speaking, the user says “stop.” Speech must stop promptly, the state must become Listening, and the next user utterance must be accepted without restarting the page.

### P0 — Permission probes still need signed-app testing

The release pack adds process-aware permission probes and keeps system switches off until the probe succeeds. A permission granted to Terminal, Python, VS Code, or another build must not count as permission for the packaged Buddy app.

Acceptance test: click a permission switch, refuse access in macOS, return to Buddy, and confirm the Buddy switch remains off and the protected action remains blocked.

### P1 — Integration controls need provider testing

The release pack adds real Gmail connection states, GitHub Device Flow wiring, and the missing plugin-connection tables. Provider authorization still needs an online test with real credentials before release.

Acceptance test: every integration row must say Connect, Connected, or Not connected based on a real credential check. Clicking Connect must open the provider’s official authorization flow and return a verified account identity.

## High-priority bugs and inconsistencies

### P1 — Qt stylesheet parser warnings

The offscreen run repeatedly reports “Could not parse stylesheet” for QFrame, QComboBox, QLineEdit, and QPushButton objects. The most likely contributors are unsupported CSS copied from the web, including `line-height`; this needs to be isolated and removed or replaced with Qt-supported styling. Release builds should start without these warnings.

### Resolved — Voice persistence copy

Voice copy now says the session is saved in Library, and the page includes an explicit Delete chat action.

### P1 — Native release identity is not verified

Running source from Terminal can cause macOS to grant access to Python or Terminal rather than Buddy. The first packaged build needs a stable application identity, entitlements, usage descriptions, signing, and notarization before permission behavior can be called complete.

### P2 — Accessibility and interaction coverage is thin

The voice animation has an accessible name, but every icon-only control, switch, status change, focus transition, and error state needs an accessibility name and keyboard path. The existing end-to-end test confirms construction, not that each visible control performs its promised action.

## Visual observations

The narrow Billing and Plugins screens are usable and do not horizontally overflow. Talk to Buddy also avoids horizontal scrolling, but its voice controls become cramped at narrow widths and the page contains a large amount of empty space before the mic. The speaking selector truncates its label at narrow widths, which is acceptable only if the full value is available on focus or in a tooltip.

The blue waveform animates continuously, including when idle. It is visually pleasant but does not yet represent microphone input or speaking amplitude. It should become quieter at idle, react to input while listening, and react to actual playback while speaking.

## Post-merge validation

- 181 project Python files parsed successfully.
- The existing end-to-end suite passed all six checks after the merge.
- Plugin connection storage initializes and returns an empty connection list on a fresh database.
- File tools remain blocked by default.
- Narrow Talk to Buddy actions now stack at 360 px; wide actions remain side by side.
- Billing, Plugins, and Talk to Buddy content fit their 360 px viewport with horizontal scrolling disabled.
- Qt stylesheet parser warnings still appear and remain a follow-up item.

## Debugging conclusion

The release pack closes the main code-level gaps identified in this session. The first macOS release should still wait for signed-app permission testing, real provider authorization tests, audio interruption testing, and cleanup of the remaining Qt stylesheet warnings.
