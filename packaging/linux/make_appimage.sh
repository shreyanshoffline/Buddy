#!/usr/bin/env bash
# Build Buddy-<ver>-<arch>.AppImage (one file; chmod +x and run) from build/bundle/Buddy.
#   packaging/linux/make_appimage.sh <version> <x86_64|aarch64>
set -euo pipefail
VERSION="${1:?version}"; ARCH="${2:?x86_64|aarch64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/Buddy.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$ROOT/build/bundle/Buddy" "$APPDIR/usr/lib/buddy"
cp "$ROOT/packaging/linux/buddy.desktop" "$APPDIR/buddy.desktop"
cp "$ROOT/packaging/linux/buddy.desktop" "$APPDIR/usr/share/applications/buddy.desktop"
cp "$ROOT/build/icons/icons/256.png" "$APPDIR/buddy.png"
ln -sf buddy.png "$APPDIR/.DirIcon"
cp "$ROOT/build/icons/icons/256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/buddy.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
if [ -z "$QT_QPA_PLATFORM" ] && { [ -e /dev/.cros_milestone ] || [ -d /opt/google/cros-containers ]; }; then
    export QT_QPA_PLATFORM=xcb
fi
exec "$HERE/usr/lib/buddy/Buddy" "$@"
RUN
chmod +x "$APPDIR/AppRun"

TOOL="$ROOT/build/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
mkdir -p "$ROOT/dist"
# --appimage-extract-and-run: CI runners have no FUSE
export ARCH
"$TOOL" --appimage-extract-and-run "$APPDIR" "$ROOT/dist/Buddy-${VERSION}-linux-${ARCH}.AppImage"
echo "created dist/Buddy-${VERSION}-linux-${ARCH}.AppImage"
