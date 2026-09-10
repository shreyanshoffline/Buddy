# Buddy macOS Debugging Session

Date: 2026-09-09  
Scope: current Buddy desktop build, with emphasis on truthfulness, voice, permissions, responsive layout, and release readiness.

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

### P0 — Voice is not yet a real conversation

The page calls itself a live voice conversation, but the implementation is push-to-talk turns:

- record one complete clip;
- upload and transcribe it;
- wait for the model;
- speak the complete reply;
- return to idle.

The mic is disabled while Buddy thinks or speaks. There is no pause button, stop-speaking button, voice activity detection, partial transcript, streaming response, or barge-in. A user cannot naturally interrupt Buddy.

Acceptance test: while Buddy is speaking, the user says “stop.” Speech must stop promptly, the state must become Listening, and the next user utterance must be accepted without restarting the page.

### P0 — Permission toggles are not proof of permission

The macOS rows open the correct-looking System Settings panel, but the switch is saved as on before macOS confirms that the Buddy process received access. A permission granted to Terminal, Python, VS Code, or another build must not count as permission for the packaged Buddy app.

Acceptance test: click a permission switch, refuse access in macOS, return to Buddy, and confirm the Buddy switch remains off and the protected action remains blocked.

### P0 — Integration controls are ahead of their real wiring

Gmail is presented as an enabled universal plugin but the Plugins page does not start or confirm Gmail OAuth. GitHub integration code exists, but there is no user-facing connection flow. The conversation layer calls plugin-connection database methods that are not currently implemented in `storage/db.py`.

Acceptance test: every integration row must say Connect, Connected, or Not connected based on a real credential check. Clicking Connect must open the provider’s official authorization flow and return a verified account identity.

## High-priority bugs and inconsistencies

### P1 — Qt stylesheet parser warnings

The offscreen run repeatedly reports “Could not parse stylesheet” for QFrame, QComboBox, QLineEdit, and QPushButton objects. The most likely contributors are unsupported CSS copied from the web, including `line-height`; this needs to be isolated and removed or replaced with Qt-supported styling. Release builds should start without these warnings.

### P1 — Voice persistence copy disagrees with behavior

The Talk to Buddy module describes voice as not saved by default, but it creates a “Voice chat” conversation and persists user and assistant turns. The visible hint says a voice chat can be saved to Library, which is ambiguous because it is already being saved.

Choose one truthful behavior before release:

- private by default, with an explicit Save button; or
- saved automatically, with copy that says so and a visible Delete conversation action.

### P1 — Native release identity is not verified

Running source from Terminal can cause macOS to grant access to Python or Terminal rather than Buddy. The first packaged build needs a stable application identity, entitlements, usage descriptions, signing, and notarization before permission behavior can be called complete.

### P2 — Accessibility and interaction coverage is thin

The voice animation has an accessible name, but every icon-only control, switch, status change, focus transition, and error state needs an accessibility name and keyboard path. The existing end-to-end test confirms construction, not that each visible control performs its promised action.

## Visual observations

The narrow Billing and Plugins screens are usable and do not horizontally overflow. Talk to Buddy also avoids horizontal scrolling, but its voice controls become cramped at narrow widths and the page contains a large amount of empty space before the mic. The speaking selector truncates its label at narrow widths, which is acceptable only if the full value is available on focus or in a tooltip.

The blue waveform animates continuously, including when idle. It is visually pleasant but does not yet represent microphone input or speaking amplitude. It should become quieter at idle, react to input while listening, and react to actual playback while speaking.

## Debugging conclusion

The foundation is healthy enough to continue: parsing, construction, the existing data-flow tests, and the recent no-horizontal-scroll work pass. The first macOS release should not be declared ready until the three P0 items—real interruptible voice, verified macOS permissions, and honest integration connection states—are implemented and tested on a signed app build.
