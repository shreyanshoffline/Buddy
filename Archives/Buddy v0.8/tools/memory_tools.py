"""Remember / forget / list durable facts. Imported by tools.tools so the
worker can call them like any other tool.
"""


def remember_fact(fact, category="general"):
    """Save a durable fact the user wants Buddy to remember across chats."""
    from storage import db
    text = (fact or "").strip()
    if not text:
        return "Nothing to remember — the fact was empty."
    fact_id = db.save_memory_fact(text, category=category or "general")
    return f"Remembered ({category or 'general'}) as fact #{fact_id}: {text}"


def forget_fact(query):
    """Delete remembered facts that match a short query."""
    from storage import db
    text = (query or "").strip()
    if not text:
        return "Tell me which fact to forget."
    removed = db.delete_memory_facts(text)
    if not removed:
        return f"I couldn't find a remembered fact matching '{text}'."
    listing = "; ".join(f"#{item['id']} {item['content']}" for item in removed)
    return f"Forgot {len(removed)} fact(s): {listing}"


def list_remembered_facts():
    """List durable facts Buddy is currently holding, including
    short/medium-term observations it's noticed on its own."""
    from storage import db
    facts = db.list_memory_facts(limit=40)
    if not facts:
        return "No durable facts saved yet."
    lines = []
    for item in facts:
        tier = item.get("tier") or "long"
        tag = "" if tier == "long" else f" ({tier}-term)"
        lines.append(f"#{item['id']} [{item.get('category') or 'general'}]{tag} {item['content']}")
    return "Remembered facts:\n" + "\n".join(lines)