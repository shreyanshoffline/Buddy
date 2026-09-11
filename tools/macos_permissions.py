"""Honest macOS permission probes for the running Buddy process.

Buddy's Plugins switch is only a Buddy-side gate. macOS still has to grant
access to *this* process. Access given to Terminal, VS Code, or another
Python install does not count as access for a packaged Buddy.app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


PRIVACY_PANELS = {
    "full_disk_access": (
        "Full Disk Access",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    ),
    "folder_access": (
        "Files & Folders",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_FilesAndFolders",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders",
    ),
    "microphone": (
        "Microphone",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Microphone",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
    ),
    "camera": (
        "Camera",
        "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Camera",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    ),
}


def is_macos():
    return sys.platform == "darwin"


def is_packaged():
    return bool(getattr(sys, "frozen", False))


BUNDLE_ID = "com.hackclub.buddy"


def _app_bundle():
    if not is_packaged():
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def bundle_id():
    app = _app_bundle()
    if app is None:
        return BUNDLE_ID
    info = app / "Contents" / "Info.plist"
    if info.exists():
        try:
            raw = info.read_text(errors="ignore")
            marker = "<key>CFBundleIdentifier</key>"
            if marker in raw:
                after = raw.split(marker, 1)[1]
                start = after.find("<string>")
                end = after.find("</string>")
                if start != -1 and end != -1:
                    return after[start + 8:end].strip() or BUNDLE_ID
        except Exception:
            pass
    return BUNDLE_ID


def codesign_info():
    """Signed Buddy.app identity. Empty when running from source."""
    app = _app_bundle()
    if app is None:
        return {"signed": False, "authority": "", "identifier": bundle_id()}
    import subprocess
    result = subprocess.run(
        ["codesign", "-dv", "--verbose=2", str(app)],
        capture_output=True, text=True, check=False,
    )
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    authority = ""
    for line in text.splitlines():
        if line.startswith("Authority=") and "Developer ID" in line:
            authority = line.split("=", 1)[1].strip()
            break
        if line.startswith("Authority=") and not authority:
            authority = line.split("=", 1)[1].strip()
    return {
        "signed": "Signature=" in text or "Authority=" in text,
        "authority": authority,
        "identifier": bundle_id(),
        "path": str(app),
    }


def process_identity():
    """What macOS is likely to show in Privacy & Security for this process."""
    app = _app_bundle()
    if app is not None:
        return app.stem
    if is_packaged():
        return Path(sys.executable).resolve().stem or "Buddy"
    name = Path(sys.executable).name
    if name.lower().startswith("python"):
        return "Python (source run — not Buddy.app)"
    return name or "Buddy"


def identity_warning():
    if is_macos() and not is_packaged():
        return (
            "You are running Buddy from source. macOS may list %s, Terminal, "
            "or VS Code instead of Buddy. A signed Buddy.app is required "
            "before this row can say Granted for Buddy."
        ) % process_identity()
    return ""


def open_privacy_panel(key):
    """Open the exact System Settings destination. Returns True if a URL launched."""
    panel = PRIVACY_PANELS.get(key)
    if not panel or not is_macos():
        return False
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    _title, modern_url, legacy_url = panel
    if QDesktopServices.openUrl(QUrl(modern_url)):
        return True
    return bool(QDesktopServices.openUrl(QUrl(legacy_url)))


def probe_microphone():
    """True only if this process can open the default input device."""
    try:
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
    except Exception:
        return False
    try:
        device = QMediaDevices.defaultAudioInput()
        if device is None or device.isNull():
            return False
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        source = QAudioSource(device, fmt)
        io_device = source.start()
        ok = io_device is not None
        try:
            source.stop()
        except Exception:
            pass
        return bool(ok)
    except Exception:
        return False


def probe_camera():
    try:
        from PySide6.QtMultimedia import QMediaDevices
    except Exception:
        return False
    try:
        cameras = QMediaDevices.videoInputs()
        return bool(cameras)
    except Exception:
        return False


def probe_full_disk_access():
    """Harmless capability probe. True/False on macOS, None if inconclusive."""
    if not is_macos():
        return False
    candidates = [
        Path.home() / "Library" / "Mail",
        Path.home() / "Library" / "Safari",
        Path("/Library/Application Support/com.apple.TCC/TCC.db"),
    ]
    saw_protected = False
    for path in candidates:
        if not path.exists():
            continue
        saw_protected = True
        try:
            if path.is_dir():
                os.listdir(path)
            else:
                with open(path, "rb") as handle:
                    handle.read(1)
            return True
        except PermissionError:
            return False
        except OSError:
            return False
    return None if not saw_protected else False


def probe_folder_access():
    """True if this process can list the user's home directory."""
    try:
        os.listdir(str(Path.home()))
        return True
    except OSError:
        return False


def probe(key):
    if key == "microphone":
        return probe_microphone()
    if key == "camera":
        return probe_camera()
    if key == "full_disk_access":
        result = probe_full_disk_access()
        return bool(result)
    if key == "folder_access":
        return probe_folder_access()
    if key == "power_controls":
        return True
    return False


def status_label(key, buddy_enabled, os_granted):
    if not buddy_enabled:
        return "Off"
    if key == "power_controls":
        return "Granted"
    if not is_macos():
        return "Unavailable off macOS"
    if os_granted:
        return "Granted"
    return "Waiting for macOS approval"
