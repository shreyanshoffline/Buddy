"""Public API for the `core` package. GUI code should only ever do
`import core` / `from core import x` — never reach into core.agent or
core.conversations directly, and never import storage/tools/models.
"""
from storage import db as _db
_db.init_db()
try:
    _db.prune_stale_short_term_memories()
except Exception:
    pass  # never block app startup over a housekeeping task

from core.agent import process_message, process_message_incognito
from core.conversations import (
    send_and_save_message,
    redo_assistant_response,
    get_recent_conversations,
    search_conversations,
    set_conversation_private,
    get_conversation_title,
    get_conversation_is_private,
    create_conversation,
    delete_conversation,
    get_conversation_history,
    set_message_feedback,
    create_conversation_from_title,
    new_message_history,
    get_profile,
    update_profile,
    set_privacy_pin,
    has_privacy_pin,
    verify_privacy_pin,
    set_conversation_favorite,
    set_conversation_archived,
    list_artifacts,
    delete_artifact,
    effective_thinking_level,
    get_plugin_toggle,
    set_plugin_toggle,
    list_plugin_toggles,
    add_plugin_folder,
    remove_plugin_folder,
    list_plugin_folders,
    add_plugin_website,
    remove_plugin_website,
    list_plugin_websites,
    set_plugin_connection,
    remove_plugin_connection,
    get_plugin_connection,
    list_plugin_connections,
)

try:
    from core.conversations import refresh_history_profile
except Exception:
    def refresh_history_profile(message_history):
        return message_history

get_or_create_buddy_user_id = _db.get_or_create_buddy_user_id

__all__ = [
    "process_message", "process_message_incognito",
    "send_and_save_message", "redo_assistant_response",
    "get_recent_conversations", "search_conversations",
    "set_conversation_private", "get_conversation_title",
    "get_conversation_is_private", "create_conversation",
    "delete_conversation", "get_conversation_history",
    "set_message_feedback", "create_conversation_from_title",
    "new_message_history", "get_profile", "update_profile",
    "set_privacy_pin", "has_privacy_pin", "verify_privacy_pin",
    "set_conversation_favorite", "set_conversation_archived",
    "get_or_create_buddy_user_id",
    "list_artifacts", "delete_artifact",
    "effective_thinking_level",
    "get_plugin_toggle", "set_plugin_toggle", "list_plugin_toggles",
    "add_plugin_folder", "remove_plugin_folder", "list_plugin_folders",
    "add_plugin_website", "remove_plugin_website", "list_plugin_websites",
    "set_plugin_connection", "remove_plugin_connection",
    "get_plugin_connection", "list_plugin_connections",
]