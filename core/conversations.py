"""Conversation-facing orchestration: everything that touches conversation_id
and the database. Calls into agent.py for the actual model pipeline.
"""
from core.agent import (
    process_message, process_message_incognito,
    generate_conversation_title, format_attachment_context,
)
from core.instruction import build_manager_instruction
from storage import db

def _sanitize_history_for_model(history):
    sanitized = []
    for msg in history:
        clean_msg = {k: v for k, v in msg.items() if k != "tool_call_id"}
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and all(isinstance(item, dict) for item in tool_calls):
            clean_msg["tool_calls"] = tool_calls
        sanitized.append(clean_msg)
    return sanitized
 
 
def _ensure_conversation_title(conversation_id, user_text, response_title=None):
    current_title = db.get_conversation_title(conversation_id) or ""
    title = response_title
 
    # Only generate an automatic title when the conversation still has a default title.
    if not title and current_title.strip().lower() in ("new chat", "untitled chat", ""):
        title = generate_conversation_title(user_text)  # LLM title, falls back to truncation internally
 
    if title:
        db.touch_conversation(conversation_id, title=title)
    return title

def send_and_save_message(conversation_id, user_text, on_event=None, attachments=None, cancel_check=None):
    previous_history = db.load_messages(conversation_id)

    db.save_message(conversation_id, "user", content=user_text)
    user_msg_id = db.latest_user_message_id(conversation_id)

    if attachments:
        db.save_conversation_attachments(conversation_id, user_msg_id, attachments)

    history = new_message_history() + _sanitize_history_for_model(previous_history)

    excerpts = db.find_relevant_chunks(conversation_id, user_text, limit=6)
    file_context = format_attachment_context(excerpts)

    image_attachments = [item for item in (attachments or []) if item.get("mime_type", "").startswith("image/")]
    result = process_message(user_text, history, on_event=on_event, file_context=file_context, cancel_check=cancel_check, image_attachments=image_attachments)

    assistant_metadata = None
    if result.get("plan_text") or result.get("tools_used") or result.get("stats"):
        assistant_metadata = {
            "plan_text": result.get("plan_text"),
            "tools_used": result.get("tools_used"),
            "tool_log": result.get("tool_log"),
            "stats": result.get("stats"),
            "images": result.get("images", []),
        }

    result["message_id"] = db.save_message(
        conversation_id,
        "assistant",
        content=result["reply"],
        metadata=assistant_metadata
    )
    for index, image_url in enumerate(result.get("images", []), start=1):
        db.save_artifact(f"Buddy creation {index}", image_url, "image", conversation_id)

    title = _ensure_conversation_title(conversation_id, user_text, result.get("chat_title"))
    if title:
        result["chat_title"] = title
        result["title"] = title

    return result
 
def redo_assistant_response(conversation_id, user_text, on_event=None, cancel_check=None):
    """Regenerates the assistant response for the same user query and saves it as a new assistant message."""
    previous_history = db.load_messages(conversation_id)
    history = new_message_history() + _sanitize_history_for_model(previous_history)
    result = process_message(user_text, history, on_event=on_event, cancel_check=cancel_check)
 
    assistant_metadata = None
    if result.get("plan_text") or result.get("tools_used") or result.get("stats"):
        assistant_metadata = {
            "plan_text": result.get("plan_text"),
            "tools_used": result.get("tools_used"),
            "tool_log": result.get("tool_log"),
            "stats": result.get("stats")
        }
 
    result["message_id"] = db.save_message(
        conversation_id,
        "assistant",
        content=result["reply"],
        metadata=assistant_metadata
    )
 
    title = _ensure_conversation_title(conversation_id, user_text, result.get("chat_title"))
    if title:
        result["chat_title"] = title
        result["title"] = title
 
    return result
 
 
def get_recent_conversations(limit=5, exclude_private=False, filter_mode="all"):
    """Fetches real chat history titles and IDs. Library passes the default
    (shows everything, with a lock glyph); the sidebar passes
    exclude_private=True so private chats don't casually surface there.
    filter_mode: 'all' | 'favorites' | 'archived'."""
    return db.list_conversations(limit=limit, exclude_private=exclude_private, filter_mode=filter_mode)


def search_conversations(query, limit=50, filter_mode="all"):
    """Searches chat titles AND message content."""
    return db.search_conversations(query, limit=limit, filter_mode=filter_mode)


def set_conversation_favorite(conversation_id, is_favorite):
    return db.set_conversation_favorite(conversation_id, is_favorite)


def set_conversation_archived(conversation_id, is_archived):
    return db.set_conversation_archived(conversation_id, is_archived)


def set_conversation_private(conversation_id, is_private):
    db.set_conversation_private(conversation_id, is_private)
 
 
def get_conversation_title(conversation_id):
    return db.get_conversation_title(conversation_id)


def get_conversation_is_private(conversation_id):
    return db.get_conversation_is_private(conversation_id)
 
 
def create_conversation():
    return db.create_conversation(title="New chat")
 
 
def delete_conversation(conversation_id):
    db.delete_conversation(conversation_id)
 
 
def get_conversation_history(conversation_id):
    return db.load_messages_with_metadata(conversation_id)


def set_message_feedback(message_id, feedback):
    db.set_message_feedback(message_id, feedback)
 
 
def create_conversation_from_title(user_text):
    title = db.auto_title_from_first_message(user_text)
    return db.create_conversation(title=title)
 
 
def new_message_history():
    return [{"role": "system", "content": build_manager_instruction(db.get_profile())}]


def get_profile():
    return db.get_profile()


def update_profile(**fields):
    return db.update_profile(**fields)


def set_privacy_pin(pin):
    return db.set_privacy_pin(pin)


def has_privacy_pin():
    return db.has_privacy_pin()


def verify_privacy_pin(pin):
    return db.verify_privacy_pin(pin)


def list_artifacts(limit=100):
    return db.list_artifacts(limit)


def delete_artifact(artifact_id):
    return db.delete_artifact(artifact_id)