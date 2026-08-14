import os
import sqlite3
import pyautogui
import subprocess
from ddgs import DDGS
from datetime import datetime, timedelta

pyautogui.FAILSAFE = True

# ==================== APP TOOLS ====================

def open_app(app):
    result = subprocess.run(["open", "-a", app], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Opened {app}."
    return f"Couldn't open {app}: {result.stderr.strip()}"

def close_app(app):
    try:
        result = subprocess.run(
            ["osascript", "-e", f'quit app "{app}"'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return f"Closed {app}."
        return f"Couldn't close {app}: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"Couldn't close {app}: Timeout expired."

def force_close_app(app):
    result = subprocess.run(["pkill", "-f", app], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Force closed {app}."
    return f"Couldn't force close {app}: {result.stderr.strip()}"

def list_apps():
    result = subprocess.run(
        [
            "/bin/sh",
            "-c",
            "find /Applications /System/Applications -maxdepth 2 -name '*.app' | grep -v -E 'Utilities|\\.localized' | awk -F'/' '{print $NF}' | sed 's/\\.app//' | sort -u",
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split("\n") if result.returncode == 0 else []

def list_apps_running():
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of (processes where background only is false)'],
        capture_output=True,
        text=True
    )
    return result.stdout.strip().split(", ") if result.returncode == 0 else []


# ==================== WEB TOOLS ====================

def web_search(query, max_results=3):
    try:
        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return f"No search results found for: '{query}'"

        formatted_output = f"DuckDuckGo Search Results for '{query}':\n"
        for i, res in enumerate(results, 1):
            title = res.get('title', 'No Title')
            snippet = res.get('body', 'No Description')
            url = res.get('href', 'No URL')
            formatted_output += f"\n{i}. {title}\n   Snippet: {snippet}\n   URL: {url}\n"
        return formatted_output
    except Exception as e:
        return f"Failed to execute web search: {str(e)}"

def open_url(url):
    result = subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True, text=True)
    return f"Opened {url}." if result.returncode == 0 else f"Couldn't open {url}: {result.stderr.strip()}"

def browser_action(action, browser="Google Chrome"):
    key_mappings = {
        "new_tab": "t",
        "new_window": "n",
        "open_history": "y",
        "undo": "z",
    }

    if action in key_mappings:
        script = f'''
        tell application "{browser}" to activate
        tell application "System Events"
            keystroke "{key_mappings[action]}" using {{command down}}
        end tell
        '''
    elif action == "reopen_tab" or action == "reopen_window":
        script = f'''
        tell application "{browser}" to activate
        tell application "System Events"
            keystroke "t" using {{command down, shift down}}
        end tell
        '''
    elif action == "redo":
        script = f'''
        tell application "{browser}" to activate
        tell application "System Events"
            keystroke "z" using {{command down, shift down}}
        end tell
        '''
    else:
        return f"Unknown browser action: {action}"

    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Performed '{action}' in {browser}." if result.returncode == 0 else result.stderr.strip()

def list_open_tabs(browser="Google Chrome"):
    script = f'''
    tell application "{browser}"
        set output to ""
        set winIndex to 1
        repeat with w in windows
            set output to output & "Window " & winIndex & ":\\n"
            repeat with t in tabs of w
                set output to output & "  - " & (title of t) & " | " & (URL of t) & "\\n"
            end repeat
            set winIndex to winIndex + 1
        end repeat
        return output
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        tabs_output = result.stdout.strip()
        return tabs_output if tabs_output else "No tabs found."
    return f"Couldn't list tabs: {result.stderr.strip()}"

def close_tab(website, browser="Google Chrome"):
    script = f'tell application "{browser}" to close (tabs of front window whose URL contains "{website}")'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Closed tab for {website}." if result.returncode == 0 else f"Couldn't close tab: {result.stderr.strip()}"


# ==================== CODING & FILES ====================

def run_code(file_path):
    expanded_path = os.path.expanduser(file_path)
    try:
        result = subprocess.run(["python3", expanded_path], capture_output=True, text=True, timeout=10)
        return f"Output:\n{result.stdout}\nErrors:\n{result.stderr}"
    except Exception as e:
        return f"Failed to run code: {str(e)}"

def search_local_files(query):
    try:
        result = subprocess.run(["mdfind", "-name", query], capture_output=True, text=True, timeout=5)
        files = result.stdout.strip().split("\n")[:5]
        return f"Found files:\n" + "\n".join(files) if files and files[0] else "No files found."
    except Exception as e:
        return f"File search failed: {str(e)}"

def open_folder_in_editor(file_path):
    expanded_path = os.path.expanduser(file_path)
    try:
        subprocess.run(["open", "-a", "Visual Studio Code", expanded_path])
        return f"Opened {expanded_path} in VS Code."
    except Exception:
        subprocess.run(["open", expanded_path])
        return f"Opened {expanded_path} in Finder."

def create_file(file_name, file_path):
    full_directory = os.path.expanduser(file_path)
    full_path = os.path.join(full_directory, file_name)
    try:
        os.makedirs(full_directory, exist_ok=True)
        with open(full_path, 'w') as f:
            f.write("")
        return f"Created file at {full_path}"
    except Exception as e:
        return f"Failed to create file: {str(e)}"

def delete_file(file_name, file_path):
    full_path = os.path.join(os.path.expanduser(file_path), file_name)
    try:
        os.remove(full_path)
        return f"Deleted file at {full_path}"
    except Exception as e:
        return f"Failed to delete file: {str(e)}"

def manage_package(action, package_name):
    cmd_map = {
        "install": ["pip3", "install", package_name],
        "update": ["pip3", "install", "--upgrade", package_name],
        "uninstall": ["pip3", "uninstall", "-y", package_name]
    }
    if action not in cmd_map:
        return f"Unknown package action: {action}"
    
    try:
        result = subprocess.run(cmd_map[action], capture_output=True, text=True)
        return f"Package operation '{action}' completed for {package_name}:\n{result.stdout}"
    except Exception as e:
        return f"Package action failed: {str(e)}"


# ==================== SYSTEM & SHELL SUPERPOWERS ====================

def run_terminal_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return f"Failed to execute command: {str(e)}"

def get_clipboard():
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return f"Clipboard Content:\n{result.stdout}"

def set_clipboard(text):
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
    process.communicate(text)
    return "Copied text to system clipboard."

def send_notification(title, message):
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script])
    return f"Notification sent: {title}"

def capture_screen(save_path="~/Desktop/screenshot.png"):
    expanded_path = os.path.expanduser(save_path)
    result = subprocess.run(["screencapture", expanded_path], capture_output=True, text=True)
    return f"Screenshot saved to {expanded_path}" if result.returncode == 0 else f"Failed screenshot: {result.stderr.strip()}"

def set_volume(amount):
    try:
        val = max(0, min(100, int(amount)))
        subprocess.run(["osascript", "-e", f"set volume output volume {val}"])
        return f"Volume set to {val}%."
    except Exception as e:
        return f"Failed to set volume: {str(e)}"

def set_dark_mode(state):
    try:
        is_dark = "true" if state.lower() in ['on', 'true', 'yes'] else "false"
        script = f'tell application "System Events" to tell appearance preferences to set dark mode to {is_dark}'
        subprocess.run(["osascript", "-e", script])
        return f"Dark mode set to {state}."
    except Exception as e:
        return f"Failed to set dark mode: {str(e)}"


# ==================== MacOS APP Automation via applescript ====================
# ================== Spotify ===================

def spotify_control(action):
    action_map = {
        "play": "play",
        "pause": "pause",
        "next": "next track",
        "previous": "previous track"
    }
    if action not in action_map:
        return f"Unknown Spotify action: {action}"

    script = f'tell application "Spotify" to {action_map[action]}'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Spotify: {action}" if result.returncode == 0 else f"Spotify Error: {result.stderr.strip()}"

def play_spotify_playlist(playlist_name):
    playlists = {
        "fav songs": "spotify:playlist:37i9dQZF1DX70RN3TfR079",
        "liked songs": "spotify:collection:tracks"
    }
    name_lower = str(playlist_name).lower()
    if name_lower in playlists:
        uri = playlists[name_lower]
        script = f'tell application "Spotify" to play track "{uri}"'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return f"Playing '{playlist_name}' on Spotify." if result.returncode == 0 else f"Error: {result.stderr.strip()}"
    return f"Error: Playlist '{playlist_name}' not saved in dictionary."

# =============== imessage ===================

def lookup_contact_number(name: str) -> dict:
    script = f'''
    tell application "Contacts"
        set thePerson to first person whose name contains "{name}"
        set thePhone to value of first phone of thePerson
        return thePhone
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return {"success": True, "number": result.stdout.strip()}
    return {"success": False, "stderr": result.stderr}

def send_imessage(recipient: str, message: str) -> dict:
    safe_message = message.replace('"', '\\"')
    safe_recipient = recipient.replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to participant "{safe_recipient}" of targetService
        send "{safe_message}" to targetBuddy
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "stderr": result.stderr,
        "stdout": result.stdout
    }
def send_group_message(chat_name: str, message: str) -> dict:
    safe_message = message.replace('"', '\\"')
    safe_chat_name = chat_name.replace('"', '\\"')
    script = f'''
    tell application "Messages"
        set targetChat to missing value
        repeat with c in chats
            if (name of c is "{safe_chat_name}") then
                set targetChat to c
                exit repeat
            end if
        end repeat
        if targetChat is missing value then
            error "Chat not found: {safe_chat_name}"
        end if
        send "{safe_message}" to targetChat
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "stderr": result.stderr,
        "stdout": result.stdout
    }

def get_unread_messages(limit: int = 20) -> list[dict]:
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT 
        message.text,
        message.date,
        message.is_from_me,
        handle.id AS sender,
        chat.display_name AS chat_name,
        chat.chat_identifier AS chat_id
    FROM message
    JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
    JOIN chat ON chat_message_join.chat_id = chat.ROWID
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    WHERE message.is_from_me = 0 AND message.is_read = 0
    ORDER BY message.date DESC
    LIMIT ?
    """
    rows = conn.execute(query, (limit,)).fetchall()
    conn.close()

    epoch = datetime(2001, 1, 1)
    results = []
    for r in rows:
        ts = epoch + timedelta(seconds=r["date"] / 1_000_000_000)
        results.append({
            "text": r["text"],
            "sender": r["sender"],
            "chat_name": r["chat_name"] or r["chat_id"],  # group chats often have no display_name set
            "timestamp": ts.isoformat(),
        })
    return results
def list_group_chats(limit: int = 20) -> list[dict]:
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT DISTINCT chat.ROWID, chat.display_name, chat.chat_identifier
    FROM chat
    JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
    WHERE chat.style = 43
    ORDER BY chat.ROWID DESC
    LIMIT ?
    """
    rows = conn.execute(query, (limit,)).fetchall()
    conn.close()

    return [
        {
            "chat_id": r["chat_identifier"],
            "display_name": r["display_name"] or "(no custom name)",
        }
        for r in rows
    ]