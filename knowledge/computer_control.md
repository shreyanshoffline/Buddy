# Computer control guide — doing anything a person does at a Mac
Order of preference: (1) a dedicated API/tool, (2) AppleScript/shell, (3) Buddy's browser for websites, (4) screen + mouse/keyboard simulation as the last resort.

## Decide the route
- Data in an app with an API (Gmail, Calendar, Drive, Outlook, Slack, GitHub): use that tool. Fast and reliable.
- Mac app with AppleScript support (Finder, Mail, Notes, Reminders, Calendar, Music, Safari, Messages, Keynote, Numbers, Pages): osascript.
- Website with no API: browser guide (web_open / web_read / web_click).
- App with no scripting: UI simulation. capture_screen to look, get_screen_size, mouse_move/mouse_click(x, y), type_text, press_hotkey. Requires Accessibility permission for Buddy.

## UI simulation loop (last resort)
1. activate_app(name). 2. capture_screen and view it. 3. One action (click or type). 4. capture_screen to verify. Never chain more than 2 blind actions.
- Prefer keyboard shortcuts over clicks: press_hotkey("cmd+space") Spotlight, "cmd+tab" switch app, "cmd+w" close window, "cmd+shift+4" screenshot (user-run), "cmd+," preferences.
- Coordinates come from the screenshot scale; check get_screen_size (Retina screenshots are 2x).

## Common jobs
- Fill a form in an app: click first field, type_text, press_hotkey("tab"), repeat. Verify with a screenshot before submitting.
- Move a window/resize: AppleScript `tell application "System Events" to tell process "X" to set position of window 1 to {0,0}`.
- Export a document to PDF: `osascript` File > Print > PDF is brittle; prefer `textutil`, `cupsfilter`, or the app's own AppleScript export.
- Automate repeated work: write a small Python script with run_code, show it to the user, run it. If it will be reused, save_lesson with the exact command.

## Safety rules
- Confirm before: sending messages/emails, purchases, deleting, anything that posts publicly, anything with money.
- Never type passwords. If a login is needed, hand control to the user (browser profile keeps the login afterwards).
- If a permission prompt appears, tell the user what to click; do not try to click it for them.
