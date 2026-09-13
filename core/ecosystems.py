"""Google Workspace and Microsoft Graph connection helpers, following the
same set_plugin_connection/get_plugin_connection pattern already used
for GitHub and Slack in core/conversations.py."""

import os

from core.conversations import set_plugin_connection, remove_plugin_connection, get_plugin_connection

__all__ = [
    "check_google_connection", "connect_google", "disconnect_google",
    "check_microsoft_connection", "connect_microsoft", "disconnect_microsoft",
]


def check_google_connection() -> str:
    if get_plugin_connection("google"):
        return "OK: connected"
    return "NOT_CONNECTED: Plugins > Google > Connect."


def connect_google() -> str:
    try:
        from tools import google_workspace_tools as gwt
        gwt._get_credentials()
        set_plugin_connection("google", "connected", None)
        return "OK: connected"
    except Exception as e:
        return f"ERROR: {e}"


def disconnect_google() -> str:
    from tools.google_workspace_tools import TOKEN_PATH
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)
    remove_plugin_connection("google")
    return "Disconnected Google."


def check_microsoft_connection() -> str:
    if get_plugin_connection("microsoft"):
        return "OK: connected"
    return "NOT_CONNECTED: Plugins > Microsoft > Connect."


def connect_microsoft() -> str:
    try:
        from tools import msgraph_tools as mst
        mst._get_token()
        set_plugin_connection("microsoft", "connected", None)
        return "OK: connected"
    except Exception as e:
        return f"ERROR: {e}"


def disconnect_microsoft() -> str:
    from tools.msgraph_tools import TOKEN_CACHE_PATH
    if os.path.exists(TOKEN_CACHE_PATH):
        os.remove(TOKEN_CACHE_PATH)
    remove_plugin_connection("microsoft")
    return "Disconnected Microsoft."
