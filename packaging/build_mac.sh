#!/bin/bash
# Build Buddy.app + Buddy-macOS.zip (+ .sha256). Run from the repo root on a Mac:
#   bash packaging/build_mac.sh
# Optional env for a Developer ID build: SIGN_IDENTITY="Developer ID Application: NAME (TEAMID)"
#   and NOTARY_PROFILE=buddy-notary (xcrun notarytool store-credentials). Without them the app is
#   ad-hoc signed (runs on Apple Silicon; users right-click > Open the first time).
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "from version import APP_VERSION; print(APP_VERSION)")
echo "==> Building Buddy $VERSION"

python3 -m pip install -q -r requirements.txt pyinstaller google-api-python-client google-auth-oauthlib playwright
python3 -m pytest -q tests

rm -rf build dist Buddy.spec
python3 -m PyInstaller --noconfirm --windowed --name Buddy \
  --osx-bundle-identifier com.hackclub.buddy \
  --add-data "knowledge:knowledge" --add-data "gui/assets:gui/assets" \
  --collect-all googleapiclient --collect-all google_auth_oauthlib \
  --collect-all msal --collect-all playwright \
  main.py

# Merge our permission strings + version into the generated Info.plist
python3 - <<PY
import plistlib
gen = "dist/Buddy.app/Contents/Info.plist"
mine = plistlib.load(open("packaging/Info.plist", "rb"))
info = plistlib.load(open(gen, "rb"))
info.update({k: v for k, v in mine.items() if k not in ("CFBundleExecutable",)})
info["CFBundleVersion"] = info["CFBundleShortVersionString"] = "$VERSION"
plistlib.dump(info, open(gen, "wb"))
PY

IDENTITY="${SIGN_IDENTITY:--}"
OPTS=(--force --deep --entitlements packaging/Buddy.entitlements --sign "$IDENTITY")
[ "$IDENTITY" != "-" ] && OPTS+=(--options runtime)
codesign "${OPTS[@]}" dist/Buddy.app
codesign --verify --deep --strict dist/Buddy.app && echo "==> signature OK"

ditto -c -k --sequesterRsrc --keepParent dist/Buddy.app dist/Buddy-macOS.zip
if [ "$IDENTITY" != "-" ] && [ -n "${NOTARY_PROFILE:-}" ]; then
  xcrun notarytool submit dist/Buddy-macOS.zip --wait --keychain-profile "$NOTARY_PROFILE"
  xcrun stapler staple dist/Buddy.app
  ditto -c -k --sequesterRsrc --keepParent dist/Buddy.app dist/Buddy-macOS.zip
fi
(cd dist && shasum -a 256 Buddy-macOS.zip > Buddy-macOS.zip.sha256)
python3 tools/release_doctor.py dist/Buddy.app || true
echo "==> Done: dist/Buddy-macOS.zip"
