# Buddy

Buddy is a local-first AI assistant for macOS. It combines chat, voice conversation, computer tools, integrations, local memory, and a lightweight floating desktop interface.

Buddy is designed to be useful without hiding what happened. When a tool works, Buddy reports the result. When a provider, permission, or network request fails, Buddy shows the actual error and the next action instead of silently improvising.

## Current State

Buddy is an active macOS beta at version `0.9.5`.

Implemented and tested:

- Local PySide6 desktop interface with chat, sidebar navigation, Library, Plugins, Models, Talk, Pricing, and Settings.
- SQLite persistence for conversations, messages, memories, profile settings, plugin settings, and voice chats.
- Automatic database migrations and recovery for older or damaged databases.
- User data stored outside the app bundle at `~/Library/Application Support/Buddy/`.
- Manager/worker agent pipeline with model routing, plans, tool execution, cancellation, timeouts, action receipts, and transparent failures.
- Confirmed user location for nearby searches without guessing from IP geolocation.
- Concise voice-mode replies when Buddy is speaking aloud.
- Free macOS system speech with Siri-like Apple voice preference and Premium/Enhanced fallback.
- GitHub Releases update checks, Settings update controls, startup update hints, and memory-preserving app replacement.
- Free GitHub Actions release packaging.

The project has passed the active offline test suite. Packaged-app permissions, live provider accounts, and notarized distribution still require real Mac release testing.

## Features

### Chat

- Regular conversations with saved history.
- Incognito conversations that do not become permanent chat history.
- Conversation titles, search, favorites, archive state, private chats, and message feedback.
- Attachments with text extraction and searchable chunks.
- Image understanding and image generation where the configured model supports it.
- Model and thinking-level controls.
- Retry and redo flows.
- Action plans with expandable tool details and results.

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

With the required macOS permission and plugin enabled, Buddy can work with:

- Applications: open, close, activate, list, and force-quit with confirmation.
- Finder and files: list, read, write, append, create, copy, move, rename, trash, delete, search, and reveal.
- Browser workflows through the configured browser tools.
- Clipboard, screenshots, notifications, volume, dark mode, system information, battery, disk, memory, and processes.
- Apple apps including Calendar, Reminders, Notes, Messages, Mail, Music, Safari, Photos, Finder, and Shortcuts.
- Terminal and code execution when explicitly enabled, with confirmation for dangerous commands.

Destructive operations remain protected by confirmation dialogs. This is intentional: “do everything” does not mean silently delete data or change the system without approval.

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

Review macOS permissions carefully. Access granted to Terminal, Python, or VS Code is not the same as access granted to a packaged Buddy.app.

## Setup

### Requirements

- macOS for the full desktop feature set.
- Python 3.12 or newer recommended.
- A working model/API configuration.
- Optional provider credentials for integrations.

### Install

```bash
git clone https://github.com/shreyanshoffline/Buddy.git
cd Buddy
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest
python main.py
```

For local development, use the project virtual environment. Some optional integrations require additional packages listed in `requirements.txt`.

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

## Plugins and Permissions

Plugins have two layers:

1. Buddy’s local feature toggle.
2. macOS permission for the actual Buddy process.

A plugin cannot honestly show “Granted” just because a local toggle is enabled. Buddy probes the running process and explains when macOS approval is still needed.

Common permissions include:

- Microphone for Talk.
- Files & Folders or Full Disk Access for protected files and Messages.
- Accessibility for UI automation.
- Automation permissions for controlling other Mac apps.
- Camera when a camera feature is enabled.

## Updates and Releases

Buddy uses GitHub Releases instead of a paid update server.

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
bash packaging/build_mac.sh
```

GitHub Actions builds `Buddy-macOS.zip` and its SHA-256 checksum when a `v*` tag is pushed. The free build is ad-hoc signed. Developer ID signing and Apple notarization are optional and require Apple Developer credentials.

Updates preserve memory because the database lives at:

```text
~/Library/Application Support/Buddy/buddy.db
```

## Testing

Run the active suite with the project environment:

```bash
venv/bin/python -m pytest -q tests
```

The tests cover database migrations, profile persistence, location memory, action status, provider configuration, and core behavior that can run offline.

## Project Layout

```text
main.py                 Application entry point
core/                   Agent pipeline, prompts, plugins, updates
gui/                    Active PySide6 interface
storage/                SQLite database and migrations
tools/                  Mac tools and provider integrations
knowledge/              Focused provider and system guides
packaging/              macOS build and release files
tests/                  Offline regression tests
PROJECT_STATUS.md       Consolidated project status and release checklist
ARCHITECTURE.md         Short codebase map
```

## Future Updates

- Fully streaming voice with streaming speech recognition, model output, and speech synthesis.
- Faster interruption and barge-in behavior during speech.
- More complete browser automation and a visible browser permission toggle.
- First-run capability setup that explains permissions one at a time.
- A lessons interface for reviewing and deleting things Buddy learned.
- Smaller, generated tool schemas instead of large hand-maintained schema files.
- More isolated provider tests with deterministic fake services.
- Better Qt accessibility and responsive-layout testing.
- Optional scheduled jobs and proactive briefings.
- Signed and notarized builds for a smoother macOS first launch.
- Release notes displayed directly inside the update banner.

## License

No license has been declared yet. Treat this repository as source-available until a license is added.
