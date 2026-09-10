"""The catalog of Mac apps Buddy knows how to recognize and (for some)
actually control via tools.py. Shared by GUI/pages/plugins_page.py (to
render toggles) and core/agent.py (to gate the matching tool calls) so
the two never drift apart.

Each entry: (key, label, [candidate .app paths], description).
`key` is the plugin_toggles key, prefixed "app:" by convention.
"""
import os

APP_CATEGORIES = [
    ("Communication & calls", [
        ("app:messages", "Messages", ["/System/Applications/Messages.app", "/Applications/Messages.app"], "Send and read iMessages."),
        ("app:facetime", "FaceTime", ["/System/Applications/FaceTime.app", "/Applications/FaceTime.app"], "Make calls and see your call history."),
        ("app:zoom", "Zoom", ["/Applications/zoom.us.app"], "Join or start Zoom meetings."),
        ("app:teams", "Microsoft Teams", ["/Applications/Microsoft Teams.app", "/Applications/Microsoft Teams (work or school).app"], "Join Teams meetings and read channels."),
        ("app:slack", "Slack", ["/Applications/Slack.app"], "Read channels and send messages you approve."),
        ("app:discord", "Discord", ["/Applications/Discord.app"], "Read and send messages in your servers."),
        ("app:whatsapp", "WhatsApp", ["/Applications/WhatsApp.app"], "Send and read WhatsApp messages."),
    ]),
    ("Calendar & tasks", [
        ("app:calendar", "Calendar", ["/System/Applications/Calendar.app", "/Applications/Calendar.app"], "Create and check events on your calendar."),
        ("app:reminders", "Reminders", ["/System/Applications/Reminders.app", "/Applications/Reminders.app"], "Add and check your reminders."),
        ("app:contacts", "Contacts", ["/System/Applications/Contacts.app", "/Applications/Contacts.app"], "Look up phone numbers and contact info."),
        ("app:notes", "Notes", ["/System/Applications/Notes.app", "/Applications/Notes.app"], "Create and read notes."),
    ]),
    ("Media", [
        ("app:spotify", "Spotify", ["/Applications/Spotify.app"], "Control playback and play your playlists."),
        ("app:music", "Music", ["/System/Applications/Music.app", "/Applications/Music.app"], "Control playback in Apple Music."),
        ("app:photos", "Photos", ["/System/Applications/Photos.app", "/Applications/Photos.app"], "Browse your photo library."),
    ]),
    ("Browsers", [
        ("app:safari", "Safari", ["/Applications/Safari.app"], "Open pages and read what's on screen."),
        ("app:chrome", "Chrome", ["/Applications/Google Chrome.app"], "Open tabs and read what's on screen."),
        ("app:firefox", "Firefox", ["/Applications/Firefox.app"], "Open pages and read what's on screen."),
        ("app:arc", "Arc", ["/Applications/Arc.app"], "Open pages and read what's on screen."),
    ]),
    ("Developer tools", [
        ("app:terminal", "Terminal", ["/Applications/Utilities/Terminal.app", "/System/Applications/Utilities/Terminal.app"], "Run commands you approve."),
        ("app:iterm", "iTerm", ["/Applications/iTerm.app"], "Run commands you approve."),
        ("app:vscode", "VS Code", ["/Applications/Visual Studio Code.app"], "Open files and run tasks in your editor."),
        ("app:cursor", "Cursor", ["/Applications/Cursor.app"], "Open files and run tasks in your editor."),
        ("app:xcode", "Xcode", ["/Applications/Xcode.app"], "Open and build Xcode projects."),
        ("app:pycharm", "PyCharm", ["/Applications/PyCharm.app", "/Applications/PyCharm CE.app"], "Open files and run tasks in your editor."),
        ("app:sublime", "Sublime Text", ["/Applications/Sublime Text.app"], "Open files in your editor."),
        ("app:androidstudio", "Android Studio", ["/Applications/Android Studio.app"], "Open and build Android Studio projects."),
        ("app:githubdesktop", "GitHub Desktop", ["/Applications/GitHub Desktop.app"], "Open repos in GitHub Desktop."),
    ]),
]


def detect_installed_apps():
    """Returns APP_CATEGORIES filtered down to only apps actually found
    on this Mac. Shape: [(category_label, [(key, label, description), ...]), ...]
    Categories with no detected apps are dropped entirely."""
    result = []
    for category_label, entries in APP_CATEGORIES:
        found = [(key, label, desc) for key, label, paths, desc in entries if any(os.path.exists(p) for p in paths)]
        if found:
            result.append((category_label, found))
    return result


def app_key_for_name(app_name):
    """Best-effort match from a free-text app name (as an LLM tool call
    would pass it, e.g. 'Slack' or 'Google Chrome') to a catalog key.
    Returns None if the app isn't one Buddy has a toggle for — those stay
    ungated, same as before this catalog existed."""
    if not app_name:
        return None
    needle = app_name.strip().lower()
    for _category_label, entries in APP_CATEGORIES:
        for key, label, _paths, _desc in entries:
            label_lower = label.lower()
            if needle == label_lower or needle in label_lower or label_lower in needle:
                return key, label
    return None
