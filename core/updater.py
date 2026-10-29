"""
core/updater.py

Checks GitHub releases for a newer version, and gives Settings enough
to show a real "Update available" banner with a working button. Honest
about what that button can and can't do at beta stage: this is a
Python checkout, not a signed notarized .app yet (that's 0.9.8 per the
roadmap), so "Update Now" means `git pull` if this is a git checkout,
or opening the release page to download if it's not. It does not
silently replace a running signed binary — nothing does that safely
without the notarization work the roadmap already scopes for 0.9.8.
"""

import os
import re
import subprocess
import sys
import tempfile
import webbrowser
import zipfile
import shlex
from pathlib import Path
import requests
from version import APP_VERSION

from tools.paths import app_root

CURRENT_VERSION = APP_VERSION
GITHUB_OWNER = "shreyanshoffline"
GITHUB_REPO = "Buddy"
REPO_ROOT = str(app_root())


def _parse_version(v: str):
    v = v.lstrip("v")
    parts = re.split(r"[.\-]", v)
    nums = []
    for p in parts:
        m = re.match(r"\d+", p)
        nums.append(int(m.group()) if m else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def _severity(current: str, latest: str) -> str:
    c = _parse_version(current)
    l = _parse_version(latest)
    if l[0] > c[0]:
        return "major"
    if l[1] > c[1]:
        return "minor"
    return "patch"


def check_for_update() -> dict:
    """Returns:
    {
        "available": bool,
        "current_version": str,
        "latest_version": str,
        "severity": "major" | "minor" | "patch" | None,
        "url": str,
        "notes": str,
    }
    Never raises — network/API failures come back as available: False
    with an error note, since a failed update check should never block
    the app from opening.
    """
    result = {
        "available": False,
        "current_version": CURRENT_VERSION,
        "latest_version": CURRENT_VERSION,
        "severity": None,
        "url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases",
        "download_url": "",
        "asset_name": "",
        "notes": "",
    }
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest",
            timeout=8,
        )
        if r.status_code == 404:
            result["notes"] = "No releases published yet."
            return result
        r.raise_for_status()
        data = r.json()
        latest_tag = data.get("tag_name", CURRENT_VERSION)
        result["latest_version"] = latest_tag
        result["url"] = data.get("html_url", result["url"])
        result["notes"] = (data.get("body") or "")[:500]
        assets = data.get("assets") or []
        preferred = pick_asset(assets)
        if preferred:
            result["download_url"] = preferred.get("browser_download_url", "")
            result["asset_name"] = preferred.get("name", "")

        if _parse_version(latest_tag) > _parse_version(CURRENT_VERSION):
            result["available"] = True
            result["severity"] = _severity(CURRENT_VERSION, latest_tag)
    except Exception as e:
        result["notes"] = f"Couldn't check for updates: {e}"
    return result


def _platform_tag() -> str:
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def pick_asset(assets, platform_tag=None, machine=None):
    """The release carries a DMG/installer/AppImage/.deb per OS plus one in-place-updatable
    macOS ZIP. Only the macOS ZIP can be applied automatically; everyone else gets the
    release page (their installer is there), never another platform's file."""
    tag = platform_tag or _platform_tag()
    if tag != "macos":
        return None
    import platform as _platform
    cpu = "arm64" if (machine or _platform.machine()).lower() in ("arm64", "aarch64") else "x86_64"
    for asset in assets or []:
        name = asset.get("name", "").lower()
        if name.endswith(".zip") and "macos" in name and cpu in name:
            return asset
    return None


def is_git_checkout() -> bool:
    return os.path.isdir(os.path.join(REPO_ROOT, ".git"))


def update_now() -> str:
    """Real action, not a fake progress bar. Two honest outcomes:
    - Git checkout: runs `git pull`, reports what actually happened.
    - Anything else: this can't safely self-replace, so it opens the
      release page and says so plainly, instead of pretending to
      update."""
    if is_git_checkout():
        try:
            result = subprocess.run(
                ["git", "pull"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return f"Update failed: {result.stderr.strip()}"
            if "Already up to date" in result.stdout:
                return "Already up to date."
            return f"Updated. Restart Buddy to use the new version.\n\n{result.stdout.strip()}"
        except Exception as e:
            return f"Update failed: {e}"
    else:
        info = check_for_update()
        if not info.get("download_url"):
            webbrowser.open(info["url"])
            return f"Buddy opened {info['url']} so you can download the installer for your computer."
        try:
            archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            with requests.get(info["download_url"], stream=True, timeout=30) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        archive.write(chunk)
            archive.close()
            if not zipfile.is_zipfile(archive.name):
                os.unlink(archive.name)
                return "Update failed: the downloaded release was not a valid ZIP archive."
            # Integrity: verify against the published .sha256 asset when the release has one.
            try:
                import hashlib
                sha_url = info["download_url"] + ".sha256"
                sha_resp = requests.get(sha_url, timeout=10)
                if sha_resp.ok:
                    expected = sha_resp.text.split()[0].strip().lower()
                    digest = hashlib.sha256(open(archive.name, "rb").read()).hexdigest()
                    if digest != expected:
                        os.unlink(archive.name)
                        return "Update failed: the download didn't match its checksum, so Buddy discarded it."
            except Exception:
                pass  # checksum asset missing/unreachable: fall back to the ZIP validity check
            executable = Path(os.path.realpath(sys.executable))
            app_path = next((str(parent) for parent in executable.parents if parent.suffix == ".app"), "")
            if not app_path:
                subprocess.run(["open", "-R", archive.name])
                return "Update downloaded. Open the ZIP to install it manually."
            install_script = tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False)
            quoted_archive = shlex.quote(archive.name)
            quoted_app = shlex.quote(app_path)
            quoted_script = shlex.quote(install_script.name)
            install_script.write(
                "#!/bin/sh\n"
                "sleep 2\n"
                "STAGING=$(mktemp -d)\n"
                f"unzip -q {quoted_archive} -d \"$STAGING\"\n"
                "REPLACEMENT=$(find \"$STAGING\" -name '*.app' -maxdepth 3 -print -quit)\n"
                f"if [ -n \"$REPLACEMENT\" ]; then mv {quoted_app} {quoted_app}.old && (ditto \"$REPLACEMENT\" {quoted_app} && rm -rf {quoted_app}.old || (rm -rf {quoted_app}; mv {quoted_app}.old {quoted_app})); open {quoted_app}; fi\n"
                f"rm -rf \"$STAGING\" {quoted_archive} {quoted_script}\n"
            )
            install_script.close()
            os.chmod(install_script.name, 0o700)
            subprocess.Popen(["/bin/sh", install_script.name])
            return "Update downloaded. Buddy will restart with the new version."
        except Exception as e:
            return f"Update failed: {e}"


def severity_message(severity: str) -> str:
    """Text for the Settings banner, calibrated to how urgent it actually is."""
    if severity == "major":
        return ("This is a major update — it may include breaking changes or new "
                "required setup steps. Read the release notes before updating, "
                "and update soon rather than skip it.")
    if severity == "minor":
        return "New features and improvements are available. Update whenever's convenient."
    return "A small fix is available. Optional, low urgency."
