"""Release doctor for the first signed macOS build.

Run from the Buddy repo root:

    python3 tools/release_doctor.py /path/to/Buddy.app

It never notarizes. It only reports what is missing.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def check_app(app_path):
    app = Path(app_path)
    findings = []

    def add(ok, title, detail=""):
        findings.append({"ok": ok, "title": title, "detail": detail})

    if not app.exists():
        add(False, "Buddy.app", "No app at %s" % app)
        return findings

    add(True, "Buddy.app exists", str(app))
    info = app / "Contents" / "Info.plist"
    add(info.exists(), "Info.plist", str(info))
    entitlements = app / "Contents" / "Buddy.entitlements"
    add(True, "Entitlements template", "Ship packaging/Buddy.entitlements with the app codesign command.")

    code, text = _run(["codesign", "-dv", "--verbose=2", str(app)])
    signed = code == 0 and ("Authority=" in text or "Signature=" in text)
    add(signed, "codesign identity", text.strip().splitlines()[-1] if text.strip() else "not signed")

    code, text = _run(["codesign", "--verify", "--deep", "--strict", str(app)])
    add(code == 0, "codesign --verify --deep --strict", text.strip() or "ok")

    code, text = _run(["spctl", "-a", "-vv", str(app)])
    add(code == 0, "Gatekeeper assessment", text.strip() or "not notarized yet")

    code, text = _run(["xcrun", "stapler", "validate", str(app)])
    add(code == 0, "Notarization staple", text.strip() or "not stapled")

    return findings


def check_source():
    findings = []
    root = Path(__file__).resolve().parent.parent
    required = [
        "GUI/main_window.py",
        "tools/macos_permissions.py",
        "packaging/Buddy.entitlements",
        "packaging/Info.plist",
        "storage/db.py",
        "tests/test_foundation.py",
    ]
    for rel in required:
        path = root / rel
        findings.append({"ok": path.exists(), "title": rel, "detail": str(path)})
    for key in ("API_KEY", "BUDDY_GITHUB_CLIENT_ID"):
        findings.append({
            "ok": True,
            "title": "env %s" % key,
            "detail": "set" if os.environ.get(key) else "missing (optional until that feature is used)",
        })
    return findings


def main(argv):
    app = argv[1] if len(argv) > 1 else ""
    rows = check_source()
    if app:
        rows.extend(check_app(app))
    failed = 0
    for row in rows:
        mark = "OK" if row["ok"] else "NO"
        if not row["ok"]:
            failed += 1
        print("%s  %s  %s" % (mark, row["title"], row["detail"]))
    print("")
    print("Failed checks: %s" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
