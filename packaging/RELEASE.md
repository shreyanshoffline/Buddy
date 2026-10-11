# Signing and notarization

## Free GitHub release flow

Buddy uses public GitHub Releases, so publishing does not require a paid
update server. From the repository root:

```bash
python3 -m tools.release_manager check
python3 -m tools.release_manager publish --notes "Describe this release"
```

The publish command requires the free GitHub CLI (`gh`) authenticated to the
Buddy repository. GitHub Actions builds `Buddy-macOS.zip` and attaches it to
the release. Buddy checks the latest release after startup and when Settings
opens.

Buddy stores its database in `~/Library/Application Support/Buddy/buddy.db`,
outside the app bundle, so replacing the application does not erase chats,
memories, or preferences.

Apple signing and notarization remain optional for this zero-cost flow. An
unsigned macOS build may show a Gatekeeper warning on first launch.

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
