"""Write portable SHA-256 sidecar files for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def checksum(path: Path) -> Path:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    output = path.with_suffix(path.suffix + ".sha256")
    output.write_text(f"{digest.hexdigest()}  {path.name}\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.artifacts:
        if not path.is_file():
            raise SystemExit(f"Release artifact not found: {path}")
        print(checksum(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
