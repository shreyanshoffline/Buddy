"""Install a downloaded Buddy ZIP after the running process exits."""

import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m tools.install_update UPDATE.zip")
    archive = Path(sys.argv[1]).expanduser().resolve()
    app_path = Path(sys.executable).resolve()
    if ".app" in app_path.parts:
        app_path = next(path for path in app_path.parents if path.suffix == ".app")
    else:
        print("Update downloaded to %s; install it manually." % archive)
        return 0

    staging = Path(tempfile.mkdtemp(prefix="buddy-update-"))
    try:
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(staging)
        candidates = list(staging.rglob("*.app"))
        if not candidates:
            raise RuntimeError("release ZIP does not contain a .app bundle")
        replacement = candidates[0]
        backup = app_path.with_name(app_path.name + ".old")
        time.sleep(2)
        if backup.exists():
            shutil.rmtree(backup)
        app_path.rename(backup)
        shutil.copytree(replacement, app_path)
        shutil.rmtree(backup)
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
        return 0
    except Exception as exc:
        print("Buddy update failed: %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())