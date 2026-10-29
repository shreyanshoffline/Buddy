"""Turn raw tool results into what the user actually asked to see.

The worker often ends with finish_task("Task successfully completed.") after a
read-only tool (unread messages, today's calendar, a note...). The data was
fetched but never shown. compose() puts it back in the final reply.
"""
import re

GENERIC = re.compile(r"^\s*(task\s+(successfully\s+)?completed\.?|done\.?|completed\.?|all\s+done\.?)\s*$", re.I)

# Tools whose output IS the answer. Anything not listed here is an action
# (send/create/open...) whose own summary is enough.
READ_TOOLS = {
    "get_unread_messages", "messages_recent_threads", "notes_find", "apple_calendar_today",
    "reminders_list", "get_unread_emails", "get_recent_emails", "calendar_today",
    "calendar_list_range", "outlook_unread", "outlook_today", "mail_list_inbox",
    "list_group_chats", "slack_recent_messages",
}

MAX_CHARS = 3500


def _format_unread(rows):
    errors = [r.get("error") for r in rows if isinstance(r, dict) and r.get("error")]
    if errors:
        return "Couldn't read messages: " + errors[0]
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return "No unread messages."
    groups = {}
    for r in rows:
        groups.setdefault(r.get("chat_name") or r.get("sender") or "Unknown chat", []).append(r)
    lines = []
    for chat, items in groups.items():
        lines.append(f"**{chat}** ({len(items)})")
        for r in items:
            who = r.get("sender") or chat
            when = (r.get("timestamp") or "")[:16].replace("T", " ")
            text = (r.get("text") or "[no text]").strip().replace("\n", " ")
            lines.append(f"- {who} · {when}: {text[:240]}")
    return "\n".join(lines)


def _format_generic(result):
    if isinstance(result, list):
        lines = []
        for item in result[:40]:
            if isinstance(item, dict):
                lines.append("- " + " | ".join(f"{v}" for v in item.values() if v not in (None, "")))
            else:
                lines.append(f"- {item}")
        return "\n".join(lines)
    return str(result).strip()


def format_for_user(tool_name, result):
    """Readable text for a read tool's result, or None for action tools / failures."""
    if tool_name not in READ_TOOLS or result in (None, "", [], {}):
        return None
    if tool_name == "get_unread_messages" and isinstance(result, list):
        text = _format_unread(result)
    else:
        text = _format_generic(result)
    if not text:
        return None
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n..."


def compose(summary, readouts):
    """summary = worker's finish_task text; readouts = [(tool_name, formatted_text)]."""
    summary = (summary or "").strip()
    shown = "\n\n".join(text for _, text in readouts if text)
    if not shown:
        return summary or "Done."
    if not summary or GENERIC.match(summary):
        return shown
    if len(summary) < 80 and shown not in summary:
        return f"{summary}\n\n{shown}"
    return summary
