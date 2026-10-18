# Signing and notarization

## Free GitHub release flow

Buddy uses public GitHub Releases, so publishing does not require a paid
update server. From the repository root:

```bash
python3 -m tools.release_manager check
python3 -m tools.release_manager publish --notes "Describe this release"
```

The publish command requires the free GitHub CLI (`gh`) authenticated to the
Buddy repository. GitHub Actions builds macOS, Windows, and Linux Nuitka
standalone ZIPs and
attaches them to the release. ChromeOS uses the Linux build inside its Linux
environment. Buddy checks the latest release after startup and when Settings
opens.

Buddy stores its database outside the app bundle, so replacing the application
does not erase chats, memories, or preferences:

- macOS: `~/Library/Application Support/Buddy/`
- Windows: `%APPDATA%/Buddy/`
- Linux/ChromeOS: `$XDG_DATA_HOME/Buddy/` or `~/.local/share/Buddy/`

Build the portable bundles with Nuitka:

```bash
python -m pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/build_nuitka.py
```

The supported release path is Nuitka `--standalone` plus the PySide6 plugin.
Nuitka `--onefile` is intentionally not used: standalone folders start faster
and can be updated by replacing the folder. The PyInstaller scripts remain
available as a fallback.

### Publishing from GitHub

1. Update `APP_VERSION` in `version.py`.
2. Commit and push the change.
3. Run **Actions → Buddy release → Run workflow** to build all targets without
   publishing a release.
4. When ready, push a matching tag, for example:

   ```bash
   git tag v0.9.8
   git push origin v0.9.8
   ```

5. GitHub creates the release and attaches the three ZIPs and their SHA-256
   files. Extract the entire ZIP on the target computer; standalone builds are
   folders, not single files.

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
