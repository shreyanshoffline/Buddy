# Shipping Buddy: step by step

GitHub builds everything. You do not need a Mac, a Windows PC and a Linux box.

## 1. Release
1. Make sure `.github/workflows/` contains only `ci.yml` and `release.yml` (delete any older release workflow: two of them will fight).
2. `version.py` says the version you want, e.g. `APP_VERSION = "0.9.8"`.
3. Commit, tag, push: `git add -A && git commit -m "Release 0.9.8" && git tag v0.9.8 && git push origin main --tags`
   (the tag MUST equal `v` + `version.py`, or the first job stops on purpose).
4. Actions > **Buddy release**. First run: 30-90 min (Nuitka compiles C). A tag run ends by publishing a GitHub Release.
5. To rehearse without publishing: Actions > Buddy release > **Run workflow**. Nothing is published; open the run, **Artifacts** (bottom) + the summary table list every final file and its size.

## 2. What you get (final installers only)
| Who | File | Install |
|---|---|---|
| Mac, Apple Silicon (M1 and later) | `Buddy-<ver>-macos-apple-silicon.dmg` | open, drag Buddy to Applications |
| Mac, Intel | `Buddy-<ver>-macos-intel.dmg` | same |
| Windows 10/11 64-bit | `Buddy-Setup-<ver>-x64.exe` | double-click; Start menu entry + uninstaller |
| Linux x86_64 | `Buddy-<ver>-linux-x86_64.AppImage` | `chmod +x`, double-click (no FUSE: add `--appimage-extract-and-run`) |
| Debian/Ubuntu/Mint, ChromeOS | `Buddy-<ver>-linux-amd64.deb` | double-click; ChromeOS: turn on Linux (Settings > Developers) first |

Also in the release: `Buddy-macos-<cpu>-<ver>.zip` is **only** for Buddy's in-app updater. Do not hand it to people. Each file has a `.sha256`.
Quick checks run on every push (`ci.yml` > packaging-checks): actionlint on the workflows, shellcheck on the scripts, and `packaging/linux/dry_run.sh`, which builds and launches a stand-in .deb and AppImage in about a minute, so mistakes surface before the 1.5-hour build.

Linux arm64 is not built: Nuitka's linker overflows on AArch64 for an app this size, and PySide6's arm64 wheels need glibc 2.39 anyway (so no ARM Chromebooks).

## 3. What CI proves before anything is published
- **Mac (each CPU):** builds `Buddy.app`, launches it, makes the DMG, then `verify_dmg.sh` mounts the DMG, checks the Applications shortcut and light-blue background files, **copies the app out like a user would**, checks version, bundle id, microphone text, icon, CPU architecture and code signature, and launches that copy.
- **Windows:** installs silently, checks `Buddy.exe`, the uninstaller and the Start menu shortcut, launches the installed app, uninstalls, checks it is gone.
- **Linux:** launches the finished AppImage; checks the `.deb` contents, installs it, launches the installed `buddy` command, removes it.
- **Final gate:** every expected file exists and is a real size, or nothing is published.
- Full unit tests run in `ci.yml` (Linux + Windows). Release jobs skip them on purpose; every job still runs the app's own `--smoke-test`, which writes its result to a file (the Windows app has no console).
- All smoke tests use a temporary data folder and never touch real Buddy data or the Keychain.

## 4. First launch (tell your users)
No paid certificates = the OS warns once:
- **macOS 15 (Sequoia) and newer:** open Buddy, click Done, then **System Settings > Privacy & Security > scroll down > Open Anyway**. (The old right-click > Open trick no longer works on Sequoia.) Or in Terminal: `xattr -dr com.apple.quarantine /Applications/Buddy.app`.
- **macOS 13-14:** right-click Buddy > Open > Open.
- **Windows:** SmartScreen > More info > Run anyway.
Removing these warnings needs an Apple Developer ID ($99/yr) and a Windows code-signing certificate. With the Apple secrets (`MACOS_CERT_P12_BASE64`, `MACOS_CERT_PASSWORD`, `MACOS_SIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD`) the workflow signs and notarizes the DMGs automatically.

## 5. Limits
- macOS 13+ (Qt 6). Windows 10/11 x64 (Windows on ARM runs it through built-in emulation). Linux needs glibc 2.35+ (Ubuntu 22.04+, Debian 12+ incl. ChromeOS).
- Mac-only tools (iMessage, Notes, Calendar) do not exist on Windows/Linux/ChromeOS.
- A universal (Intel+ARM in one) DMG is NOT part of the pipeline. `packaging/macos/merge_universal.py` still exists if you ever want it, but nothing depends on it.

## 6. Local build (optional)
```bash
python3.12 -m venv .venv-build && . .venv-build/bin/activate   # must be 3.12, clean (no PyQt)
pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/build_nuitka.py --skip-tests --smoke-test      # -> build/bundle/
python packaging/macos/make_dmg.py --app build/bundle/Buddy.app --icon build/icons/Buddy.icns --out dist/Buddy.dmg
```
Windows: `iscc /DAppVersion=0.9.8 packaging\windows\Buddy.iss` - Linux: `packaging/linux/make_deb.sh 0.9.8 amd64` and `make_appimage.sh 0.9.8 x86_64`.

## 7. Files
`build_nuitka.py` build + smoke test - `make_icons.py` icons - `macos/` DMG art, builder, verifier (+ optional universal merge) - `windows/Buddy.iss` installer - `linux/` AppImage, .deb, launcher, .desktop - `Info.plist`, `Buddy.entitlements` - `../.github/workflows/` the pipeline.
