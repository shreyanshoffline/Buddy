"""Free GitHub Releases helper for Buddy maintainers.

Requires only Git and the GitHub CLI (`gh`) for publishing. Public GitHub
repositories and their Actions minutes are free.
"""

import argparse
import subprocess
from pathlib import Path

from version import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent


def run(command):
    return subprocess.run(command, cwd=ROOT, check=True, text=True)


def check():
    required = [ROOT / "version.py", ROOT / "packaging" / "Info.plist", ROOT / "tools" / "release_doctor.py"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing release files: " + ", ".join(missing))
    run(["python3", "tools/release_doctor.py"])
    print("Release checks passed for Buddy %s" % APP_VERSION)


def publish(notes):
    check()
    tag = "v" + APP_VERSION
    run(["git", "diff", "--exit-code"])
    run(["git", "tag", "-a", tag, "-m", "Buddy %s" % APP_VERSION])
    run(["git", "push", "origin", tag])
    command = ["gh", "release", "create", tag, "--title", "Buddy %s" % APP_VERSION]
    if notes:
        command.extend(["--notes", notes])
    else:
        command.append("--generate-notes")
    run(command)


parser = argparse.ArgumentParser(description="Publish Buddy through free GitHub Releases.")
parser.add_argument("command", choices=["check", "publish"])
parser.add_argument("--notes", default="")
args = parser.parse_args()

if args.command == "check":
    check()
else:
    publish(args.notes)