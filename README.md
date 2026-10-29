# Buddy

Buddy is a local-first desktop AI assistant for macOS, Windows, Linux, and ChromeOS's Linux environment. It combines chat, voice conversation, computer tools, integrations, local memory, and a lightweight floating desktop interface.

Buddy is designed to be useful without hiding what happened. When a tool works, Buddy reports the result. When a provider, permission, or network request fails, Buddy shows the actual error and the next action instead of silently improvising.

<p align="center">
  <img src="gui/assets/Buddy_Logo_Beta.png" alt="Buddy logo" width="140">
</p>

## Screenshots

<!-- Add the images to docs/images/ using the filenames listed in docs/images/README.md -->

| | |
| --- | --- |
| ![Chat with suggestion chips](docs/images/chat.png) | ![Live work log](docs/images/work-log.png) |
| **Chat** — greeting, suggestions, history | **Work log** — every plan step, tool call, and timing |
| ![Memory tab](docs/images/memory.png) | ![Plugins page](docs/images/plugins.png) |
| **Memory** — five categories you control | **Plugins** — connections and permissions |
| ![Talk page](docs/images/talk.png) | ![Coding mode](docs/images/coding-mode.png) |
| **Talk** — voice conversation | **Coding mode** — builds and tests software |

## Current State

Buddy is an active cross-platform beta at version `0.9.8`.

Implemented and tested:

- Local PySide6 desktop interface with chat, sidebar navigation, Library, Memory, Plugins, Talk, Pricing, and Settings.
- SQLite persistence for conversations, messages, memories, profile settings, plugin settings, and voice chats.
- Automatic database migrations and recovery for older or damaged databases.
- User data stored outside the app bundle in the operating system's application-data directory.
- Manager/worker agent pipeline with model routing, plans, tool execution, cancellation, timeouts, action receipts, and transparent failures.
- Confirmed user location for nearby searches without guessing from IP geolocation.
- Concise voice-mode replies when Buddy is speaking aloud.
- Free macOS system speech with Siri-like Apple voice preference and Premium/Enhanced fallback.
- GitHub Releases update checks, Settings update controls, startup update hints, and memory-preserving app replacement.
- Free GitHub Actions release packaging.
- One entry point: `python3 main.py` starts the desktop app and its local backend together.
- Portable Windows and Linux builds from the same source tree, plus the macOS signed-build path.
- Conditional plan continuation: workers can add verified follow-up steps when new tool results change the work.

The offline suite covers the shared core. Packaged-app permissions, live provider accounts, and notarized distribution still require real release testing on each target OS.

### Platform support

The shared app, chat pipeline, browser tools, files, web actions, provider clients, memory, updates, and attachments use the same code on every desktop build.

| Platform | Build | Native capabilities |
| --- | --- | --- |
| macOS 13+ | Universal `.dmg` and `.zip` from GitHub Releases | Full Apple app automation and macOS permissions |
| Windows 10+ | x64 `.exe` installer from GitHub Releases | Desktop, browser, files, web, Microsoft, Google, Slack, and GitHub workflows |
| Linux | x86_64 `.AppImage` or `.deb` from GitHub Releases | Desktop, browser, files, web, Microsoft, Google, Slack, and GitHub workflows |
| ChromeOS | Install the x86_64 Linux `.deb` in the Linux environment | Same Linux capabilities on supported x86_64 Chromebooks |

Apple-only tools are disabled with a clear explanation on other systems. Buddy does not pretend that AppleScript features exist on Windows or Linux.

## What Buddy Can Do

Not sure what to ask? Say **"What can you do?"** and Buddy answers from its built-in capability guide (`knowledge/capabilities.md`) with examples tailored to you. A few to start with:

- "What's unread from my professor, and draft a reply asking for an extension."
- "Organize my Downloads folder by file type."
- "Build me a Snake game in Python." (coding mode)
- "Remember that my sister's birthday is June 3."
- "Start my school setup." (opens your usual apps and sites)

## Features

### Chat

- Regular conversations with saved history.
- Incognito conversations that do not become permanent chat history.
- Conversation titles, search, favorites, archive state, private chats, and message feedback.
- Attachments with text extraction and searchable chunks.
- Image understanding and image generation where the configured model supports it.
- Model and thinking-level controls.
- Retry and redo flows.
- Live work logs while Buddy is working, plus the complete selectable plan, tool details, results, and timings after the reply finishes.

### Voice Conversation

Talk to Buddy through the Talk page.

- Microphone recording with speech detection.
- Speech-to-text transcription.
- Short voice-aware replies, normally one to three sentences.
- macOS system speech at no additional cost.
- Prefers installed Apple conversational voices such as Samantha, Allison, or Ava.
- Falls back to installed Premium or Enhanced voices.
- Interrupt, pause, resume, stop speaking, end chat, and delete chat controls.
- Voice conversations are saved to Library unless deleted.

The current voice pipeline is record, transcribe, generate, and speak. Fully streaming speech is a future improvement.

### Computer Tools

With the relevant plugin enabled, Buddy can work with common desktop actions on every supported OS:

- Applications: open, close, activate, list, and force-quit with confirmation where the OS supports it.
- Files and file managers: list, read, write, append, create, copy, move, rename, trash, delete, search, and reveal.
- Browser workflows through the configured browser tools.
- Clipboard, screenshots, notifications, volume, dark mode, system information, battery, disk, memory, and processes.
- Apple apps including Calendar, Reminders, Notes, Messages, Mail, Music, Safari, Photos, Finder, and Shortcuts on macOS.
- Terminal and code execution when explicitly enabled, with confirmation for dangerous commands.

Destructive operations remain protected by confirmation dialogs. This is intentional: “do everything” does not mean silently delete data or change the system without approval.

### Coding Mode

Ask Buddy to build, fix, or upgrade software. It plans with a cheap model, writes files with the strong model only where real code is needed, runs and tests the project, fixes failures on its own, and can undo its changes. It needs **Files & Folders** and **Terminal** enabled in Plugins.

### Routine Suggestions

Opt in under Settings (off by default) and Buddy records app names, website hostnames, and times only. Once a routine repeats on three or more days, it offers one-click suggestions on a new chat. Password managers, banking, health, and login sites are skipped, and "Forget my activity data" wipes everything.

### Nearby Search and Location

- Save a city or neighborhood in Plugins.
- Buddy remembers the confirmed location across turns and restarts.
- Nearby restaurant, cafe, store, and event requests use that confirmed location.
- Buddy never treats an IP-based guess as the user’s location.
- If no location is confirmed, Buddy asks for one instead of inventing a city.
- Web search uses the Hack Club Search Brave-compatible API when configured.

### Integrations

#### Gmail and Google Workspace

Google OAuth supports Gmail and Workspace features such as:

- Read recent and unread email.
- Create and edit drafts.
- Calendar events and daily calendar views.
- Google Meet links.
- Drive listing, search, upload, and download workflows.
- Docs, Sheets, and Slides creation and editing.
- Tasks, Contacts, Translate, Maps, and supported Photos operations.

Buddy never sends email automatically. It creates drafts for the user to review and send.

Setup requires a Google desktop OAuth `credentials.json`. OAuth tokens are stored in the user data directory.

#### Microsoft 365

Microsoft Graph support includes:

- Outlook unread mail, search, and drafts.
- Outlook calendar events.
- OneDrive listing, search, upload, and download.
- OneNote pages and sections.
- Teams chat operations where the account and permissions support them.
- To Do, Excel, and Contacts helpers.

Microsoft sign-in uses a device code displayed inside Buddy. The browser opens automatically, and Buddy waits for approval without requiring Terminal instructions.

Setup requires an Azure application client ID with the appropriate account types and permissions.

#### Slack

Slack support includes:

- Connect with a Slack bot token directly in Plugins.
- Optional hosted OAuth installation flow.
- List channels.
- Read recent channel messages.
- Send messages after explicit confirmation.

The Slack bot must be invited to channels Buddy should read or use.

#### GitHub

GitHub support includes:

- Device Flow sign-in.
- Account identity verification.
- Repository status and Git operations.
- Branches, commits, pulls, pull requests, and review comments where permissions allow.

A GitHub OAuth App client ID is required for Device Flow.

### Memory and Privacy

- Conversations, profile data, preferences, and long-term memories remain local by default.
- The Memory tab groups what Buddy knows into relationships, work patterns, preferences and choices, important information, and communication style.
- Each memory category can be disabled independently. Disabled categories stop new saves and are excluded from future memory retrieval.
- Saved facts and learned work rules can be edited or deleted; deletion requires confirmation.
- The database is stored outside the application bundle so updates do not erase memory.
- Private chats can be protected by a local Privacy PIN.
- Incognito conversations are not saved as permanent chat history.
- Settings includes data deletion controls.
- Provider credentials are kept in provider token caches or local secure storage paths rather than being sent to the model as ordinary conversation text.
- Buddy does not claim a permission or provider connection succeeded unless the real check succeeds.

### Cost Controls

Buddy is designed to avoid paying repeatedly for the same work:

- Haiku 5.5 handles normal chat, planning, and easy/medium actions.
- Sonnet 5.5 is reserved for hard, high-effort, and deep tasks.
- Image generation remains on the configured image model.
- Embeddings are cached locally by model and text hash, so repeated memory lookups do not call the embedding API again.
- Transient model retries default to two attempts instead of repeatedly multiplying usage.
- Change the retry budget with `BUDDY_MAX_MODEL_RETRIES=1` or another positive integer when needed.
- Provider data and actions are not cached as fake results because they can become stale.

Review OS permissions carefully. Access granted to Terminal, Python, or VS Code is not the same as access granted to a packaged Buddy app.

## Setup

### Requirements

- Python 3.12 or newer recommended.
- macOS 13+, Windows 10+, Linux with a desktop session, or ChromeOS with Linux apps enabled.
- A desktop environment for the PySide6 UI; a headless server is only useful for the optional backend.
- A working model/API configuration.
- Optional provider credentials for integrations.

### Install

```bash
git clone https://github.com/shreyanshoffline/Buddy.git
cd Buddy
python3 -m venv venv
python3 -m pip install -r requirements.txt pytest
python3 main.py
```

For local development, activate `venv` using the normal command for your shell. On Windows, use `python` instead of `python3` if that is the installed command. `main.py` starts the local backend automatically. Set `BUDDY_START_BACKEND=0` for a frontend-only run, or set `BUDDY_BACKEND_PORT` when port 5000 is unavailable.

### Configuration

Copy `.env.example` to `.env` and fill in what you need (at minimum `API_KEY`). From source, keep `.env` in the project folder. For the packaged app, put it in Buddy's data folder, which is also where the database lives:

- macOS: `~/Library/Application Support/Buddy/.env`
- Windows: `%APPDATA%\Buddy\.env`
- Linux and ChromeOS: `~/.local/share/Buddy/.env`

### Hack Club Search

Buddy uses the Brave-compatible Hack Club Search API:

```env
HACK_CLUB_SEARCH_API_KEY=your_key_here
```

The endpoint is `https://search.hackclub.com/res/v1/web/search` and uses a Bearer token. See `https://search.hackclub.com/docs` for API details.

### Provider setup

Provider-specific setup guides live in `knowledge/`:

- `knowledge/google_workspace.md`
- `knowledge/microsoft.md`
- `knowledge/slack.md`
- `knowledge/web_search.md`
- `knowledge/browser.md`
- `knowledge/macos.md`

### Switching between hosted and self-hosted AI

Buddy keeps the model provider behind one small compatibility boundary. The
default is the existing OpenRouter path. To point the same desktop app at a
remote OpenAI-compatible server, copy `.env.example` to `.env` and set:

```env
BUDDY_AI_PROVIDER=self_hosted
BUDDY_SELF_HOSTED_URL=https://your-server.example/v1
BUDDY_SELF_HOSTED_MODEL=Qwen3-1.7B-Instruct
BUDDY_SELF_HOSTED_API_KEY=
```

This works with a server such as `llama-server`, vLLM, Ollama, or a Buddy API
that exposes `/chat/completions`. Manager calls, normal chat, tool calls,
coding mode, retries, and the existing UI use the same code in either mode.
Leave `BUDDY_AI_PROVIDER=openrouter` to preserve the current hosted setup.

Self-hosted mode does not require an embedding service: memory falls back to
Buddy's local keyword retrieval unless `BUDDY_SELF_HOSTED_EMBEDDING_MODEL` is
configured. Image generation remains on OpenRouter by default because a
text-only self-hosted model cannot generate images. Set `BUDDY_IMAGE_PROVIDER`
only when the selected self-hosted server supports the required image API.

For a small CPU-only server, start with one worker and a short context window.
The provider switch is an infrastructure choice, not a promise that every
model has the same coding ability; run the coding evaluation before making a
self-hosted model the default for users.

## Plugins and Permissions

Plugins have two layers:

1. Buddy’s local feature toggle.
2. The operating system permission required by the actual Buddy process.

A plugin cannot honestly show “Granted” just because a local toggle is enabled. Buddy probes the running process and explains when OS approval is still needed.

Common permissions include:

- Microphone for Talk.
- Files & Folders or Full Disk Access for protected files and Messages on macOS.
- Accessibility for UI automation.
- Automation permissions for controlling other Mac apps.
- Camera when a camera feature is enabled.

## Updates and Releases

Buddy uses GitHub Releases instead of a paid update server. Version numbers live in `version.py`; release tags are created from that value.

Run release checks locally:

```bash
python3 -m tools.release_manager check
```

Publish a release through GitHub:

```bash
python3 -m tools.release_manager publish --notes "Describe the release"
```

Build locally on macOS:

```bash
python3 -m pip install -r requirements.txt -r packaging/requirements-build.txt
python3 packaging/build_nuitka.py
```

Build locally on Windows or Linux:

```bash
python -m pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/build_nuitka.py
```

The release build uses Nuitka `--standalone` with the PySide6 plugin. It does
not use `--onefile`: standalone bundles launch faster and are easier to update
because the app files remain together in a normal folder. On macOS the build
also adds the microphone, camera, and Automation permission strings to the app
and re-signs it.

GitHub Actions builds macOS, Windows, and Linux Nuitka standalone ZIPs plus
checksums when a `v*` tag is pushed. ChromeOS users run the Linux ZIP inside
the ChromeOS Linux environment. macOS signing and notarization are optional.

### GitHub release steps

1. Set the next version in `version.py`, such as `0.9.8`.
2. Commit and push the change to GitHub.
3. Open **Actions**, select **Buddy release**, and choose **Run workflow** for
   a pre-release build of all three targets.
4. When the artifacts look correct, create and push a matching tag:

   ```bash
   git tag v0.9.8
   git push origin v0.9.8
   ```

5. GitHub attaches `Buddy-macos-0.9.8.zip`, `Buddy-windows-0.9.8.zip`,
   `Buddy-linux-0.9.8.zip`, and their SHA-256 files to the release.
6. Extract the whole ZIP and launch the executable inside it. Do not move only
   the executable out of the standalone folder.

Updates preserve memory because the database lives outside the app bundle:

- macOS: `~/Library/Application Support/Buddy/`
- Windows: `%APPDATA%/Buddy/`
- Linux and ChromeOS Linux: `$XDG_DATA_HOME/Buddy/` or `~/.local/share/Buddy/`

## Testing

Run the active suite with the project environment:

```bash
python -m pytest -q tests
```

The suite runs offline (no accounts or network) and covers database migrations, memory controls, location memory, the tiered agent pipeline, coding mode, provider configuration, the Slack and platform layers, and a headless GUI smoke test.

## Project Layout

```text
main.py                 Application entry point
backend/                Local Flask service and single-process runtime
core/                   Agent pipeline, prompts, plugins, updates
gui/                    PySide6 interface and bundled assets
storage/                SQLite database and migrations
tools/                  Shared OS adapter, provider integrations, and tools
knowledge/              Guides Buddy reads, including its capability list
packaging/              Nuitka build, Info.plist, entitlements, release notes
future/model_workflow/  Experimental workflow editor kept for a future release
docs/images/            Screenshots used by this README
tests/                  Offline regression tests
ARCHITECTURE.md         Short codebase map
```

## Known Limitations

- The voice pipeline is record, transcribe, generate, speak rather than fully streaming.
- The free macOS build is ad-hoc signed, so macOS warns on first launch (right-click, Open). Developer ID signing and notarization are optional.
- Apple-app automation is macOS only; other systems get shared desktop, browser, file, and web actions.
- Packaged-app permissions and live provider accounts need a real run on each OS.

## Future Updates

- Fully streaming voice with streaming speech recognition, model output, and speech synthesis.
- Faster interruption and barge-in behavior during speech.
- More complete browser automation and a visible browser permission toggle.
- First-run capability setup that explains permissions one at a time.
- More memory insights and review tools beyond the current category controls.
- Revisit the archived model workflow only after it has a clear user benefit and a tested responsive layout (`future/model_workflow/`).
- Smaller, generated tool schemas instead of large hand-maintained schema files.
- More isolated provider tests with deterministic fake services.
- Better Qt accessibility and responsive-layout testing.
- Optional scheduled jobs and proactive briefings.
- Signed and notarized builds for a smoother macOS first launch.
- Release notes displayed directly inside the update banner.
- Dedicated Windows and Linux native adapters for screenshots, notifications, clipboard, power, and accessibility.
- ChromeOS PWA or packaged-web shell once the shared web client exists.

## Credits

The Memory icon is based on the Lucide "brain" icon (ISC License).

## License

No license has been declared yet. Treat this repository as source-available until a license is added.
