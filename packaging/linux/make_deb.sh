#!/usr/bin/env bash
# Build buddy_<ver>_<arch>.deb from build/bundle/Buddy.
# Works on Debian/Ubuntu and ChromeOS's Linux environment (double-click the .deb in the Files app).
#   packaging/linux/make_deb.sh <version> <amd64|arm64>
set -euo pipefail
VERSION="${1:?version}"; ARCH="${2:?amd64|arm64}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PKG="$ROOT/build/deb/buddy_${VERSION}_${ARCH}"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications"

cp -a "$ROOT/build/bundle/Buddy" "$PKG/opt/buddy"
install -m 0755 "$ROOT/packaging/linux/buddy-launcher.sh" "$PKG/usr/bin/buddy"
install -m 0644 "$ROOT/packaging/linux/buddy.desktop" "$PKG/usr/share/applications/buddy.desktop"
for size in 16 24 32 48 64 128 256 512; do
    dir="$PKG/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dir"
    install -m 0644 "$ROOT/build/icons/icons/${size}.png" "$dir/buddy.png"
done

find "$PKG" -type d -exec chmod 755 {} +
INSTALLED_KB=$(du -sk "$PKG/opt" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: buddy-assistant
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_KB}
Maintainer: Shrey Industries <noreply@github.com>
Homepage: https://github.com/shreyanshoffline/Buddy
Depends: libc6 (>= ${MIN_GLIBC:-2.35}), libgl1, libegl1, libfontconfig1, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libpulse0
Description: Buddy, your personal AI assistant
 Buddy chats, remembers, and works with your apps. Built by Shrey Industries
 for Hack Club.
CONTROL
cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
POST
chmod 0755 "$PKG/DEBIAN/postinst"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/Buddy-${VERSION}-linux-${ARCH}.deb"
echo "created dist/Buddy-${VERSION}-linux-${ARCH}.deb"
