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
import requests

CURRENT_VERSION = "0.9.5"
GITHUB_OWNER = "shreyanshoffline"
GITHUB_REPO = "Buddy"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

        if _parse_version(latest_tag) > _parse_version(CURRENT_VERSION):
            result["available"] = True
            result["severity"] = _severity(CURRENT_VERSION, latest_tag)
    except Exception as e:
        result["notes"] = f"Couldn't check for updates: {e}"
    return result


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
        import subprocess as sp
        sp.run(["open", info["url"]])
        return (f"This build can't self-update yet — opened {info['url']} for you to "
                f"download the new version manually. Full self-update ships once "
                f"Buddy is signed and notarized.")


def severity_message(severity: str) -> str:
    """Text for the Settings banner, calibrated to how urgent it actually is."""
    if severity == "major":
        return ("This is a major update — it may include breaking changes or new "
                "required setup steps. Read the release notes before updating, "
                "and update soon rather than skip it.")
    if severity == "minor":
        return "New features and improvements are available. Update whenever's convenient."
    return "A small fix is available. Optional, low urgency."
