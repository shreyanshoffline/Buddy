"""Token budget, tool relevance, and chat compaction for Buddy.

Why this exists: the worker used to receive ALL ~209 tool schemas (~16k tokens)
on every request, and the whole chat history on every manager call. This module
keeps one user turn under TURN_TOKEN_CAP by:

  1. select_tools()      - send only the tools relevant to this request
  2. find_tools          - a tiny meta-tool so the worker can pull in more on demand
  3. trim_result()       - shrink big tool outputs before they go back to the model
  4. compact_history()   - summarize old chat messages once the chat gets long
  5. fits_budget()       - hard stop instead of silently burning tokens

Pure stdlib (+ lazy import of models for the summarizer), so it is easy to test.
"""
import difflib
import json
import re

TURN_TOKEN_CAP = 20_000       # hard ceiling of prompt tokens for ONE user turn
WORKER_TOOL_LIMIT = 14        # max tools offered to the worker per request
FIND_TOOLS_LIMIT = 8          # max tools one find_tools call can load
RESULT_TOKEN_LIMIT = 1_200    # tool output kept for the model (full output stays in the work log)
HISTORY_COMPACT_AT = 3_500    # compact when chat history (without system prompt) passes this
KEEP_RECENT = 6               # newest messages are never summarized

CORE_TOOLS = ("finish_task", "read_guide", "find_tools")

# The model keeps picking the old duplicates. Hide them when the better one exists.
DEPRECATED = {
    "create_note": "notes_create",
    "create_calendar_event": "apple_calendar_create_event",
    "create_reminder": "reminders_add",
}

# Tools that belong together: if one is selected strongly, offer its siblings.
FAMILIES = (
    {"send_imessage", "get_unread_messages", "lookup_contact_number", "list_group_chats",
     "send_group_message", "messages_recent_threads", "messages_draft"},
    {"notes_create", "notes_find", "notes_append"},
    {"apple_calendar_today", "apple_calendar_create_event", "apple_calendar_move_event"},
    {"reminders_list", "reminders_add", "reminders_complete"},
    {"get_recent_emails", "get_unread_emails", "create_draft", "list_drafts", "modify_draft",
     "check_gmail_connection"},
    {"web_open", "web_read", "web_click", "web_type", "web_select", "web_press", "web_scroll"},
    {"spotify_control", "play_spotify_playlist", "music_control"},
)

# user word -> extra words to match against tool names/descriptions
SYNONYMS = {
    "text": ("imessage", "message"), "texts": ("imessage", "message"), "sms": ("imessage",),
    "imessage": ("imessage", "message"), "imessages": ("imessage", "message"),
    "reply": ("message",),
    "meeting": ("calendar", "event"), "appointment": ("calendar", "event"),
    "schedule": ("calendar", "event"),
    "remind": ("reminders",), "reminder": ("reminders",), "todo": ("reminders",),
    "email": ("gmail", "draft"), "mail": ("gmail", "draft"), "inbox": ("gmail", "unread"),
    "song": ("music", "spotify"), "play": ("music", "spotify"),
    "folder": ("directory", "file"), "screenshot": ("capture", "screen"),
    "search": ("web", "search"), "weather": ("weather",), "volume": ("volume",),
}

_STOP = set("""a an the and or of to in on at for with from by is are was be it this that these those
me my i you your we our can could would should will please just then also about into out up down all any
some more most new use using used make made get got do does did have has had not no yes if so as""".split())


def est_tokens(value):
    """Cheap token estimate: ~4 characters per token."""
    if isinstance(value, str):
        return len(value) // 4 + 1
    return len(json.dumps(value, default=str, ensure_ascii=False)) // 4 + 1


def _msg_text(m):
    """Text of a chat message that may be a dict OR an SDK message object."""
    if isinstance(m, dict):
        content, calls = m.get("content"), m.get("tool_calls")
    else:
        content, calls = getattr(m, "content", None), getattr(m, "tool_calls", None)
    text = content if isinstance(content, str) else json.dumps(content or "", default=str)
    for call in calls or []:
        try:
            fn = call["function"] if isinstance(call, dict) else call.function
            name = fn["name"] if isinstance(fn, dict) else fn.name
            args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            text += f" {name} {args}"
        except Exception:
            text += str(call)
    return text


def est_messages(messages):
    return sum(len(_msg_text(m)) for m in messages) // 4 + len(messages) * 4


# --------------------------------------------------------------------------
# Tool relevance
# --------------------------------------------------------------------------

def _name(item):
    return ((item.get("function") or {}).get("name")) or ""


def _words(text, vocab):
    words = {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in _STOP and len(w) > 1}
    out = set(words)
    out |= {w + "s" for w in words}                                    # note -> notes
    out |= {w[:-1] for w in words if w.endswith("s") and len(w) > 3}   # messages -> message
    for w in words:
        out.update(SYNONYMS.get(w, ()))
        # forgive typos ("calandar" -> "calendar")
        if len(w) >= 5 and w not in vocab:
            out.update(difflib.get_close_matches(w, vocab, n=1, cutoff=0.8))
    return out


def _vocab(schema):
    vocab = set()
    for item in schema:
        vocab.update(_name(item).lower().split("_"))
    return sorted(v for v in vocab if len(v) >= 5)


def select_tools(schema, *texts, limit=WORKER_TOOL_LIMIT, always=CORE_TOOLS, exclude=()):
    """Return the tool schemas most relevant to `texts` (user request, plan, ...).

    Scoring: tool-name word match counts 3x, description word match 1x. Words that
    show up in many descriptions ("file", "create") are ignored so they cannot
    drag in unrelated tools. Siblings of a strongly matched tool come along.
    """
    available = {_name(t) for t in schema}
    pool = [t for t in schema
            if _name(t) not in exclude and DEPRECATED.get(_name(t)) not in available]
    vocab = _vocab(pool)
    words = _words(" ".join(texts), vocab)

    desc_tokens = {}
    doc_freq = {}
    for t in pool:
        toks = set(re.findall(r"[a-z]+", ((t.get("function") or {}).get("description") or "").lower()))
        toks -= _STOP
        desc_tokens[_name(t)] = toks
        for tok in toks:
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    common = {tok for tok, n in doc_freq.items() if n > max(6, len(pool) * 0.06)}
    name_freq = {}
    for t in pool:
        for tok in set(_name(t).lower().split("_")):
            name_freq[tok] = name_freq.get(tok, 0) + 1

    scored = []
    for t in pool:
        name = _name(t)
        name_hits = words & set(name.lower().split("_"))
        desc_hits = (words & desc_tokens[name]) - common
        # distinctive name words (calendar, imessage) count 3; verbs shared by many tools
        # (list, create, get, code) count 1 so "create a note" does not pull in every create_*
        score = sum(3 if name_freq.get(w, 0) <= 14 else 1 for w in name_hits) + len(desc_hits)
        if score >= 2:
            scored.append((score, bool(name_hits), name, t))
    scored.sort(key=lambda s: (-s[0], s[2]))

    chosen, names = [], set()

    def add(t):
        n = _name(t)
        if n not in names and len(chosen) < limit + len(always):
            names.add(n)
            chosen.append(t)

    by_name = {_name(t): t for t in pool}
    for n in always:
        if n in by_name:
            add(by_name[n])
    picked = 0
    for score, strong, name, t in scored:
        if picked >= limit:
            break
        before = len(chosen)
        add(t)
        picked += len(chosen) - before
        if strong:  # bring along the siblings (e.g. lookup_contact_number with send_imessage)
            for fam in FAMILIES:
                if name in fam:
                    for sib in sorted(fam):
                        if sib in by_name and picked < limit:
                            before = len(chosen)
                            add(by_name[sib])
                            picked += len(chosen) - before
    return chosen


FIND_TOOLS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_tools",
        "description": "Load more tools by keyword when none of your current tools fit "
                       "(e.g. 'slack', 'spreadsheet', 'weather'). Returns the names it loaded.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "What you need to do."}},
                       "required": ["query"]},
    },
}


def with_find_tools(tools):
    return list(tools) + [FIND_TOOLS_SCHEMA]


def tool_signature(item):
    fn = item.get("function") or {}
    params = fn.get("parameters") or {}
    props = list((params.get("properties") or {}).keys())
    required = set(params.get("required") or [])
    args = ", ".join(p if p in required else p + "?" for p in props)
    return f"{fn.get('name')}({args})"


def tools_note(tools):
    """One short system note so the Manager plans with real tool names."""
    sigs = [tool_signature(t) for t in tools if _name(t) not in CORE_TOOLS]
    if not sigs:
        return None
    return ("Tools most relevant to this request (name the exact tool in each plan step; "
            "never plan AppleScript/osascript or shell commands for Notes, Calendar, Reminders, "
            "Messages or Mail): " + "; ".join(sigs))


# --------------------------------------------------------------------------
# Keep tool output small
# --------------------------------------------------------------------------

def trim_result(text, limit=RESULT_TOKEN_LIMIT):
    text = str(text)
    max_chars = limit * 4
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.7)
    tail = max_chars - head
    return f"{text[:head]}\n...[{len(text) - max_chars} characters trimmed]...\n{text[-tail:]}"


def shrink_old_results(messages, keep_last=2, limit=300):
    """Squeeze older tool outputs in an action history (dicts only)."""
    tool_idx = [i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "tool"]
    for i in tool_idx[:-keep_last] if keep_last else tool_idx:
        messages[i]["content"] = trim_result(messages[i].get("content", ""), limit)


def fits_budget(messages, tools, used, cap=TURN_TOKEN_CAP):
    """True if sending this request keeps the whole turn under the cap."""
    return used + est_messages(messages) + est_tokens(tools) <= cap


# --------------------------------------------------------------------------
# Chat compaction
# --------------------------------------------------------------------------

_SUMMARY_CACHE = {}   # conversation_id -> {"count": messages already summarized, "text": summary}

SUMMARY_PROMPT = (
    "You compress a chat between a user and their assistant Buddy. Update the running summary "
    "below with the new messages. Keep it under 180 words. Keep: what the user wants, names and "
    "aliases (e.g. 'mom' = contact 'Mama'), preferences, decisions, results of finished tasks, "
    "anything still pending. Drop greetings and small talk. Output only the summary.")


def _flatten(messages):
    lines = []
    for m in messages:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "?")
        lines.append(f"{role}: {_msg_text(m)[:1200]}")
    return "\n".join(lines)


def default_summarizer(prompt_text):
    from models import run_manager_step, message_text
    from core.model_config import load_model_config
    response = run_manager_step(load_model_config()["chat"],
                                [{"role": "system", "content": SUMMARY_PROMPT},
                                 {"role": "user", "content": prompt_text}], 350)
    return message_text(response.choices[0].message).strip()


def compact_history(history, conversation_id=None, summarize=None, force=False):
    """history = [system_prompt, *messages]. Returns (new_history, note_or_None).

    Old messages become one short summary message; the last KEEP_RECENT stay verbatim.
    The summary is cached per conversation and only extended, never rebuilt.
    """
    has_sys = bool(history) and isinstance(history[0], dict) and history[0].get("role") == "system"
    head, body = (history[:1], history[1:]) if has_sys else ([], list(history))
    if len(body) <= KEEP_RECENT:
        return history, None
    if not force and est_messages(body) < HISTORY_COMPACT_AT:
        return history, None

    old, recent = body[:-KEEP_RECENT], body[-KEEP_RECENT:]
    cached = _SUMMARY_CACHE.get(conversation_id) if conversation_id is not None else None
    done = cached["count"] if cached and cached["count"] <= len(old) else 0
    prior = cached["text"] if done else ""
    fresh = old[done:]
    before = est_messages(body)

    summarize = summarize or default_summarizer
    try:
        text = summarize(f"Running summary so far:\n{prior or '(none)'}\n\nNew messages:\n{_flatten(fresh)}")
        if not text:
            raise ValueError("empty summary")
    except Exception:
        text = (prior + "\n" if prior else "") + "(Older messages were dropped to save tokens.)"
    if conversation_id is not None:
        _SUMMARY_CACHE[conversation_id] = {"count": len(old), "text": text}

    summary_msg = {"role": "system", "content": "Summary of earlier conversation:\n" + text}
    new_history = head + [summary_msg] + recent
    saved = max(0, before - est_messages(new_history[len(head):]))
    return new_history, f"Compacted {len(old)} older messages (~{saved} tokens saved)."
