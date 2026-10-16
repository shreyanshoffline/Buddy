"""Small cross-platform adapter for actions shared by every desktop build.

Provider integrations and Apple automation stay in their own modules. This
file owns only the boring operating-system differences so the rest of Buddy
can ask for an action without branching on ``sys.platform`` everywhere.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def platform_name() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    if system == "Linux":
        # ChromeOS exposes a Linux environment to desktop applications.
        if os.environ.get("CHROMEOS_RELEASE_NAME") or os.environ.get("CROS_USER_ID_HASH"):
            return "chromeos"
        return "linux"
    return "other"


def capability_summary() -> dict:
    name = platform_name()
    return {
        "platform": name,
        "native_automation": name == "macos",
        "browser": True,
        "desktop_gui": True,
        "notes": (
            "Apple automation and Apple apps are available."
            if name == "macos"
            else "Common desktop, browser, file, and web actions are available; Apple-only tools are disabled."
        ),
    }


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    return value if value.startswith(("http://", "https://")) else "https://" + value


def _first_available(names: Iterable[str]) -> str | None:
    return next((shutil.which(name) for name in names if shutil.which(name)), None)


def open_url(url: str, browser: str | None = None) -> tuple[bool, str]:
    target = _normalize_url(url)
    system = platform_name()
    try:
        if system == "macos":
            command = ["open"]
            if browser:
                command += ["-a", browser]
            command.append(target)
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        elif system == "windows":
            executable = _first_available(_browser_commands(browser)) if browser else None
            if executable:
                result = subprocess.run([executable, target], capture_output=True, text=True, timeout=10)
            else:
                os.startfile(target)  # type: ignore[attr-defined]
                return True, f"Opened {target}."
        else:
            executable = _first_available(_browser_commands(browser)) or shutil.which("xdg-open")
            if not executable:
                return False, "No desktop URL opener is installed."
            result = subprocess.run([executable, target], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, f"Opened {target}" + (f" in {browser}." if browser else ".")
        return False, (result.stderr or "The operating system rejected the request.").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def _browser_commands(browser: str | None) -> list[str]:
    value = (browser or "").lower()
    if "chrome" in value:
        return ["google-chrome", "chrome", "chrome.exe"]
    if "edge" in value:
        return ["microsoft-edge", "msedge", "msedge.exe"]
    if "firefox" in value:
        return ["firefox", "firefox.exe"]
    if "safari" in value:
        return ["safari"]
    return [browser] if browser else []


def open_application(name: str) -> tuple[bool, str]:
    app = (name or "").strip()
    if not app:
        return False, "No application name was provided."
    system = platform_name()
    try:
        if system == "macos":
            result = subprocess.run(["open", "-a", app], capture_output=True, text=True, timeout=10)
        else:
            candidates = [app, app + ".exe"] if system == "windows" else [app]
            # Friendly browser names are common in the UI, while PATH uses
            # platform-specific executable names.
            if any(browser_word in app.lower() for browser_word in ("chrome", "edge", "firefox", "safari")):
                candidates = _browser_commands(app) + candidates
            executable = _first_available(candidates)
            if not executable:
                return False, f"Could not find {app} on PATH."
            result = subprocess.run([executable], capture_output=True, text=True, timeout=10)
        return (True, f"Opened {app}.") if result.returncode == 0 else (False, (result.stderr or "Open failed").strip())
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def close_application(name: str) -> tuple[bool, str]:
    """Ask the current OS to terminate an application gracefully."""
    app = (name or "").strip()
    if not app:
        return False, "No application name was provided."
    try:
        if platform_name() == "windows":
            image = app if app.lower().endswith(".exe") else app + ".exe"
            result = subprocess.run(["taskkill", "/IM", image, "/T"], capture_output=True, text=True, timeout=10)
        elif platform_name() == "macos":
            # AppleScript is kept in tools.tools so macOS permission errors
            # remain visible to the user.
            return False, "Use the macOS automation adapter for this application."
        else:
            result = subprocess.run(["pkill", "-TERM", "-f", app], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, f"Closed {app}."
        return False, (result.stderr or "Application was not running.").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def list_available_applications() -> list[str]:
    """Return common installed command-line launchers without scanning the disk."""
    names = (
        "google-chrome", "chrome", "microsoft-edge", "msedge", "firefox",
        "code", "slack", "spotify", "python", "python3", "terminal",
    )
    return sorted({Path(executable).name for executable in (_first_available([name]) for name in names) if executable})


def list_running_applications() -> list[str]:
    system = platform_name()
    try:
        if system == "windows":
            result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10)
            return sorted({line.split(",", 1)[0].strip('"') for line in result.stdout.splitlines() if line.strip()})
        command = ["ps", "-A", "-o", "comm="]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return sorted({Path(line.strip()).name for line in result.stdout.splitlines() if line.strip()})
    except (OSError, subprocess.SubprocessError):
        return []


def reveal_path(path: str) -> tuple[bool, str]:
    target = Path(os.path.expanduser(path)).resolve()
    if not target.exists():
        return False, f"Path does not exist: {target}"
    try:
        system = platform_name()
        if system == "macos":
            result = subprocess.run(["open", "-R", str(target)], capture_output=True, text=True, timeout=10)
        elif system == "windows":
            result = subprocess.run(["explorer", "/select," + str(target)], capture_output=True, text=True, timeout=10)
        else:
            folder = target if target.is_dir() else target.parent
            opener = shutil.which("xdg-open")
            if not opener:
                return False, "No desktop file opener is installed."
            result = subprocess.run([opener, str(folder)], capture_output=True, text=True, timeout=10)
        return (True, f"Opened {target}.") if result.returncode == 0 else (False, (result.stderr or "Open failed").strip())
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
