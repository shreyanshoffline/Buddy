import os
import shutil
import subprocess
import webbrowser
import pyautogui
import time
import requests
from dotenv import load_dotenv
from ddgs import DDGS

# App Tools ================================================

def open_app(app):
    result = subprocess.run(
        ["open", "-a", app], capture_output=True, text=True
    )
    if result.returncode == 0:
        return f"Opened {app}."
    else:
        return f"Couldn't open {app}: {result.stderr.strip()}"

def close_app(app):
    try:
        result = subprocess.run(
            ["osascript", "-e", f'quit app "{app}"'],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return f"Couldn't close {app}: Timeout expired"

    if result.returncode == 0:
        return f"Closed {app}."
    else:
        return f"Couldn't close {app}: {result.stderr.strip()}"

def force_close_app(app):
    result = subprocess.run(
        ["pkill", "-f", app], capture_output=True, text=True
    )
    if result.returncode == 0:
        return f"Force closed {app}."
    else:
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
    if result.returncode == 0:
        return result.stdout.strip().split("\n")
    else:
        return []

def list_apps_running():
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of (processes where background only is false)'],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip().split(", ")
    else:
        return []

def maximize_app(app):
    script = f'''
    tell application "System Events"
        tell process "{app}"
            set value of attribute "AXFullScreen" of window 1 to true
        end tell
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Maximized {app}."
    else:
        return f"Couldn't maximize {app}: {result.stderr.strip()}"

def minimize_app(app):
    script = f'''
    tell application "System Events"
        tell process "{app}"
            set value of attribute "AXMinimized" of window 1 to true
        end tell
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Minimized {app}."
    else:
        return f"Couldn't minimize {app}: {result.stderr.strip()}"


# Web Tools ================================================

def web_search(query, max_results=3):
    """
    Searches the live web using DuckDuckGo and returns top results.
    No API key required. Unrestricted full-web search.
    """
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
    result = subprocess.run(
        ["open", "-a", "Google Chrome", url], capture_output=True, text=True
    )
    if result.returncode == 0:
        return f"Opened {url}."
    else:
        return f"Couldn't open {url}: {result.stderr.strip()}"

def open_new_tab(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "t" using {{command down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Opened new tab in {browser}." if result.returncode == 0 else result.stderr.strip()

def open_new_window(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "n" using {{command down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Opened new window in {browser}." if result.returncode == 0 else result.stderr.strip()

def close_tab(browser, website):
    result = subprocess.run(
        ["osascript", "-e", f'tell application "{browser}" to close (tabs of front window whose URL contains "{website}")'],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return f"Closed tab for {website}."
    else:
        return f"Couldn't close tab for {website}: {result.stderr.strip()}"

def close_window(browser, website):
    result = subprocess.run(
        ["osascript", "-e", f'tell application "{browser}" to close (windows whose URL contains "{website}")'],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return f"Closed window for {website}."
    else:
        return f"Couldn't close window for {website}: {result.stderr.strip()}"

def reopen_closed_tab(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "t" using {{command down, shift down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Reopened last closed tab in {browser}." if result.returncode == 0 else result.stderr.strip()

def reopen_closed_window(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "t" using {{command down, shift down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Reopened last closed window in {browser}." if result.returncode == 0 else result.stderr.strip()

def open_history(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "y" using {{command down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Opened history in {browser}." if result.returncode == 0 else result.stderr.strip()

def undo_tab_action(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "z" using {{command down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Undid last action in {browser}." if result.returncode == 0 else result.stderr.strip()

def redo_tab_action(browser):
    script = f'''
    tell application "{browser}" to activate
    tell application "System Events"
        keystroke "z" using {{command down, shift down}}
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"Redid last action in {browser}." if result.returncode == 0 else result.stderr.strip()

# Coding Tools ================================================

def run_code(file_path):
    try:
        result = subprocess.run(["python3", file_path], capture_output=True, text=True, timeout=10)
        return f"Output:\n{result.stdout}\nErrors:\n{result.stderr}"
    except Exception as e:
        return f"Failed to run code: {str(e)}"

def test_code(file_path):
    try:
        result = subprocess.run(["python3", "-m", "unittest", file_path], capture_output=True, text=True, timeout=10)
        return f"Test Results:\n{result.stdout}\n{result.stderr}"
    except Exception as e:
        return f"Failed to test code: {str(e)}"

def debug_code():
    return "Interactive debugging is not supported via background execution."

def open_folder_in_editor(file_path):
    try:
        subprocess.run(["open", "-a", "Visual Studio Code", file_path])
        return f"Opened {file_path} in VS Code."
    except Exception:
        subprocess.run(["open", file_path])
        return f"Opened {file_path} in Finder."

def create_file(file_name, file_path):
    full_path = os.path.join(file_path, file_name)
    try:
        with open(full_path, 'w') as f:
            f.write("")
        return f"Created file at {full_path}"
    except Exception as e:
        return f"Failed to create file: {str(e)}"

def delete_file(file_name, file_path):
    full_path = os.path.join(file_path, file_name)
    try:
        os.remove(full_path)
        return f"Deleted file at {full_path}"
    except Exception as e:
        return f"Failed to delete file: {str(e)}"

def install_package(package_name, tool="pip3"):
    try:
        result = subprocess.run([tool, "install", package_name], capture_output=True, text=True)
        return f"Installed {package_name}:\n{result.stdout}"
    except Exception as e:
        return f"Failed to install package: {str(e)}"

def update_package(package_name, tool="pip3"):
    try:
        result = subprocess.run([tool, "install", "--upgrade", package_name], capture_output=True, text=True)
        return f"Updated {package_name}:\n{result.stdout}"
    except Exception as e:
        return f"Failed to update package: {str(e)}"

def uninstall_package(package_name, tool="pip3"):
    try:
        result = subprocess.run([tool, "uninstall", "-y", package_name], capture_output=True, text=True)
        return f"Uninstalled {package_name}:\n{result.stdout}"
    except Exception as e:
        return f"Failed to uninstall package: {str(e)}"


# System Tools ================================================

def capture_screen(save_path="~/Desktop/screenshot.png"):
    expanded_path = os.path.expanduser(save_path)
    result = subprocess.run(["screencapture", expanded_path], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Screenshot saved to {expanded_path}"
    return f"Failed to capture screen: {result.stderr.strip()}"

def record_screen(duration_seconds, save_path="~/Desktop/screen_recording.mov"):
    expanded_path = os.path.expanduser(save_path)
    # -v = record video, -V = duration
    result = subprocess.run(["screencapture", "-v", "-V", str(duration_seconds), expanded_path], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Screen recorded for {duration_seconds} seconds and saved to {expanded_path}"
    return f"Failed to record screen: {result.stderr.strip()}"


# Cursor =======================================================
pyautogui.FAILSAFE = True

def move_cursor(end_x, end_y, start_x=None, start_y=None):
    try:
        if start_x is not None and start_y is not None:
            pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.moveTo(int(end_x), int(end_y), duration=0.2)
        return f"Moved cursor to ({end_x}, {end_y})."
    except Exception as e:
        return f"Failed to move cursor: {str(e)}"

def left_click_cursor():
    try:
        pyautogui.click(button='left')
        return "Left clicked cursor."
    except Exception as e:
        return f"Failed left click: {str(e)}"

def left_double_click_cursor():
    try:
        pyautogui.doubleClick(button='left')
        return "Left double clicked cursor."
    except Exception as e:
        return f"Failed double click: {str(e)}"

def left_drag_cursor(start_x, start_y, end_x, end_y):
    try:
        pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.dragTo(int(end_x), int(end_y), duration=0.5, button='left')
        return f"Left dragged cursor from ({start_x}, {start_y}) to ({end_x}, {end_y})."
    except Exception as e:
        return f"Failed left drag: {str(e)}"

def right_click_cursor():
    try:
        pyautogui.click(button='right')
        return "Right clicked cursor."
    except Exception as e:
        return f"Failed right click: {str(e)}"

def right_double_click_cursor():
    try:
        pyautogui.doubleClick(button='right')
        return "Right double clicked cursor."
    except Exception as e:
        return f"Failed right double click: {str(e)}"

def right_drag_cursor(start_x, start_y, end_x, end_y):
    try:
        pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.dragTo(int(end_x), int(end_y), duration=0.5, button='right')
        return f"Right dragged cursor from ({start_x}, {start_y}) to ({end_x}, {end_y})."
    except Exception as e:
        return f"Failed right drag: {str(e)}"

def scroll_cursor(direction, amount=5):
    try:
        clicks = int(amount) if direction.lower() == 'up' else -int(amount)
        pyautogui.scroll(clicks)
        return f"Scrolled {direction} by {amount} units."
    except Exception as e:
        return f"Failed to scroll: {str(e)}"


# Text =======================================================

def type_text(text):
    try:
        pyautogui.write(text, interval=0.01)
        return "Text typed successfully."
    except Exception as e:
        return f"Failed to type text: {str(e)}"

def delete_text():
    try:
        pyautogui.press('backspace')
        return "Deleted text."
    except Exception as e:
        return f"Failed to delete text: {str(e)}"

def copy_text():
    try:
        pyautogui.hotkey('command', 'c')
        return "Copied text."
    except Exception as e:
        return f"Failed to copy text: {str(e)}"

def cut_text():
    try:
        pyautogui.hotkey('command', 'x')
        return "Cut text."
    except Exception as e:
        return f"Failed to cut text: {str(e)}"

def paste_text():
    try:
        pyautogui.hotkey('command', 'v')
        return "Pasted text."
    except Exception as e:
        return f"Failed to paste text: {str(e)}"


# Universal Commands =========================================

def undo():
    try:
        pyautogui.hotkey('command', 'z')
        return "Performed undo."
    except Exception as e:
        return f"Failed undo: {str(e)}"

def redo():
    try:
        pyautogui.hotkey('command', 'shift', 'z')
        return "Performed redo."
    except Exception as e:
        return f"Failed redo: {str(e)}"

def select_all():
    try:
        pyautogui.hotkey('command', 'a')
        return "Selected all."
    except Exception as e:
        return f"Failed to select all: {str(e)}"

def save():
    try:
        pyautogui.hotkey('command', 's')
        return "Saved current context."
    except Exception as e:
        return f"Failed to save: {str(e)}"


# System Poweroffs ===========================================

def restart(user_confirmation):
    if str(user_confirmation).lower() in ['yes', 'true', '1', 'y']:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'])
        return "Restarting system."
    return "Restart cancelled by user."

def shutdown(user_confirmation):
    if str(user_confirmation).lower() in ['yes', 'true', '1', 'y']:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'])
        return "Shutting down system."
    return "Shutdown cancelled by user."

def screensaver():
    subprocess.run(["open", "-a", "ScreenSaverEngine"])
    return "Started screensaver."

def sleep():
    subprocess.run(["pmset", "displaysleepnow"])
    return "Display put to sleep."

def lock_screen():
    script = 'tell application "System Events" to keystroke "q" using {control down, command down}'
    subprocess.run(["osascript", "-e", script])
    return "Screen locked."

def log_out(user_confirmation):
    if str(user_confirmation).lower() in ['yes', 'true', '1', 'y']:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to log out'])
        return "Logging out."
    return "Log out cancelled by user."


# User Focus Modes and Commands ==============================

def toggle_stage_manager():
    return "Stage Manager toggling requires unreliable Control Center UI scripting on modern macOS and has been bypassed for safety."


# User Preferences ===========================================

def set_volume(amount):
    try:
        val = max(0, min(100, int(amount)))
        subprocess.run(["osascript", "-e", f"set volume output volume {val}"])
        return f"Volume set to {val}%."
    except Exception as e:
        return f"Failed to set volume: {str(e)}"

def set_brightness(amount):
    return "Native display brightness control via terminal requires a third-party tool like 'brightness' installed via Homebrew."

def set_key_glow(amount):
    return "Native keyboard backlight control via terminal requires third-party libraries and cannot be reliably executed natively."

def set_dark_mode(state):
    try:
        is_dark = "true" if str(state).lower() in ['yes', 'true', '1', 'on'] else "false"
        script = f'tell application "System Events" to tell appearance preferences to set dark mode to {is_dark}'
        subprocess.run(["osascript", "-e", script])
        return f"Dark mode set to {is_dark}."
    except Exception as e:
        return f"Failed to set dark mode: {str(e)}"


# Spotify Commands ===========================================

def spotify_play():
    result = subprocess.run(["osascript", "-e", 'tell application "Spotify" to play'], capture_output=True, text=True)
    return "Spotify playing." if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def spotify_pause():
    result = subprocess.run(["osascript", "-e", 'tell application "Spotify" to pause'], capture_output=True, text=True)
    return "Spotify paused." if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def spotify_next():
    result = subprocess.run(["osascript", "-e", 'tell application "Spotify" to next track'], capture_output=True, text=True)
    return "Skipped to next track on Spotify." if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def spotify_previous():
    result = subprocess.run(["osascript", "-e", 'tell application "Spotify" to previous track'], capture_output=True, text=True)
    return "Returned to previous track on Spotify." if result.returncode == 0 else f"Error: {result.stderr.strip()}"

def play_spotify_playlist(playlist_name):
    # Your personal "Speed Dial" dictionary
    # Format must be strictly lowercase for the keys
    playlists = {
        "fav songs": "spotify:playlist:37i9dQZF1DX70RN3TfR079", # Example: Spotify's Workout mix
        "liked songs": "spotify:collection:tracks"              # This is the special URI for Liked Songs!
    }

    name_lower = str(playlist_name).lower()
    
    if name_lower in playlists:
        uri = playlists[name_lower]
        # The AppleScript command to play a specific URI
        script = f'tell application "Spotify" to play track "{uri}"'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"Successfully started playing the '{playlist_name}' playlist."
        else:
            return f"Error playing playlist: {result.stderr.strip()}"
    else:
        # Crucial: If Buddy doesn't know the playlist, he tells the Manager to inform you.
        return f"Error: Playlist '{playlist_name}' is not saved in your dictionary. Tell the user to add it to tools.py."

def get_clipboard():
    """Returns the text currently stored in the system clipboard."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout

def set_clipboard(text):
    """Sets text directly to the system clipboard."""
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
    process.communicate(text)
    return "Copied text to clipboard."

def run_terminal_command(command):
    """Executes a bash command in the terminal and returns output."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return f"Failed to execute command: {str(e)}"

def send_notification(title, message):
    """Sends a native macOS desktop notification."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script])
    return "Notification sent."

def search_local_files(query):
    """Searches local files on the Mac using Spotlight index (mdfind)."""
    try:
        result = subprocess.run(
            ["mdfind", "-name", query], capture_output=True, text=True, timeout=5
        )
        files = result.stdout.strip().split("\n")[:5]  # Limit top 5 matches
        return f"Found files:\n" + "\n".join(files) if files[0] else "No files found."
    except Exception as e:
        return f"File search failed: {str(e)}"