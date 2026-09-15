"""Persisted plugin prefs and tool gating.

Toggles live in user_profile.plugins_json. The worker only sees tools that
are currently allowed. execute_tool also refuses a blocked tool so a stale
plan cannot sneak past the schema filter.
"""
import json
from urllib.parse import urlparse

from storage import db
from tools.tools_schema import tools_schema

GMAIL_TOOLS = {
    "check_gmail_connection",
    "get_recent_emails",
    "get_unread_emails",
    "create_draft",
    "list_drafts",
    "modify_draft",
}
SEARCH_TOOLS = {"web_search"}
WEATHER_TOOLS = {"get_weather"}
MESSAGES_TOOLS = {
    "lookup_contact_number",
    "send_imessage",
    "get_unread_messages",
    "list_group_chats",
    "send_group_message",
}
TERMINAL_TOOLS = {"run_terminal_command", "run_code"}
EDITOR_TOOLS = {"open_folder_in_editor"}
BROWSER_TOOLS = {
    "browser_action",
    "list_open_tabs",
    "close_tab",
    "get_active_tab_info",
    "navigate_active_tab",
}
POWER_TOOLS = {"sleep_display", "lock_screen", "start_screensaver"}
FILE_TOOLS = {
    "list_directory",
    "read_file_content",
    "write_file_content",
    "append_to_file",
    "create_file",
    "create_directory",
    "copy_file",
    "move_file",
    "rename_file",
    "trash_file",
    "delete_file",
    "empty_trash",
    "get_file_info",
    "search_local_files",
    "open_in_finder",
    "open_folder_in_editor",
    "run_code",
}
URL_TOOLS = {"open_url", "navigate_active_tab", "download_file", "ping_host"}

GOOGLE_WORKSPACE_TOOLS = {
    "calendar_today", "calendar_create_event", "calendar_move_event", "meet_create_link",
    "drive_list_recent", "drive_upload_file", "docs_create", "docs_append_heading",
    "sheets_create", "sheets_write_range", "sheets_read_range",
    "slides_create_from_bullets", "translate_text", "maps_directions", "photos_list_recent",
}
MICROSOFT_TOOLS = {
    "outlook_unread", "outlook_create_draft", "outlook_today", "outlook_create_event",
    "onedrive_recent", "onedrive_upload", "onenote_list_sections", "onenote_create_page",
    "teams_list_chats", "teams_send_message",
}
SLACK_TOOLS = {
    "slack_list_channels", "slack_recent_messages", "slack_send_message",
}
GITHUB_OPS_TOOLS = {
    "github_clone_repo", "github_status", "github_create_branch", "github_commit_all",
    "github_push", "github_pull", "github_create_pull_request", "github_list_open_prs",
    "github_add_pr_comment", "github_add_review_comment", "add_code_comment",
}
APPLE_TOOLS = {
    "reminders_list", "reminders_add", "reminders_complete",
    "notes_find", "notes_append", "notes_create",
    "apple_calendar_today", "apple_calendar_create_event", "apple_calendar_move_event",
    "messages_recent_threads", "messages_draft",
    "mail_list_inbox", "mail_create_draft",
    "music_play", "music_pause", "music_play_playlist", "music_now_playing",
    "facetime_call", "clock_run_shortcut",
    "finder_reveal", "finder_move", "finder_trash",
    "safari_list_tabs", "safari_open_url", "safari_current_tab_title",
    "photos_search", "photos_export_one",
    "appstore_open_search", "appstore_open_product_id",
    "open_system_settings_pane", "icloud_probe", "icloud_list",
}


APP_ALIASES = {
    "slack": ("slack",),
    "messages": ("messages", "imessage"),
    "vscode": ("visual studio code", "vs code", "code", "vscode"),
    "terminal": ("terminal", "iterm"),
    "chrome": ("chrome", "chromium", "google chrome"),
}


def default_plugins():
    return {
        "universal": {"gmail": False, "web_search": True, "weather": True},
        "apps": {},
        "websites": [],
        "system": {
            "full_disk_access": False,
            "folder_access": False,
            "microphone": True,
            "camera": False,
            "power_controls": False,
        },
    }


def load_plugins():
    profile = db.get_profile() or {}
    raw = profile.get("plugins_json") or ""
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    base = default_plugins()
    base["universal"].update(data.get("universal") or {})
    base["apps"].update(data.get("apps") or {})
    sites = data.get("websites") or []
    if isinstance(sites, list):
        base["websites"] = [str(s).strip() for s in sites if str(s).strip()]
    base["system"].update(data.get("system") or {})
    return base


def save_plugins(data):
    db.update_profile(plugins_json=json.dumps(data))


def _app_on(plugins, key):
    return bool(plugins.get("apps", {}).get(key, True))


def tool_allowed(tool_name, plugins=None):
    plugins = plugins or load_plugins()
    name = (tool_name or "").split(".")[-1]

    if name in GMAIL_TOOLS:
        if not plugins["universal"].get("gmail", False):
            return False
        try:
            from tools.tools import gmail_connection_status
            if not gmail_connection_status().get("connected"):
                return False
        except Exception:
            return False
    if name in SEARCH_TOOLS and not plugins["universal"].get("web_search", True):
        return False
    if name in WEATHER_TOOLS and not plugins["universal"].get("weather", True):
        return False
    if name in MESSAGES_TOOLS and not _app_on(plugins, "messages"):
        return False
    if name in TERMINAL_TOOLS and not _app_on(plugins, "terminal"):
        return False
    if name in EDITOR_TOOLS and not _app_on(plugins, "vscode"):
        return False
    if name in BROWSER_TOOLS and not _app_on(plugins, "chrome"):
        return False
    if name in POWER_TOOLS and not plugins["system"].get("power_controls"):
        return False
    if name in FILE_TOOLS and not (
        plugins["system"].get("full_disk_access")
        or plugins["system"].get("folder_access")
    ):
        return False
    if name in GOOGLE_WORKSPACE_TOOLS:
        try:
            import core
            if not core.get_plugin_connection("google"):
                return False
        except Exception:
            return False
    if name in MICROSOFT_TOOLS:
        try:
            import core
            if not core.get_plugin_connection("microsoft"):
                return False
        except Exception:
            return False
    if name in GITHUB_OPS_TOOLS:
        try:
            import core
            if not core.get_plugin_connection("github"):
                return False
        except Exception:
            return False
    if name in SLACK_TOOLS:
        try:
            import core
            if not core.get_plugin_connection("slack"):
                return False
        except Exception:
            return False
    if name in APPLE_TOOLS:
        import platform
        if platform.system() != "Darwin":
            return False
    return True


def _host(value):
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        return (urlparse(text).hostname or "").lower().lstrip("www.")
    except Exception:
        return text.lower()


def website_allowed(url, plugins=None):
    plugins = plugins or load_plugins()
    allow = [_host(s) for s in plugins.get("websites") or []]
    allow = [s for s in allow if s]
    if not allow:
        return True
    host = _host(url)
    if not host:
        return False
    return any(host == site or host.endswith("." + site) for site in allow)


def blocked_reason(tool_name, tool_args=None, plugins=None):
    plugins = plugins or load_plugins()
    name = (tool_name or "").split(".")[-1]
    if not tool_allowed(name, plugins):
        if name in FILE_TOOLS:
            return (
                "Buddy's file access is turned off. Enable Full Disk Access or "
                "Files & Folders in Plugins, then approve Buddy in macOS "
                "Privacy & Security."
            )
        if name in GOOGLE_WORKSPACE_TOOLS:
            return "Google isn't connected. Plugins > Google > Connect."
        if name in MICROSOFT_TOOLS:
            return "Microsoft isn't connected. Plugins > Microsoft > Connect."
        if name in GITHUB_OPS_TOOLS:
            return "GitHub isn't connected. Plugins > GitHub > Connect."
        if name in SLACK_TOOLS:
            return "Slack isn't connected. Plugins > Slack > Connect."
        if name in APPLE_TOOLS:
            return "This is an Apple-only tool and isn't available on this OS."
        return "This plugin is turned off in Plugins."
    args = tool_args or {}
    if name == "open_app":
        app = (args.get("app") or args.get("app_name") or args.get("name") or "").lower()
        for key, aliases in APP_ALIASES.items():
            if any(alias in app for alias in aliases) and not _app_on(plugins, key):
                return f"{key} is turned off in Plugins."
    if name in URL_TOOLS:
        target = args.get("url") or args.get("host") or args.get("query") or ""
        if target and not website_allowed(target, plugins):
            return "That website is not in the allowed list in Plugins."
    return None


def active_tools_schema(plugins=None):
    plugins = plugins or load_plugins()
    out = []
    for item in tools_schema:
        fn = (item.get("function") or {})
        name = fn.get("name") or ""
        if tool_allowed(name, plugins):
            out.append(item)
    return out