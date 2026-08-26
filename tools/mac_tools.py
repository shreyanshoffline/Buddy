"""
macOS Agent Tools - Masterpiece Edition
=======================================
Comprehensive, safe toolset for an AI agent controlling a Mac.
All dangerous operations (delete, kill, shutdown, empty trash, etc.)
require explicit user confirmation via native macOS dialog.

Designed for macOS only (AppleScript + native commands).
Future: abstract backend for Linux/Windows.

Dependencies (install via manage_package if missing):
  - pyautogui
  - ddgs (or duckduckgo-search)
  - google-auth, google-auth-oauthlib, google-api-python-client  (for Gmail)
  - Optional: psutil, send2trash

Place Gmail credentials at:
  ~/Buddy/credentials.json
  ~/Buddy/token.json
"""

import os
import re
import base64
import json
import sqlite3
import subprocess
import platform
import shutil
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

# Optional imports with graceful fallback
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from ddgs import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    HAS_GMAIL = True
except ImportError:
    HAS_GMAIL = False


# =============================================================================
# CONFIG & PATHS
# =============================================================================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
TOKEN_PATH = os.path.expanduser("~/Buddy/token.json")
CREDS_PATH = os.path.expanduser("~/Buddy/credentials.json")

# Patterns that trigger mandatory confirmation for run_terminal_command
DANGEROUS_COMMAND_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r)",  # rm -rf, rm -r, etc.
    r"\bsudo\b",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r">\s*/dev/",
    r"\bchmod\s+777\b",
    r"\bchown\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bkillall\b",
    r"\bpkill\b",
    r"\bdiskutil\s+erase",
    r"\blaunchctl\s+unload",
]


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _run_applescript(script: str, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run an AppleScript and return the completed process."""
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _escape_applescript(text: str) -> str:
    """Escape double quotes and backslashes for safe AppleScript string insertion."""
    if text is None:
        return ""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _confirm(title: str, message: str, default_cancel: bool = True) -> bool:
    """
    Show a native macOS confirmation dialog.
    Returns True only if the user clicks "Allow".
    """
    safe_title = _escape_applescript(title)
    safe_message = _escape_applescript(message)
    default_btn = "Cancel" if default_cancel else "Allow"
    script = f'''
    try
        set theResponse to display dialog "{safe_message}" with title "{safe_title}" ¬
            buttons {{"Cancel", "Allow"}} default button "{default_btn}" with icon caution
        return button returned of theResponse
    on error
        return "Cancel"
    end try
    '''
    try:
        result = _run_applescript(script, timeout=60)
        return result.stdout.strip() == "Allow"
    except Exception:
        return False


def _is_dangerous_command(command: str) -> bool:
    """Heuristic check whether a shell command looks destructive."""
    cmd_lower = command.lower()
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True
    return False


def _expand(path: str) -> str:
    """Expand ~ and make absolute."""
    return os.path.abspath(os.path.expanduser(path))


# =============================================================================
# APP TOOLS
# =============================================================================

def open_app(app: str) -> str:
    """Launches an application installed on the Mac by name."""
    result = subprocess.run(["open", "-a", app], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Opened {app}."
    return f"Couldn't open {app}: {result.stderr.strip()}"


def close_app(app: str) -> str:
    """Gracefully quits an application."""
    try:
        result = _run_applescript(f'quit app "{_escape_applescript(app)}"', timeout=5)
        if result.returncode == 0:
            return f"Closed {app}."
        return f"Couldn't close {app}: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"Couldn't close {app}: Timeout expired."


def force_close_app(app: str) -> str:
    """Force closes a non-responsive app using pkill. Requires confirmation."""
    if not _confirm("Force Quit App", f"Force quit '{app}'? Unsaved work will be lost."):
        return "Force quit cancelled by user."
    result = subprocess.run(["pkill", "-f", app], capture_output=True, text=True)
    if result.returncode == 0:
        return f"Force closed {app}."
    return f"Couldn't force close {app}: {result.stderr.strip()}"


def list_apps() -> List[str]:
    """Lists installed applications in /Applications and /System/Applications."""
    result = subprocess.run(
        [
            "/bin/sh", "-c",
            "find /Applications /System/Applications -maxdepth 2 -name '*.app' 2>/dev/null "
            "| grep -v -E 'Utilities|\\.localized' "
            "| awk -F'/' '{print $NF}' | sed 's/\\.app//' | sort -u",
        ],
        capture_output=True, text=True,
    )
    return [a for a in result.stdout.strip().split("\n") if a] if result.returncode == 0 else []


def list_apps_running() -> List[str]:
    """Lists all active visible GUI applications currently running."""
    result = _run_applescript(
        'tell application "System Events" to get name of (processes where background only is false)'
    )
    if result.returncode == 0:
        return [a.strip() for a in result.stdout.strip().split(",") if a.strip()]
    return []


def get_frontmost_app() -> str:
    """Returns the name of the currently frontmost (focused) application."""
    result = _run_applescript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return f"Error: {result.stderr.strip()}"


def activate_app(app: str) -> str:
    """Brings an already-running app to the foreground (or launches it)."""
    result = _run_applescript(f'tell application "{_escape_applescript(app)}" to activate')
    if result.returncode == 0:
        return f"Activated {app}."
    return f"Couldn't activate {app}: {result.stderr.strip()}"


# =============================================================================
# WEB / BROWSER TOOLS
# =============================================================================

def web_search(query: str, max_results: int = 5) -> str:
    """Searches the web via DuckDuckGo for live facts, current information, or links."""
    if not HAS_DDGS:
        return "Error: ddgs / duckduckgo-search package not installed. Use manage_package to install it."
    try:
        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return f"No search results found for: '{query}'"
        formatted = f"DuckDuckGo Search Results for '{query}':\n"
        for i, res in enumerate(results, 1):
            title = res.get("title", "No Title")
            snippet = res.get("body", "No Description")
            url = res.get("href", "No URL")
            formatted += f"\n{i}. {title}\n   Snippet: {snippet}\n   URL: {url}\n"
        return formatted
    except Exception as e:
        return f"Failed to execute web search: {str(e)}"


def open_url(url: str, browser: str = "Google Chrome") -> str:
    """Opens a specific URL in the given browser (default Google Chrome)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    result = subprocess.run(["open", "-a", browser, url], capture_output=True, text=True)
    return f"Opened {url} in {browser}." if result.returncode == 0 else f"Couldn't open {url}: {result.stderr.strip()}"


def browser_action(action: str, browser: str = "Google Chrome") -> str:
    """
    Performs common browser actions via keyboard shortcuts.
    Supported: new_tab, new_window, reopen_tab, reopen_window, open_history, undo, redo, close_tab, next_tab, prev_tab
    """
    key_map = {
        "new_tab": ('t', "command"),
        "new_window": ('n', "command"),
        "open_history": ('y', "command"),
        "undo": ('z', "command"),
        "redo": ('z', "command shift"),
        "reopen_tab": ('t', "command shift"),
        "reopen_window": ('n', "command shift"),
        "close_tab": ('w', "command"),
        "next_tab": (']', "command shift"),
        "prev_tab": ('[', "command shift"),
    }
    if action not in key_map:
        return f"Unknown browser action: {action}. Supported: {list(key_map.keys())}"
    key, mods = key_map[action]
    mod_str = "command down"
    if "shift" in mods:
        mod_str = "command down, shift down"
    script = f'''
    tell application "{_escape_applescript(browser)}" to activate
    delay 0.3
    tell application "System Events"
        keystroke "{key}" using {{{mod_str}}}
    end tell
    '''
    result = _run_applescript(script)
    return f"Performed '{action}' in {browser}." if result.returncode == 0 else result.stderr.strip()


def list_open_tabs(browser: str = "Google Chrome") -> str:
    """Lists all currently open tabs in the browser, including titles and URLs, grouped by window."""
    script = f'''
    tell application "{_escape_applescript(browser)}"
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
    result = _run_applescript(script, timeout=15)
    if result.returncode == 0:
        return result.stdout.strip() or "No tabs found."
    return f"Couldn't list tabs: {result.stderr.strip()}"


def close_tab(website: str, browser: str = "Google Chrome") -> str:
    """Closes browser tabs whose URL contains the given keyword."""
    script = f'tell application "{_escape_applescript(browser)}" to close (tabs of front window whose URL contains "{_escape_applescript(website)}")'
    result = _run_applescript(script)
    return f"Closed tab(s) matching '{website}'." if result.returncode == 0 else f"Couldn't close tab: {result.stderr.strip()}"


def get_active_tab_info(browser: str = "Google Chrome") -> Dict[str, str]:
    """Returns title and URL of the currently active tab."""
    script = f'''
    tell application "{_escape_applescript(browser)}"
        set t to active tab of front window
        return (title of t) & "|||" & (URL of t)
    end tell
    '''
    result = _run_applescript(script)
    if result.returncode == 0 and "|||" in result.stdout:
        title, url = result.stdout.strip().split("|||", 1)
        return {"title": title, "url": url}
    return {"error": result.stderr.strip() or "Could not get active tab"}


def navigate_active_tab(url: str, browser: str = "Google Chrome") -> str:
    """Navigates the currently active tab to a new URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    script = f'''
    tell application "{_escape_applescript(browser)}"
        set URL of active tab of front window to "{_escape_applescript(url)}"
    end tell
    '''
    result = _run_applescript(script)
    return f"Navigated to {url}." if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


# =============================================================================
# FILE SYSTEM TOOLS
# =============================================================================

def list_directory(path: str = "~", max_entries: int = 100) -> Union[List[str], str]:
    """Lists contents of a directory (names only)."""
    p = _expand(path)
    if not os.path.isdir(p):
        return f"Not a directory or does not exist: {p}"
    try:
        entries = sorted(os.listdir(p))[:max_entries]
        return entries
    except PermissionError:
        return f"Permission denied: {p}"
    except Exception as e:
        return f"Error listing {p}: {e}"


def read_file_content(path: str, max_chars: int = 50000) -> str:
    """Reads text content of a file (truncated if very large)."""
    p = _expand(path)
    if not os.path.isfile(p):
        return f"File not found: {p}"
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 1)
        if len(content) > max_chars:
            return content[:max_chars] + f"\n\n... [truncated, file larger than {max_chars} chars]"
        return content
    except Exception as e:
        return f"Error reading {p}: {e}"


def write_file_content(path: str, content: str, overwrite: bool = False) -> str:
    """Writes text content to a file. Requires confirmation if file exists and overwrite=False."""
    p = _expand(path)
    if os.path.exists(p) and not overwrite:
        if not _confirm("Overwrite File?", f"File already exists:\n{p}\n\nOverwrite it?"):
            return "Write cancelled by user."
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} characters to {p}"
    except Exception as e:
        return f"Error writing {p}: {e}"


def append_to_file(path: str, content: str) -> str:
    """Appends text to the end of a file (creates if missing)."""
    p = _expand(path)
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {p}"
    except Exception as e:
        return f"Error appending to {p}: {e}"


def create_file(file_name: str, file_path: str) -> str:
    """Creates an empty file at the given directory path."""
    full_dir = _expand(file_path)
    full_path = os.path.join(full_dir, file_name)
    try:
        os.makedirs(full_dir, exist_ok=True)
        if os.path.exists(full_path):
            return f"File already exists: {full_path}"
        with open(full_path, "w") as f:
            f.write("")
        return f"Created empty file at {full_path}"
    except Exception as e:
        return f"Failed to create file: {e}"


def create_directory(path: str) -> str:
    """Creates a directory (and parents if needed)."""
    p = _expand(path)
    try:
        os.makedirs(p, exist_ok=True)
        return f"Directory ready: {p}"
    except Exception as e:
        return f"Failed to create directory: {e}"


def copy_file(src: str, dst: str) -> str:
    """Copies a file or directory tree to a new location."""
    s, d = _expand(src), _expand(dst)
    try:
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
            shutil.copy2(s, d)
        return f"Copied {s} → {d}"
    except Exception as e:
        return f"Copy failed: {e}"


def move_file(src: str, dst: str) -> str:
    """Moves/renames a file or directory. Requires confirmation."""
    s, d = _expand(src), _expand(dst)
    if not _confirm("Confirm Move", f"Move:\n{s}\n→\n{d}?"):
        return "Move cancelled by user."
    try:
        os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
        shutil.move(s, d)
        return f"Moved {s} → {d}"
    except Exception as e:
        return f"Move failed: {e}"


def rename_file(path: str, new_name: str) -> str:
    """Renames a file or folder (stays in same directory)."""
    p = _expand(path)
    new_path = os.path.join(os.path.dirname(p), new_name)
    if not _confirm("Confirm Rename", f"Rename:\n{os.path.basename(p)}\n→\n{new_name}?"):
        return "Rename cancelled by user."
    try:
        os.rename(p, new_path)
        return f"Renamed to {new_path}"
    except Exception as e:
        return f"Rename failed: {e}"


def trash_file(path: str) -> str:
    """Moves a file or folder to the Trash (recoverable). Uses Finder."""
    p = _expand(path)
    if not os.path.exists(p):
        return f"Path does not exist: {p}"
    # Use Finder to move to Trash (safe)
    script = f'''
    tell application "Finder"
        delete (POSIX file "{_escape_applescript(p)}" as alias)
    end tell
    '''
    result = _run_applescript(script)
    if result.returncode == 0:
        return f"Moved to Trash: {p}"
    return f"Could not trash {p}: {result.stderr.strip()}"


def delete_file(file_name: str, file_path: str) -> str:
    """
    Permanently deletes a file (NOT recoverable).
    Requires explicit user confirmation. Prefer trash_file when possible.
    """
    full_path = os.path.join(_expand(file_path), file_name)
    if not os.path.exists(full_path):
        return f"File not found: {full_path}"
    if not _confirm(
        "⚠️ PERMANENT DELETE",
        f"This will PERMANENTLY delete (cannot undo):\n\n{full_path}\n\nAre you absolutely sure?"
    ):
        return "Permanent deletion cancelled by user."
    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return f"Permanently deleted: {full_path}"
    except Exception as e:
        return f"Delete failed: {e}"


def empty_trash() -> str:
    """Empties the macOS Trash. Requires confirmation."""
    if not _confirm("Empty Trash?", "This will permanently delete all items in the Trash. Continue?"):
        return "Empty Trash cancelled by user."
    result = _run_applescript('tell application "Finder" to empty trash')
    if result.returncode == 0:
        return "Trash emptied."
    return f"Could not empty trash: {result.stderr.strip()}"


def get_file_info(path: str) -> Dict[str, Any]:
    """Returns size, created, modified, is_dir, etc. for a path."""
    p = _expand(path)
    if not os.path.exists(p):
        return {"error": f"Path not found: {p}"}
    try:
        st = os.stat(p)
        return {
            "path": p,
            "is_dir": os.path.isdir(p),
            "size_bytes": st.st_size,
            "size_human": _human_size(st.st_size),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(st.st_birthtime).isoformat() if hasattr(st, "st_birthtime") else None,
            "permissions": oct(st.st_mode)[-3:],
        }
    except Exception as e:
        return {"error": str(e)}


def search_local_files(query: str, max_results: int = 10) -> str:
    """Searches for local files using Spotlight (mdfind)."""
    try:
        result = subprocess.run(
            ["mdfind", "-name", query],
            capture_output=True, text=True, timeout=8,
        )
        files = [f for f in result.stdout.strip().split("\n") if f][:max_results]
        if files:
            return "Found files:\n" + "\n".join(files)
        return "No files found."
    except Exception as e:
        return f"File search failed: {e}"


def open_in_finder(path: str) -> str:
    """Reveals a file or folder in Finder."""
    p = _expand(path)
    result = subprocess.run(["open", "-R", p], capture_output=True, text=True)
    return f"Revealed in Finder: {p}" if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def open_folder_in_editor(file_path: str) -> str:
    """Opens a folder or file in VS Code (falls back to Finder)."""
    expanded = _expand(file_path)
    try:
        subprocess.run(["open", "-a", "Visual Studio Code", expanded], check=False)
        return f"Opened {expanded} in VS Code."
    except Exception:
        subprocess.run(["open", expanded])
        return f"Opened {expanded} in Finder."


def _human_size(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


# =============================================================================
# SYSTEM & SHELL
# =============================================================================

def run_terminal_command(command: str, timeout: int = 30) -> str:
    """
    Executes a raw bash command and returns stdout + stderr.
    Dangerous-looking commands require user confirmation first.
    """
    if _is_dangerous_command(command):
        if not _confirm(
            "⚠️ Potentially Dangerous Command",
            f"This command looks destructive:\n\n{command}\n\nAllow execution?"
        ):
            return "Command cancelled by user (dangerous pattern detected)."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            out += f"\n[exit code: {result.returncode}]"
        return out
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s."
    except Exception as e:
        return f"Failed to execute command: {e}"


def get_clipboard() -> str:
    """Reads and returns text currently stored in the system clipboard."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"


def set_clipboard(text: str) -> str:
    """Writes text into the system clipboard."""
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
    process.communicate(text)
    return "Copied text to system clipboard."


def send_notification(title: str, message: str) -> str:
    """Triggers a native macOS desktop banner notification."""
    script = f'display notification "{_escape_applescript(message)}" with title "{_escape_applescript(title)}"'
    _run_applescript(script)
    return f"Notification sent: {title}"


def capture_screen(save_path: str = "~/Desktop/screenshot.png") -> str:
    """Takes a screenshot of the entire display and saves it."""
    expanded = _expand(save_path)
    result = subprocess.run(["screencapture", "-x", expanded], capture_output=True, text=True)
    return f"Screenshot saved to {expanded}" if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def set_volume(amount: int) -> str:
    """Sets the macOS output volume (0-100)."""
    try:
        val = max(0, min(100, int(amount)))
        _run_applescript(f"set volume output volume {val}")
        return f"Volume set to {val}%."
    except Exception as e:
        return f"Failed to set volume: {e}"


def get_volume() -> str:
    """Returns the current output volume level (0-100)."""
    result = _run_applescript("output volume of (get volume settings)")
    if result.returncode == 0:
        return f"Current volume: {result.stdout.strip()}%"
    return f"Error: {result.stderr.strip()}"


def set_dark_mode(state: str) -> str:
    """Enables or disables macOS system Dark Mode. state = 'on' or 'off'."""
    is_dark = "true" if state.lower() in ("on", "true", "yes", "1") else "false"
    script = f'tell application "System Events" to tell appearance preferences to set dark mode to {is_dark}'
    result = _run_applescript(script)
    return f"Dark mode set to {state}." if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def get_dark_mode() -> str:
    """Returns whether Dark Mode is currently enabled."""
    result = _run_applescript(
        'tell application "System Events" to tell appearance preferences to get dark mode'
    )
    if result.returncode == 0:
        return "Dark Mode is ON" if result.stdout.strip() == "true" else "Dark Mode is OFF"
    return f"Error: {result.stderr.strip()}"


def get_system_info() -> Dict[str, str]:
    """Returns basic system information (macOS version, hardware, etc.)."""
    info = {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
    }
    # macOS specific
    try:
        ver = subprocess.check_output(["sw_vers"], text=True)
        for line in ver.strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
    except Exception:
        pass
    return info


def get_battery_status() -> str:
    """Returns battery percentage and charging status (laptops)."""
    try:
        result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "Could not read battery info (desktop?)."
    except Exception as e:
        return f"Error: {e}"


def get_disk_space(path: str = "/") -> str:
    """Returns human-readable disk usage for the given path."""
    try:
        result = subprocess.run(["df", "-h", path], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except Exception as e:
        return f"Error: {e}"


def get_memory_info() -> str:
    """Returns memory pressure / usage summary."""
    try:
        result = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # fallback
        result = subprocess.run(["vm_stat"], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def list_processes(limit: int = 30) -> str:
    """Lists top processes by CPU usage."""
    try:
        result = subprocess.run(
            ["ps", "aux", "-r"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        return "\n".join(lines[: limit + 1])  # header + N
    except Exception as e:
        return f"Error: {e}"


def kill_process(pid_or_name: str) -> str:
    """Kills a process by PID or name. Requires confirmation."""
    if not _confirm("Kill Process?", f"Terminate process '{pid_or_name}'?\nUnsaved work in that app may be lost."):
        return "Kill cancelled by user."
    try:
        # Try as PID first
        if str(pid_or_name).isdigit():
            result = subprocess.run(["kill", str(pid_or_name)], capture_output=True, text=True)
        else:
            result = subprocess.run(["pkill", "-f", str(pid_or_name)], capture_output=True, text=True)
        if result.returncode == 0:
            return f"Killed {pid_or_name}."
        return f"Could not kill {pid_or_name}: {result.stderr.strip()}"
    except Exception as e:
        return f"Error: {e}"


def lock_screen() -> str:
    """Immediately locks the screen (requires password to unlock)."""
    # Works on modern macOS
    result = subprocess.run(
        ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
        capture_output=True, text=True,
    )
    # Alternative
    if result.returncode != 0:
        _run_applescript('tell application "System Events" to keystroke "q" using {command down, control down}')
    return "Screen lock initiated."


def sleep_display() -> str:
    """Puts the display to sleep (computer stays awake)."""
    result = subprocess.run(["pmset", "displaysleepnow"], capture_output=True, text=True)
    return "Display sleeping." if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def start_screensaver() -> str:
    """Starts the system screensaver."""
    result = subprocess.run(
        ["open", "-a", "ScreenSaverEngine"], capture_output=True, text=True
    )
    return "Screensaver started." if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


# =============================================================================
# NETWORK
# =============================================================================

def get_ip_address() -> str:
    """Returns local and public-ish network info."""
    try:
        local = subprocess.check_output(["ipconfig", "getifaddr", "en0"], text=True).strip()
    except Exception:
        local = "unknown (en0)"
    try:
        # quick public IP (may fail offline)
        public = subprocess.check_output(
            ["curl", "-s", "--max-time", "3", "https://api.ipify.org"], text=True
        ).strip()
    except Exception:
        public = "unavailable"
    return f"Local (en0): {local}\nPublic: {public}"


def ping_host(host: str, count: int = 3) -> str:
    """Pings a host and returns the result summary."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True, text=True, timeout=count * 3 + 2,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return f"Ping failed: {e}"


def download_file(url: str, save_path: str) -> str:
    """Downloads a file from a URL to the given local path using curl."""
    p = _expand(save_path)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    try:
        result = subprocess.run(
            ["curl", "-L", "--fail", "-o", p, url],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            size = os.path.getsize(p)
            return f"Downloaded to {p} ({_human_size(size)})"
        return f"Download failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Download error: {e}"


def check_internet() -> str:
    """Quick check whether the machine can reach the internet."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2000", "1.1.1.1"],
            capture_output=True, text=True, timeout=5,
        )
        return "Internet appears reachable." if result.returncode == 0 else "No internet connectivity detected."
    except Exception:
        return "Could not determine internet status."


# =============================================================================
# SPOTIFY & APPLE MUSIC
# =============================================================================

def spotify_control(action: str) -> str:
    """Controls active Spotify playback: play, pause, next, previous."""
    action_map = {
        "play": "play",
        "pause": "pause",
        "next": "next track",
        "previous": "previous track",
    }
    if action not in action_map:
        return f"Unknown Spotify action: {action}"
    script = f'tell application "Spotify" to {action_map[action]}'
    result = _run_applescript(script)
    return f"Spotify: {action}" if result.returncode == 0 else f"Spotify Error: {result.stderr.strip()}"


def play_spotify_playlist(playlist_name: str) -> str:
    """Plays a saved playlist by friendly name (extend the dict as needed)."""
    playlists = {
        "fav songs": "spotify:playlist:37i9dQZF1DX70RN3TfR079",
        "liked songs": "spotify:collection:tracks",
    }
    name_lower = str(playlist_name).lower()
    if name_lower not in playlists:
        return f"Playlist '{playlist_name}' not in the built-in mapping. Known: {list(playlists.keys())}"
    uri = playlists[name_lower]
    script = f'tell application "Spotify" to play track "{uri}"'
    result = _run_applescript(script)
    return f"Playing '{playlist_name}' on Spotify." if result.returncode == 0 else f"Error: {result.stderr.strip()}"


def music_control(action: str) -> str:
    """Controls the Apple Music / iTunes app: play, pause, next, previous."""
    action_map = {
        "play": "play",
        "pause": "pause",
        "next": "next track",
        "previous": "previous track",
    }
    if action not in action_map:
        return f"Unknown Music action: {action}"
    script = f'tell application "Music" to {action_map[action]}'
    result = _run_applescript(script)
    return f"Music: {action}" if result.returncode == 0 else f"Music Error: {result.stderr.strip()}"


# =============================================================================
# GMAIL (requires credentials in ~/Buddy/)
# =============================================================================

def _get_gmail_service():
    if not HAS_GMAIL:
        raise RuntimeError("Gmail libraries not installed. Run manage_package('install', 'google-api-python-client') etc.")
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(f"Missing {CREDS_PATH}. Place your OAuth credentials there.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _clean_snippet(text: str) -> str:
    return re.sub(r"[\u200c\u200b\ufeff]+", "", text or "").strip()


def _fetch_messages(query: str, max_results: int) -> List[Dict]:
    service = _get_gmail_service()
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = results.get("messages", [])
    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": _clean_snippet(full.get("snippet", "")),
        })
    return emails


def get_recent_emails(days_back: int = 7, max_results: int = 10) -> List[Dict]:
    """Get recent inbox emails from the last `days_back` days."""
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"in:inbox after:{after_date}"
    return _fetch_messages(query, max_results)


def get_unread_emails(days_back: int = 7, max_results: int = 10) -> List[Dict]:
    """Get unread inbox emails from the last `days_back` days."""
    after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    query = f"in:inbox is:unread after:{after_date}"
    return _fetch_messages(query, max_results)


def create_draft(recipient: str, subject: str, body: str) -> Dict:
    """Create a new Gmail draft. Does NOT send it."""
    service = _get_gmail_service()
    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return {"draft_id": draft["id"], "recipient": recipient, "subject": subject}


def list_drafts(max_results: int = 10) -> List[Dict]:
    """List existing drafts (draft_id, to, subject)."""
    service = _get_gmail_service()
    results = service.users().drafts().list(userId="me", maxResults=max_results).execute()
    drafts = results.get("drafts", [])
    out = []
    for d in drafts:
        full = service.users().drafts().get(userId="me", id=d["id"]).execute()
        headers = {h["name"]: h["value"] for h in full["message"]["payload"]["headers"]}
        out.append({
            "draft_id": d["id"],
            "to": headers.get("To", ""),
            "subject": headers.get("Subject", ""),
        })
    return out


def modify_draft(draft_id: str, recipient: str = None, subject: str = None, body: str = None) -> Dict:
    """Modify an existing draft. Always pass full body if changing content."""
    service = _get_gmail_service()
    existing = service.users().drafts().get(userId="me", id=draft_id).execute()
    headers = {h["name"]: h["value"] for h in existing["message"]["payload"]["headers"]}
    new_recipient = recipient or headers.get("To", "")
    new_subject = subject or headers.get("Subject", "")
    new_body = body if body is not None else ""
    message = MIMEText(new_body)
    message["to"] = new_recipient
    message["subject"] = new_subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    updated = service.users().drafts().update(
        userId="me", id=draft_id, body={"message": {"raw": raw}}
    ).execute()
    return {"draft_id": updated["id"], "recipient": new_recipient, "subject": new_subject}


# =============================================================================
# iMESSAGE / MESSAGES
# =============================================================================

def lookup_contact_number(name: str) -> Dict:
    """Looks up a phone number for a contact by name (requires Contacts access)."""
    script = f'''
    tell application "Contacts"
        set thePerson to first person whose name contains "{_escape_applescript(name)}"
        set thePhone to value of first phone of thePerson
        return thePhone
    end tell
    '''
    result = _run_applescript(script)
    if result.returncode == 0:
        return {"success": True, "number": result.stdout.strip()}
    return {"success": False, "stderr": result.stderr.strip()}


def send_imessage(recipient: str, message: str) -> Dict:
    """Sends an iMessage to a phone number or email address."""
    safe_message = _escape_applescript(message)
    safe_recipient = _escape_applescript(recipient)
    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to participant "{safe_recipient}" of targetService
        send "{safe_message}" to targetBuddy
    end tell
    '''
    result = _run_applescript(script)
    return {
        "success": result.returncode == 0,
        "stderr": result.stderr.strip(),
        "stdout": result.stdout.strip(),
    }


def get_unread_messages(limit: int = 20) -> List[Dict]:
    """
    Reads unread incoming iMessages/SMS from the local Messages database.
    Requires Full Disk Access for the terminal/Python process.
    """
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    if not os.path.exists(db_path):
        return [{"error": "Messages database not found or inaccessible. Grant Full Disk Access."}]
    try:
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
                "chat_name": r["chat_name"] or r["chat_id"],
                "timestamp": ts.isoformat(),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def list_group_chats(limit: int = 20) -> List[Dict]:
    """Lists group chats with chat_id and display_name."""
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    if not os.path.exists(db_path):
        return [{"error": "Messages database not found. Grant Full Disk Access."}]
    try:
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
    except Exception as e:
        return [{"error": str(e)}]


def send_group_message(chat_name: str, message: str) -> Dict:
    """Sends an iMessage to an existing group chat by name or identifier."""
    safe_message = _escape_applescript(message)
    safe_chat_name = _escape_applescript(chat_name)
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
    result = _run_applescript(script)
    return {
        "success": result.returncode == 0,
        "stderr": result.stderr.strip(),
        "stdout": result.stdout.strip(),
    }


# =============================================================================
# PRODUCTIVITY: REMINDERS, NOTES, CALENDAR (basic)
# =============================================================================

def create_reminder(title: str, body: str = "", list_name: str = "Reminders") -> str:
    """Creates a new reminder in the Reminders app."""
    script = f'''
    tell application "Reminders"
        set theList to list "{_escape_applescript(list_name)}"
        make new reminder at end of reminders of theList with properties {{name:"{_escape_applescript(title)}", body:"{_escape_applescript(body)}"}}
    end tell
    '''
    result = _run_applescript(script)
    return f"Reminder created: {title}" if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def create_note(title: str, body: str = "") -> str:
    """Creates a new note in the Notes app."""
    # body can contain basic HTML-ish, but plain is safer
    script = f'''
    tell application "Notes"
        make new note at folder "Notes" with properties {{name:"{_escape_applescript(title)}", body:"{_escape_applescript(body)}"}}
    end tell
    '''
    result = _run_applescript(script)
    return f"Note created: {title}" if result.returncode == 0 else f"Failed: {result.stderr.strip()}"


def create_calendar_event(title: str, start_datetime: str, end_datetime: str = None, calendar_name: str = "Home") -> str:
    """
    Creates a basic calendar event.
    start_datetime / end_datetime format: "YYYY-MM-DD HH:MM" (local time).
    If end is omitted, defaults to +1 hour.
    """
    try:
        start = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M")
        if end_datetime:
            end = datetime.strptime(end_datetime, "%Y-%m-%d %H:%M")
        else:
            end = start + timedelta(hours=1)
    except ValueError:
        return "Invalid datetime format. Use YYYY-MM-DD HH:MM"
    # AppleScript date construction is verbose; use a simpler approach via shell + Calendar URL or AppleScript
    start_str = start.strftime("%A, %B %d, %Y at %I:%M %p")
    end_str = end.strftime("%A, %B %d, %Y at %I:%M %p")
    script = f'''
    set startDate to date "{start_str}"
    set endDate to date "{end_str}"
    tell application "Calendar"
        tell calendar "{_escape_applescript(calendar_name)}"
            make new event with properties {{summary:"{_escape_applescript(title)}", start date:startDate, end date:endDate}}
        end tell
    end tell
    '''
    result = _run_applescript(script, timeout=15)
    return f"Event created: {title}" if result.returncode == 0 else f"Failed (check calendar name & date parsing): {result.stderr.strip()}"


# =============================================================================
# INPUT SIMULATION (requires Accessibility permissions for pyautogui)
# =============================================================================

def type_text(text: str, interval: float = 0.02) -> str:
    """Types the given text using simulated keyboard (pyautogui)."""
    if not HAS_PYAUTOGUI:
        return "pyautogui not installed. Use manage_package to install it."
    try:
        pyautogui.write(text, interval=interval)
        return f"Typed {len(text)} characters."
    except Exception as e:
        return f"Typing failed: {e}"


def press_hotkey(*keys: str) -> str:
    """
    Presses a hotkey combination, e.g. press_hotkey('command', 'c') for copy.
    Common keys: command, option, control, shift, enter, tab, escape, up, down...
    """
    if not HAS_PYAUTOGUI:
        return "pyautogui not installed."
    try:
        pyautogui.hotkey(*keys)
        return f"Pressed hotkey: {'+'.join(keys)}"
    except Exception as e:
        return f"Hotkey failed: {e}"


def mouse_click(x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> str:
    """Clicks the mouse at (x,y) or current position. Coordinates are absolute screen pixels."""
    if not HAS_PYAUTOGUI:
        return "pyautogui not installed."
    try:
        if x is not None and y is not None:
            pyautogui.click(x, y, button=button, clicks=clicks)
            return f"Clicked {button} at ({x},{y}) x{clicks}"
        else:
            pyautogui.click(button=button, clicks=clicks)
            return f"Clicked {button} at current position x{clicks}"
    except Exception as e:
        return f"Click failed: {e}"


def mouse_move(x: int, y: int, duration: float = 0.3) -> str:
    """Moves the mouse cursor to absolute screen coordinates."""
    if not HAS_PYAUTOGUI:
        return "pyautogui not installed."
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return f"Moved mouse to ({x},{y})"
    except Exception as e:
        return f"Move failed: {e}"


def get_mouse_position() -> Dict[str, int]:
    """Returns current mouse (x, y) coordinates."""
    if not HAS_PYAUTOGUI:
        return {"error": "pyautogui not installed"}
    pos = pyautogui.position()
    return {"x": pos.x, "y": pos.y}


def get_screen_size() -> Dict[str, int]:
    """Returns screen width and height in pixels."""
    if not HAS_PYAUTOGUI:
        # fallback
        try:
            result = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"], text=True
            )
            return {"info": result[:500]}
        except Exception:
            return {"error": "Could not determine screen size"}
    size = pyautogui.size()
    return {"width": size.width, "height": size.height}


# =============================================================================
# SPEECH
# =============================================================================

def speak(text: str, voice: str = None, rate: int = None) -> str:
    """Speaks the given text using macOS `say` command."""
    cmd = ["say"]
    if voice:
        cmd.extend(["-v", voice])
    if rate:
        cmd.extend(["-r", str(rate)])
    cmd.append(text)
    try:
        subprocess.run(cmd, check=True, timeout=60)
        return f"Spoke: {text[:50]}..."
    except Exception as e:
        return f"Speak failed: {e}"


def list_voices() -> str:
    """Lists available macOS voices for the say command."""
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


# =============================================================================
# CODING / PACKAGE HELPERS
# =============================================================================

def run_code(file_path: str) -> str:
    """Runs a Python file and returns stdout and stderr (10s timeout)."""
    expanded = _expand(file_path)
    try:
        result = subprocess.run(
            ["python3", expanded], capture_output=True, text=True, timeout=15
        )
        return f"Output:\n{result.stdout}\nErrors:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Code execution timed out (15s)."
    except Exception as e:
        return f"Failed to run code: {e}"


def manage_package(action: str, package_name: str) -> str:
    """Installs, updates, or uninstalls a Python package using pip3."""
    cmd_map = {
        "install": ["pip3", "install", package_name],
        "update": ["pip3", "install", "--upgrade", package_name],
        "uninstall": ["pip3", "uninstall", "-y", package_name],
    }
    if action not in cmd_map:
        return f"Unknown package action: {action}. Use install/update/uninstall."
    try:
        result = subprocess.run(cmd_map[action], capture_output=True, text=True, timeout=120)
        return f"Package '{action}' for {package_name}:\n{result.stdout}\n{result.stderr}"
    except Exception as e:
        return f"Package action failed: {e}"


# =============================================================================
# TASK COMPLETION SIGNAL
# =============================================================================

def finish_task(summary: str) -> str:
    """
    Signals that all steps in the plan have been executed successfully.
    The summary should be a short, direct answer for the user (no bullet lists of steps).
    """
    return f"TASK_COMPLETE: {summary}"


# =============================================================================
# THINGS I CONSIDERED BUT DID NOT IMPLEMENT (tell me if you want them)
# =============================================================================
"""
Not coded because they are either:
- Too risky / hard to make safe
- Require extra permissions or third-party tools that may not be present
- Brittle across macOS versions

Possible future additions (ask me to implement any of these):

1. Window management (resize, move, list all windows of an app) – needs Accessibility + more complex AppleScript.
2. Full Calendar CRUD with attendees, recurrence, alerts.
3. Slack / Discord / Teams messaging via their APIs (needs user tokens).
4. OCR on screenshots (requires tesseract install).
5. Voice dictation / speech-to-text (requires additional setup).
6. Bluetooth / Wi-Fi toggle (networksetup, but can disconnect you).
7. Printer control / print file.
8. Time Machine status / start backup.
9. Focus modes / Do Not Disturb control.
10. Advanced GUI automation with image recognition (pyautogui.locateOnScreen).
11. Browser content extraction (get page text via AppleScript or JS injection – limited in Chrome).
12. Cross-OS abstraction layer (already planned for later).

If you need any of the above, tell me and I will carefully add them with proper confirmation guards.
"""