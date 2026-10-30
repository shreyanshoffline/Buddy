#!/usr/bin/env bash
# One-minute check of the Linux packaging scripts using a stand-in app instead of the real
# 1-hour Nuitka build: builds the .deb and AppImage, installs/launches/removes the .deb,
# launches the AppImage. Runs in a temp copy, so it never touches build/ or dist/.
#   bash packaging/linux/dry_run.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"
mkdir -p "$T/packaging" "$T/build/bundle/Buddy"
cp -r "$SRC/packaging/linux" "$T/packaging/"
python3 "$SRC/packaging/make_icons.py" --out "$T/build/icons" >/dev/null
cat > "$T/build/bundle/Buddy/Buddy" <<'APP'
#!/bin/sh
out=""
for a in "$@"; do case "$a" in --smoke-out=*) out="${a#--smoke-out=}";; esac; done
[ -n "$out" ] && echo "SMOKE OK" > "$out"
APP
chmod +x "$T/build/bundle/Buddy/Buddy"

bash "$T/packaging/linux/make_deb.sh" 0.0.0 amd64
DEB="$T/dist/Buddy-0.0.0-linux-amd64.deb"
# Capture first, then grep. Never `dpkg-deb -c | grep -q`: grep -q quits at the first match, dpkg-deb's
# tar then gets a broken pipe, and `set -o pipefail` turns that into a false failure.
LISTING="$(dpkg-deb -c "$DEB")"
for want in "opt/buddy/Buddy" "usr/bin/buddy" "applications/buddy.desktop" "apps/buddy.png"; do
    grep -q "$want\$" <<<"$LISTING" || { echo "DRY RUN FAILED: $want missing from the .deb"; exit 1; }
done
INFO="$(dpkg-deb -I "$DEB")"
grep -q "Package: buddy-assistant" <<<"$INFO" || { echo "DRY RUN FAILED: wrong package name"; exit 1; }

bash "$T/packaging/linux/make_appimage.sh" 0.0.0 x86_64
IMG="$T/dist/Buddy-0.0.0-linux-x86_64.AppImage"
chmod +x "$IMG"
"$IMG" --appimage-extract-and-run --smoke-test --smoke-out="$T/ai.txt"
grep -q "SMOKE OK" "$T/ai.txt" || { echo "DRY RUN FAILED: AppImage did not launch"; exit 1; }
echo "DRY RUN OK"
