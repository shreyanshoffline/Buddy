"""
core/paths.py

One place that answers "where does Buddy's data actually live" — used
by every module that needs to read/write a file, instead of each one
guessing its own fixed ~/Buddy or ~/.buddy path.

Why this matters: a hardcoded ~/Buddy/token.json breaks the moment
someone runs Buddy from a different folder (Desktop, a Photos folder,
wherever), or once it's a compiled .app someone else installs
somewhere Buddy's original author never chose. Resolving paths
relative to where the actual running code lives means it works no
matter where the folder sits.
"""

import sys
import os
from pathlib import Path


def app_root() -> Path:
    """The real folder Buddy's code is running from right now.

    Handles three cases:
    - Normal `python main.py` run: walks up from this file to the
      project root (core/paths.py -> core/ -> project root).
    - PyInstaller-style frozen build: sys.frozen is set, use the
      executable's own folder.
    - Nuitka standalone build: no sys.frozen, but the running module's
      __file__ still resolves to a real path inside the distributed
      app folder (not a temp extraction, as long as it's built
      --standalone rather than --onefile) — same walk-up logic works.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir(subfolder: str = "data") -> Path:
    """A writable folder inside Buddy's own directory tree — created if
    it doesn't exist yet. This is where anything Buddy generates for
    itself (tokens, local databases, caches) should live, so the whole
    app stays self-contained and movable as one folder."""
    d = app_root() / subfolder
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_file(name: str, subfolder: str = "data") -> str:
    """Full path to a specific file inside the app's own data folder."""
    return str(data_dir(subfolder) / name)


def resolve_existing(name: str, extra_candidates=None) -> str:
    """For files a user might have manually dropped somewhere reasonable
    (like credentials.json) — checks the most likely real locations and
    returns whichever one actually exists, falling back to the app's own
    data folder as the default write location if none do yet. Mirrors
    the search tools.py's _gmail_file already used, generalized so
    every module shares one implementation instead of duplicating it."""
    root = app_root()
    candidates = [
        root / "tools" / name,
        root / name,
        root / "data" / name,
        Path.cwd() / "tools" / name,
        Path.cwd() / name,
    ]
    if extra_candidates:
        candidates = list(extra_candidates) + candidates
    for path in candidates:
        if path.exists():
            return str(path)
    return data_file(name)
