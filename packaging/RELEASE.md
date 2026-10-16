# Signing and notarization

## Free GitHub release flow

Buddy uses public GitHub Releases, so publishing does not require a paid
update server. From the repository root:

```bash
python3 -m tools.release_manager check
python3 -m tools.release_manager publish --notes "Describe this release"
```

The publish command requires the free GitHub CLI (`gh`) authenticated to the
Buddy repository. GitHub Actions builds macOS, Windows, and Linux ZIPs and
attaches them to the release. ChromeOS uses the Linux build inside its Linux
environment. Buddy checks the latest release after startup and when Settings
opens.

Buddy stores its database outside the app bundle, so replacing the application
does not erase chats, memories, or preferences:

- macOS: `~/Library/Application Support/Buddy/`
- Windows: `%APPDATA%/Buddy/`
- Linux/ChromeOS: `$XDG_DATA_HOME/Buddy/` or `~/.local/share/Buddy/`

Build the portable non-macOS bundles with:

```bash
python -m pip install -r requirements.txt pyinstaller pytest
python packaging/build.py
```

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
