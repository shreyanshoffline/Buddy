# Signing and notarization

These commands run on a Mac with a Developer ID Application certificate.

```bash
codesign --deep --force --options runtime \
  --entitlements packaging/Buddy.entitlements \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" \
  dist/Buddy.app

xcrun notarytool submit dist/Buddy.zip --wait --keychain-profile buddy-notary
xcrun stapler staple dist/Buddy.app
python3 tools/release_doctor.py dist/Buddy.app
```

Privacy & Security should then list `Buddy` (`com.hackclub.buddy`), not Python or Terminal.
