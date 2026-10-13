# macOS guide — how to do things on a Mac with Buddy's tools
Read the section you need with read_guide("macos", section="<keyword>"). Prefer a dedicated tool over run_terminal_command; use osascript/shell only when no tool fits.

## Apps
- Open/close/focus: open_app, close_app, force_close_app (last resort), activate_app, list_apps_running, get_frontmost_app.
- Not installed? appstore_open_search(query) or run_terminal_command("brew install --cask <name>") if Homebrew exists (check `which brew`).
- Quit everything except Buddy: list_apps_running, then close_app each.

## Files and Finder
- Find by name: search_local_files (Spotlight). Find by content: run_terminal_command `mdfind "kind:pdf invoice"` or `grep -ril "text" ~/Documents`.
- Read/write: read_file_content, write_file_content, append_to_file, create_directory, copy_file, move_file, rename_file.
- Delete: trash_file (recoverable). delete_file / empty_trash only after the user confirms.
- Show in Finder: open_in_finder or finder_reveal. Open a file with its default app: run_terminal_command `open "<path>"`; with a specific app: `open -a "Preview" "<path>"`.
- Zip: `ditto -c -k --sequesterRsrc --keepParent "<folder>" "<out>.zip"`; unzip: `ditto -x -k "<zip>" "<dest>"`.
- Big files: `find ~ -type f -size +500M 2>/dev/null | head`. Folder sizes: `du -sh ~/Downloads/* | sort -h | tail`.
- Protected folders (Desktop/Documents/Downloads) need the Files & Folders permission for Buddy; if a read fails with "Operation not permitted", tell the user to enable it in Plugins, do not retry.

## System settings and state
- Volume: get_volume, set_volume. Dark mode: get_dark_mode, set_dark_mode. Battery: get_battery_status. Disk: get_disk_space. RAM: get_memory_info. Overview: get_system_info.
- Open a settings pane: open_system_settings_pane(pane). Wi-Fi on/off: `networksetup -setairportpower en0 on|off`. Current Wi-Fi: `networksetup -getairportnetwork en0`.
- Bluetooth: `blueutil` if installed (`brew install blueutil`), else open the Bluetooth pane.
- Do Not Disturb/Focus: no reliable CLI. Run a Shortcut: clock_run_shortcut(name) — ask the user to create a Shortcut named e.g. "Focus On" once, then save_lesson.
- Brightness: `brightness 0.6` (brew install brightness). Lock: lock_screen. Sleep display: sleep_display.
- Processes: list_processes, kill_process (confirm first for anything not clearly user-owned).

## Clipboard, screenshots, notifications
- get_clipboard / set_clipboard. Screenshot: capture_screen(save_path). Region screenshot to clipboard needs the user; do not simulate keys.
- send_notification(title, message). Speak aloud: speak(text).

## Reminders, Notes, Calendar (Apple)
- Reminders: reminders_add, reminders_list, reminders_complete. Notes: notes_create, notes_find, notes_append. Calendar: apple_calendar_today, apple_calendar_create_event, apple_calendar_move_event.
- Use ISO times with the user's timezone. Always read the event back to the user after creating it.

## Messages and Mail
- iMessage: lookup_contact_number first, then send_imessage. Groups: list_group_chats then send_group_message. Show the exact text and recipient and get a yes before sending.
- Mail.app: mail_list_inbox, mail_create_draft (drafts only; never auto-send).

## Music and media
- Spotify: spotify_control(action), play_spotify_playlist. Apple Music: music_play, music_pause, music_now_playing, music_play_playlist.

## AppleScript patterns (via run_terminal_command)
- Run: `osascript -e 'tell application "Finder" to get name of every disk'`.
- Multi-line: pass each line with its own -e. Escape double quotes inside strings with \". Never build scripts from unescaped user text.
- Keystrokes/UI scripting need Accessibility permission for Buddy: `tell application "System Events" to keystroke "v" using command down`.
- Safari JS: `tell application "Safari" to do JavaScript "document.title" in current tab of front window` (needs Safari > Develop > Allow JavaScript from Apple Events).

## Shell toolbox
- `open`, `pbcopy`/`pbpaste`, `mdfind`, `say`, `screencapture`, `defaults read/write`, `pmset -g batt`, `caffeinate -t 3600`, `networksetup`, `softwareupdate -l`, `sw_vers`, `system_profiler SPHardwareDataType`, `diskutil list`, `launchctl list`, `plutil -p`, `sips -Z 1024 in.jpg --out out.jpg` (resize image), `textutil -convert pdf in.docx`, `afconvert`.
- Install packages: manage_package(name) or `brew install`. Python snippets: run_code.

## When something fails
- "Operation not permitted" = missing macOS permission, not a bug: say which one (Full Disk Access, Accessibility, Automation, Files & Folders) and open_system_settings_pane.
- Command not found: check `which <cmd>`, offer `brew install`.
- Never retry a failing destructive command; report and ask.
