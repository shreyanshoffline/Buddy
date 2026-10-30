#!/usr/bin/env bash
# Verify a finished DMG the way a user experiences it: mount it, check the layout, copy the app out
# (like dragging to Applications), then validate and LAUNCH that copy.
#   packaging/macos/verify_dmg.sh dist/Buddy-0.9.8-macos-intel.dmg x86_64 0.9.8
set -euo pipefail
DMG="${1:?dmg}"; ARCH="${2:?arm64|x86_64}"; VERSION="${3:?version}"
fail() { echo "VERIFY FAILED: $*" >&2; exit 1; }
[ -f "$DMG" ] || fail "$DMG does not exist"

WORK="$(mktemp -d)"; MNT="$WORK/mnt"; mkdir -p "$MNT"
hdiutil attach "$DMG" -mountpoint "$MNT" -nobrowse -readonly -noautoopen >/dev/null
trap 'hdiutil detach "$MNT" -force >/dev/null 2>&1 || true' EXIT

echo "== DMG layout"; ls -la "$MNT"
[ -d "$MNT/Buddy.app" ] || fail "Buddy.app is not in the DMG (is it just a folder or zip?)"
[ -L "$MNT/Applications" ] && [ "$(readlink "$MNT/Applications")" = "/Applications" ] || fail "Applications shortcut missing"
[ -d "$MNT/.background" ] || fail "custom light-blue background folder is missing"
[ -f "$MNT/.DS_Store" ] || fail "Finder window layout (.DS_Store) is missing"
ls "$MNT"/.background/dmg_background.* >/dev/null 2>&1 || fail "custom background image is missing (found: $(ls "$MNT/.background"))"
echo "custom background + window layout present: $(ls "$MNT/.background")"

echo "== copy out like drag-to-Applications"
APP="$WORK/Applications/Buddy.app"; mkdir -p "$WORK/Applications"
ditto "$MNT/Buddy.app" "$APP"

echo "== Info.plist"
PB=/usr/libexec/PlistBuddy; PL="$APP/Contents/Info.plist"
[ "$($PB -c 'Print :CFBundleShortVersionString' "$PL")" = "$VERSION" ] || fail "bundle version != $VERSION"
[ "$($PB -c 'Print :CFBundleIdentifier' "$PL")" = "com.hackclub.buddy" ] || fail "bundle id wrong"
$PB -c 'Print :NSMicrophoneUsageDescription' "$PL" >/dev/null || fail "microphone permission text missing"
ICON="$($PB -c 'Print :CFBundleIconFile' "$PL")" || fail "no CFBundleIconFile"
[ -f "$APP/Contents/Resources/$ICON" ] || [ -f "$APP/Contents/Resources/$ICON.icns" ] || fail "icon file $ICON missing"

echo "== architecture"
ARCHS="$(lipo -archs "$APP/Contents/MacOS/Buddy")"; echo "$ARCHS"
[ "$ARCHS" = "$ARCH" ] || fail "expected $ARCH, got $ARCHS"

echo "== signature"
codesign --verify --deep --strict "$APP" || fail "code signature invalid after copying out of the DMG"

echo "== launch the copied app"
export BUDDY_DATA_DIR="$WORK/data" BUDDY_SMOKE_TEST=1 QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
"$APP/Contents/MacOS/Buddy" --smoke-test --smoke-out="$WORK/smoke.txt" || true
cat "$WORK/smoke.txt" 2>/dev/null || true
grep -q "SMOKE OK" "$WORK/smoke.txt" 2>/dev/null || fail "installed app did not start"
echo "VERIFY OK: $DMG"
