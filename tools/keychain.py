"""Store provider tokens in macOS Keychain when possible.

SQLite only keeps account labels. Secrets never belong in buddy.db.
On non-macOS or when `security` fails, tokens stay in a 0600 sidecar
file next to the database — still not in the chat database.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tools.paths import data_file


SERVICE_PREFIX = "com.hackclub.buddy"


def _sidecar_path():
    configured = os.environ.get("BUDDY_DB_PATH")
    if configured:
        return Path(configured).expanduser().with_name("buddy.secrets.json")
    return Path(data_file("buddy.secrets.json", subfolder=""))


def _use_keychain():
    return sys.platform == "darwin"


def _security(*args, input_text=None):
    result = subprocess.run(
        ["security"] + list(args),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def set_secret(name, secret):
    if not secret:
        delete_secret(name)
        return "cleared"
    if _use_keychain():
        _security("delete-generic-password", "-s", "%s.%s" % (SERVICE_PREFIX, name), "-a", "buddy")
        result = _security(
            "add-generic-password",
            "-s", "%s.%s" % (SERVICE_PREFIX, name),
            "-a", "buddy",
            "-w", secret,
            "-U",
        )
        if result.returncode == 0:
            return "keychain"
    path = _sidecar_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
    data[name] = secret
    path.write_text(json.dumps(data))
    os.chmod(path, 0o600)
    return "sidecar"


def get_secret(name):
    if _use_keychain():
        result = _security(
            "find-generic-password",
            "-s", "%s.%s" % (SERVICE_PREFIX, name),
            "-a", "buddy",
            "-w",
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    path = _sidecar_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    return data.get(name)


def delete_secret(name):
    if _use_keychain():
        _security("delete-generic-password", "-s", "%s.%s" % (SERVICE_PREFIX, name), "-a", "buddy")
    path = _sidecar_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
        data.pop(name, None)
        path.write_text(json.dumps(data))
        os.chmod(path, 0o600)
