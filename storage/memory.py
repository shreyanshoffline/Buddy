"""Layered RAG memory for Buddy.

Layers, highest priority first:

1. identity  — name, age, bio, apps, links from user_profile
2. facts     — durable things the user asked Buddy to remember
3. episodes  — past tasks that actually worked (task_memories)
4. files     — retrieved chunks from files attached to this chat
5. recents   — short snippets from other recent chats (keyword only)

Each layer is retrieved independently, then packed into one system note
capped so it cannot blow the context window. Embeddings are used when
they exist; otherwise the same keyword scorer already in storage.db
keeps working.
"""
from storage import db

MAX_NOTE_CHARS = 3500
FACT_LIMIT = 8
EPISODE_LIMIT = 3
FILE_CHUNK_LIMIT = 6
RECENT_LIMIT = 3


def _identity_lines(profile):
    if not profile:
        return []
    lines = []
    name = (profile.get("name") or "").strip()
    if name:
        lines.append(f"The user's name is {name}.")
    age = profile.get("age")
    if age:
        lines.append(f"They are {age}.")
    bio = (profile.get("bio") or "").strip()
    if bio:
        lines.append(f"About them: {bio}")
    apps = (profile.get("favorite_apps") or "").strip()
    if apps:
        lines.append(f"Favorite apps: {apps}")
    links = (profile.get("quick_links") or "").strip()
    if links:
        lines.append(f"Quick links: {links}")
    return lines


def build_memory_context(user_input, conversation_id=None, file_context=None):
    """Return a single system-note string, or None if nothing useful."""
    sections = []

    try:
        profile = db.get_profile()
    except Exception:
        profile = {}
    identity = _identity_lines(profile)
    if identity:
        sections.append("Who the user is:\n- " + "\n- ".join(identity))

    try:
        facts = db.find_relevant_facts(user_input, limit=FACT_LIMIT)
    except Exception:
        facts = []
    if facts:
        lines = []
        for fact in facts:
            label = fact.get("category") or "fact"
            lines.append(f"[{label}] {fact['content']}")
        sections.append("Things they asked you to remember:\n- " + "\n- ".join(lines))

    try:
        episodes = db.find_similar_task_memories(user_input, limit=EPISODE_LIMIT, min_overlap=2)
    except Exception:
        episodes = []
    if episodes:
        lines = []
        for mem in episodes:
            worked = mem.get("outcome_summary") or mem.get("plan_text") or ""
            lines.append(f"{mem['task_summary']}" + (f" — {worked}" if worked else ""))
        sections.append("Similar things that worked before:\n- " + "\n- ".join(lines))

    if file_context:
        sections.append(file_context)
    elif conversation_id:
        try:
            chunks = db.find_relevant_chunks(conversation_id, user_input, limit=FILE_CHUNK_LIMIT)
        except Exception:
            chunks = []
        if chunks:
            parts = ["Files attached to this chat. Cite the filename when you use them."]
            for chunk in chunks:
                part = chunk.get("chunk_index", 0) + 1
                parts.append(f"--- {chunk.get('name', 'file')} (part {part}) ---\n{chunk.get('content', '')}")
            sections.append("\n\n".join(parts))

    try:
        recents = db.find_recent_chat_snippets(user_input, limit=RECENT_LIMIT, exclude_conversation_id=conversation_id)
    except Exception:
        recents = []
    if recents:
        lines = [f"{item['role']}: {item['content']}" for item in recents]
        sections.append("Related bits from earlier chats:\n- " + "\n- ".join(lines))

    if not sections:
        return None

    note = (
        "Memory layers for this turn. Use what is relevant. "
        "Do not recite the whole list. If something conflicts with what "
        "the user just said, believe the new message.\n\n"
        + "\n\n".join(sections)
    )
    if len(note) > MAX_NOTE_CHARS:
        note = note[:MAX_NOTE_CHARS].rsplit("\n", 1)[0] + "\n…"
    return note
