"""
Apple ecosystem backend for Buddy.

Every function returns a short, human-readable string describing what
actually happened (or exactly why it didn't) — never a silent guess.
Drop this file in as tools/apple_tools.py and import the functions you
need into tools/tools.py's schema, same pattern as the existing Gmail
tools.

Permission model (macOS truth, not Buddy's opinion):
- AppleScript "tell application X" -> needs Automation permission for
  that specific app, granted the FIRST time it runs (a system dialog
  appears). If denied, macOS raises error -1743, which every function
  here catches and reports honestly.
- Messages history + Full Disk Access -> reading chat.db needs Full
  Disk Access (System Settings > Privacy & Security > Full Disk
  Access), not just Automation. There's no dialog for this one — the
  read just silently returns nothing until you grant it, so we detect
  that case explicitly.
- System Events (used for Messages draft-typing) needs Accessibility
  permission.
"""

import os
import sqlite3
import subprocess
import shutil
import glob
from datetime import datetime, timedelta

ICLOUD_DRIVE_PATH = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
CHAT_DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")


# ---------------------------------------------------------------------------
# Shared AppleScript runner
# ---------------------------------------------------------------------------

def _run_applescript(script: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: timed out talking to the app. It may be showing a dialog."
    if result.returncode != 0:
        err = result.stderr.strip()
        if "-1743" in err or "not allowed" in err.lower():
            return ("PERMISSION_DENIED: macOS blocked this. The user needs to grant "
                    "Automation access for this app in System Settings > Privacy & "
                    "Security > Automation, then try again.")
        return f"ERROR: {err or 'unknown AppleScript error'}"
    return result.stdout.strip()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _is_permission_error(output: str) -> bool:
    return output.startswith("PERMISSION_DENIED") or output.startswith("ERROR")


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def reminders_list(list_name: str = None, include_completed: bool = False) -> str:
    target = f'list "{_escape(list_name)}" of ' if list_name else ""
    completed_filter = "" if include_completed else "whose completed is false"
    script = f'''
    tell application "Reminders"
        set out to {{}}
        set theReminders to (reminders of {target}default list {completed_filter})
        if {target} is "" then set theReminders to (reminders of every list {completed_filter})
        repeat with r in theReminders
            set dueStr to "no due date"
            try
                set dueStr to (due date of r) as string
            end try
            set end of out to (name of r & " | due: " & dueStr)
        end repeat
        return out as string
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return out if out else "No reminders found."


def reminders_add(title: str, due: str = None, list_name: str = None, notes: str = None) -> str:
    list_clause = f'list "{_escape(list_name)}"' if list_name else "default list"
    props = [f'name:"{_escape(title)}"']
    if notes:
        props.append(f'body:"{_escape(notes)}"')
    if due:
        # due passed as "YYYY-MM-DD HH:MM"; AppleScript needs a date object
        props.append(f'due date:(date "{due}")')
    script = f'''
    tell application "Reminders"
        make new reminder at {list_clause} with properties {{{", ".join(props)}}}
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f'Added reminder "{title}"' + (f" due {due}" if due else "") + f' to {list_name or "default list"}.'


def reminders_complete(title: str, list_name: str = None) -> str:
    target = f'list "{_escape(list_name)}"' if list_name else "default list"
    script = f'''
    tell application "Reminders"
        set matches to (reminders of {target} whose name is "{_escape(title)}")
        if (count of matches) is 0 then return "NOT_FOUND"
        set completed of (item 1 of matches) to true
        return "OK"
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    if out == "NOT_FOUND":
        return f'No reminder titled "{title}" found in {list_name or "default list"}.'
    return f'Marked "{title}" done.'


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def notes_find(title_query: str) -> str:
    script = f'''
    tell application "Notes"
        set matches to (notes whose name contains "{_escape(title_query)}")
        if (count of matches) is 0 then return "NOT_FOUND"
        set n to item 1 of matches
        return (name of n) & "\\n---\\n" & (body of n)
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f'No note matching "{title_query}".' if out == "NOT_FOUND" else out


def notes_append(title_query: str, text: str) -> str:
    script = f'''
    tell application "Notes"
        set matches to (notes whose name contains "{_escape(title_query)}")
        if (count of matches) is 0 then return "NOT_FOUND"
        set n to item 1 of matches
        set body of n to (body of n) & "<div><br></div><div>{_escape(text)}</div>"
        return "OK"
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    if out == "NOT_FOUND":
        return f'No note matching "{title_query}" to append to.'
    return f'Appended to note "{title_query}".'


def notes_create(title: str, body: str = "", folder: str = None) -> str:
    folder_clause = f'folder "{_escape(folder)}"' if folder else "default folder"
    script = f'''
    tell application "Notes"
        make new note at {folder_clause} with properties {{name:"{_escape(title)}", body:"{_escape(body)}"}}
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f'Created note "{title}"' + (f" in {folder}" if folder else "") + "."


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_today(calendar_name: str = None) -> str:
    cal_clause = f'calendar "{_escape(calendar_name)}"' if calendar_name else "every calendar"
    script = f'''
    tell application "Calendar"
        set today to current date
        set startOfDay to today - (time of today)
        set endOfDay to startOfDay + (24 * 60 * 60)
        set out to {{}}
        repeat with c in ({cal_clause} as list)
            set theEvents to (events of c whose start date is greater than or equal to startOfDay and start date is less than endOfDay)
            repeat with e in theEvents
                set end of out to ((summary of e) & " | " & (start date of e as string))
            end repeat
        end repeat
        return out as string
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return out if out else "Nothing on the calendar today."


def calendar_create_event(title: str, start_iso: str, end_iso: str,
                           calendar_name: str = None, location: str = None) -> str:
    cal_clause = f'calendar "{_escape(calendar_name)}"' if calendar_name else "calendar 1"
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    loc_prop = f', location:"{_escape(location)}"' if location else ""
    script = f'''
    tell application "Calendar"
        tell {cal_clause}
            make new event with properties {{summary:"{_escape(title)}", start date:(date "{start_dt.strftime('%B %d, %Y %I:%M:%S %p')}"), end date:(date "{end_dt.strftime('%B %d, %Y %I:%M:%S %p')}"){loc_prop}}}
        end tell
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f'Created "{title}" from {start_dt.strftime("%-I:%M %p")} to {end_dt.strftime("%-I:%M %p")}.'


def calendar_move_event(title: str, hours_delta: float, calendar_name: str = None) -> str:
    cal_clause = f'calendar "{_escape(calendar_name)}"' if calendar_name else "every calendar"
    seconds = int(hours_delta * 3600)
    script = f'''
    tell application "Calendar"
        repeat with c in ({cal_clause} as list)
            set matches to (events of c whose summary is "{_escape(title)}")
            if (count of matches) > 0 then
                set e to item 1 of matches
                set start date of e to (start date of e) + {seconds}
                set end date of e to (end date of e) + {seconds}
                return "OK"
            end if
        end repeat
        return "NOT_FOUND"
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    if out == "NOT_FOUND":
        return f'No event titled "{title}" found.'
    direction = "later" if hours_delta > 0 else "earlier"
    return f'Moved "{title}" {abs(hours_delta)}h {direction}.'


# ---------------------------------------------------------------------------
# Messages — read via chat.db (needs Full Disk Access), draft via GUI scripting
# (needs Accessibility). Never auto-sends.
# ---------------------------------------------------------------------------

def messages_recent_threads(limit: int = 10) -> str:
    if not os.path.exists(CHAT_DB_PATH):
        return "PERMISSION_DENIED: Messages database not readable. Grant Full Disk Access to Buddy in System Settings > Privacy & Security > Full Disk Access, then restart Buddy."
    try:
        tmp_copy = "/tmp/buddy_chat_read.db"
        shutil.copy2(CHAT_DB_PATH, tmp_copy)
        con = sqlite3.connect(tmp_copy)
        cur = con.cursor()
        cur.execute("""
            SELECT chat.chat_identifier, message.text, message.date
            FROM message
            JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
            JOIN chat ON chat.ROWID = chat_message_join.chat_id
            WHERE message.text IS NOT NULL
            ORDER BY message.date DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        con.close()
        os.remove(tmp_copy)
        if not rows:
            return "No recent messages found."
        return "\n".join(f"{who}: {text}" for who, text, _ in rows)
    except Exception as e:
        return f"PERMISSION_DENIED: could not read Messages ({e}). Grant Full Disk Access."


def messages_draft(recipient: str, text: str) -> str:
    """Opens Messages with the text typed in — never presses Send."""
    script = f'''
    tell application "Messages"
        activate
    end tell
    delay 0.5
    tell application "System Events"
        tell process "Messages"
            keystroke "n" using command down
            delay 0.3
            keystroke "{_escape(recipient)}"
            delay 0.3
            key code 36
            delay 0.3
            keystroke "{_escape(text)}"
        end tell
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return ("PERMISSION_DENIED: needs Accessibility access for System Events "
                "(System Settings > Privacy & Security > Accessibility).")
    return f'Drafted a message to {recipient} — window is open, waiting for you to hit Send.'


# ---------------------------------------------------------------------------
# Mail.app — ONLY use when the user explicitly asked for Apple Mail, never
# as a Gmail fallback.
# ---------------------------------------------------------------------------

def mail_list_inbox(limit: int = 10, mailbox: str = "INBOX") -> str:
    script = f'''
    tell application "Mail"
        set out to {{}}
        set theMessages to messages 1 thru {limit} of mailbox "{_escape(mailbox)}" of account 1
        repeat with m in theMessages
            set end of out to ((subject of m) & " — " & (sender of m))
        end repeat
        return out as string
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return out if out else "Mailbox is empty or not found."


def mail_create_draft(to: str, subject: str, body: str) -> str:
    script = f'''
    tell application "Mail"
        set newMsg to make new outgoing message with properties {{subject:"{_escape(subject)}", content:"{_escape(body)}", visible:true}}
        tell newMsg
            make new to recipient at end of to recipients with properties {{address:"{_escape(to)}"}}
        end tell
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f'Drafted an Apple Mail message to {to} — not sent.'


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------

def music_play() -> str:
    return _finish(_run_applescript('tell application "Music" to play'), "Playing.")


def music_pause() -> str:
    return _finish(_run_applescript('tell application "Music" to pause'), "Paused.")


def music_play_playlist(name: str) -> str:
    script = f'tell application "Music" to play playlist "{_escape(name)}"'
    return _finish(_run_applescript(script), f'Playing playlist "{name}".')


def music_now_playing() -> str:
    script = '''
    tell application "Music"
        if player state is playing then
            return (name of current track) & " — " & (artist of current track)
        else
            return "Nothing is playing."
        end if
    end tell
    '''
    return _run_applescript(script)


def _finish(out: str, success_msg: str) -> str:
    return out if _is_permission_error(out) else success_msg


# ---------------------------------------------------------------------------
# FaceTime — no real AppleScript dictionary; URL scheme opens the call sheet
# and requires the user to confirm, which matches "no in-call robot" anyway.
# ---------------------------------------------------------------------------

def facetime_call(contact_or_number: str, video: bool = True) -> str:
    scheme = "facetime" if video else "facetime-audio"
    try:
        subprocess.run(["open", f"{scheme}://{contact_or_number}"], check=True, timeout=10)
        return f'Opened FaceTime {"video" if video else "audio"} call sheet for {contact_or_number} — confirm to connect.'
    except Exception as e:
        return f"ERROR: could not open FaceTime ({e})."


# ---------------------------------------------------------------------------
# Clock — Apple's Clock app has no public AppleScript dictionary. The only
# reliable path is a pre-built Shortcuts automation the user creates once
# in the Shortcuts app (e.g. "Start Timer", "Set Alarm").
# ---------------------------------------------------------------------------

def clock_run_shortcut(shortcut_name: str, input_text: str = None) -> str:
    cmd = ["shortcuts", "run", shortcut_name]
    if input_text:
        cmd += ["--input-path", "-"]
    try:
        subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=15, check=True)
        return f'Ran Shortcuts automation "{shortcut_name}".'
    except FileNotFoundError:
        return "ERROR: `shortcuts` CLI not found (needs macOS 12+)."
    except subprocess.CalledProcessError as e:
        return f'ERROR: Shortcut "{shortcut_name}" not found or failed. Create it once in the Shortcuts app first.'


# ---------------------------------------------------------------------------
# Finder
# ---------------------------------------------------------------------------

def finder_reveal(path: str) -> str:
    script = f'tell application "Finder" to reveal POSIX file "{_escape(os.path.expanduser(path))}"'
    _run_applescript(script)
    subprocess.run(["open", "-R", os.path.expanduser(path)])
    return f"Revealed {path} in Finder."


def finder_move(path: str, destination_folder: str) -> str:
    src = os.path.expanduser(path)
    dst_dir = os.path.expanduser(destination_folder)
    if not os.path.exists(src):
        return f"ERROR: {path} does not exist."
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    shutil.move(src, dst)
    return f"Moved {path} to {dst}."


def finder_trash(path: str) -> str:
    full = os.path.expanduser(path)
    script = f'tell application "Finder" to delete POSIX file "{full}"'
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return f"Moved {path} to Trash — Cmd+Z in Finder to undo."


# ---------------------------------------------------------------------------
# Safari
# ---------------------------------------------------------------------------

def safari_list_tabs() -> str:
    script = '''
    tell application "Safari"
        set out to {}
        repeat with w in windows
            repeat with t in tabs of w
                set end of out to (name of t)
            end repeat
        end repeat
        return out as string
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return out if out else "No Safari windows open."


def safari_open_url(url: str) -> str:
    script = f'''
    tell application "Safari"
        activate
        open location "{_escape(url)}"
    end tell
    '''
    out = _run_applescript(script)
    return out if _is_permission_error(out) else f"Opened {url} in Safari."


def safari_current_tab_title() -> str:
    script = 'tell application "Safari" to return name of current tab of front window'
    return _run_applescript(script)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def photos_search(query: str = None, album: str = None, limit: int = 10) -> str:
    if album:
        script = f'''
        tell application "Photos"
            set out to {{}}
            set theAlbum to album "{_escape(album)}"
            set thePhotos to (media items of theAlbum)
            repeat with i from 1 to (min of {{{limit}, count of thePhotos}})
                set end of out to (filename of (item i of thePhotos))
            end repeat
            return out as string
        end tell
        '''
    else:
        script = f'''
        tell application "Photos"
            set out to {{}}
            set thePhotos to (media items whose filename contains "{_escape(query or '')}")
            repeat with i from 1 to (min of {{{limit}, count of thePhotos}})
                set end of out to (filename of (item i of thePhotos))
            end repeat
            return out as string
        end tell
        '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    return out if out else "No matching photos."


def photos_export_one(filename_query: str, destination_folder: str) -> str:
    dest = os.path.expanduser(destination_folder)
    os.makedirs(dest, exist_ok=True)
    script = f'''
    tell application "Photos"
        set matches to (media items whose filename contains "{_escape(filename_query)}")
        if (count of matches) is 0 then return "NOT_FOUND"
        export {{item 1 of matches}} to POSIX file "{dest}"
        return "OK"
    end tell
    '''
    out = _run_applescript(script)
    if _is_permission_error(out):
        return out
    if out == "NOT_FOUND":
        return f'No photo matching "{filename_query}".'
    return f'Exported a photo matching "{filename_query}" to {destination_folder}.'


# ---------------------------------------------------------------------------
# App Store
# ---------------------------------------------------------------------------

def appstore_open_search(app_name: str) -> str:
    url = f"macappstore://apps.apple.com/search?term={app_name.replace(' ', '+')}"
    subprocess.run(["open", url])
    return f'Opened the App Store search results for "{app_name}".'


def appstore_open_product_id(app_id: str) -> str:
    subprocess.run(["open", f"macappstore://apps.apple.com/app/id{app_id}"])
    return f"Opened App Store product page for app id {app_id}."


# ---------------------------------------------------------------------------
# System Settings deep links
# ---------------------------------------------------------------------------

SYSTEM_SETTINGS_PANES = {
    "microphone": "com.apple.preference.security?Privacy_Microphone",
    "camera": "com.apple.preference.security?Privacy_Camera",
    "automation": "com.apple.preference.security?Privacy_Automation",
    "full_disk_access": "com.apple.preference.security?Privacy_AllFiles",
    "accessibility": "com.apple.preference.security?Privacy_Accessibility",
    "notifications": "com.apple.preference.notifications",
    "files_and_folders": "com.apple.preference.security?Privacy_ListenEvent",
}


def open_system_settings_pane(pane: str) -> str:
    key = pane.lower().replace(" ", "_")
    if key not in SYSTEM_SETTINGS_PANES:
        return f"ERROR: unknown pane '{pane}'. Known: {', '.join(SYSTEM_SETTINGS_PANES)}"
    subprocess.run(["open", f"x-apple.systempreferences:{SYSTEM_SETTINGS_PANES[key]}"])
    return f"Opened System Settings > {pane}."


# ---------------------------------------------------------------------------
# iCloud Drive — treated as a folder, only after confirming Buddy can read it
# ---------------------------------------------------------------------------

def icloud_probe() -> str:
    if os.path.isdir(ICLOUD_DRIVE_PATH) and os.access(ICLOUD_DRIVE_PATH, os.R_OK):
        return "OK: iCloud Drive is readable at " + ICLOUD_DRIVE_PATH
    return "PERMISSION_DENIED: iCloud Drive folder not accessible. Grant Full Disk Access."


def icloud_list(subpath: str = "") -> str:
    full = os.path.join(ICLOUD_DRIVE_PATH, subpath)
    if not os.path.isdir(full):
        return f"ERROR: {full} is not a folder (or iCloud Drive isn't accessible)."
    entries = os.listdir(full)
    return "\n".join(entries) if entries else "(empty)"