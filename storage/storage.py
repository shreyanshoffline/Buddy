"""
Local persistence for Buddy — chat history + user profile/settings.
SQLite, single file, lives next to the app (~/Library/Application Support/Buddy/buddy.db on macOS).
This is app-level memory: which conversations exist, what was said.
It is NOT the same as message_history passed to the model each turn.
"""

import sqlite3
import os
import json
import time
from pathlib import Path
from contextlib import contextmanager
import re
MAX_FILE_CHARS = 200_000   # doubled — handle larger files
CHUNK_CHARS = 3000         # bigger chunks = more context per retrieval hit
CHUNK_OVERLAP = 400        # more overlap = less chance of splitting mid-thought

# --- Where the DB lives ---
def _default_db_path():
    # Use the project directory for the database file
    project_root = Path(__file__).parent.parent
    db_file = project_root / "buddy.db"
    return str(db_file)

_DB_PATH = None

def get_db_path():
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = os.environ.get("BUDDY_DB_PATH", _default_db_path())
    return _DB_PATH


@contextmanager
def _connect():
    db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'New chat',
            is_private INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,               -- user / assistant / system / tool
            content TEXT,
            tool_calls TEXT,                  -- JSON-serialized OpenAI-style tool_calls, nullable
            tool_call_id TEXT,                -- for role='tool' messages
            metadata TEXT,                    -- JSON: Dev Chamber info (plan_text/tools_used/stats), NOT model tool_calls
            created_at REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS task_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_summary TEXT NOT NULL,     -- short description of what was asked
            plan_text TEXT,                 -- the plan that worked
            outcome_summary TEXT,           -- finish_task summary / result
            keywords TEXT,                  -- space-joined lowercase keywords, precomputed for cheap matching
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_task_memories_created ON task_memories(created_at);

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),  -- single row
            name TEXT,
            age INTEGER,
            bio TEXT,                          -- the "3 sentences about yourself"
            email TEXT,
            theme_color TEXT DEFAULT 'blue',
            dark_mode INTEGER DEFAULT 0,
            subscription_tier TEXT DEFAULT 'free',
            byo_api_key TEXT
        );
        """)
        # migration: add email column for older dbs created before this existed
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(user_profile)")]
        if "email" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN email TEXT")
        # migration: add is_private column for older dbs
        conv_cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)")]
        if "is_private" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0")
        # migration: add feedback column for older dbs
        msg_cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)")]
        if "feedback" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN feedback TEXT")
        # Ensure the single profile row exists
        conn.execute("""
            INSERT OR IGNORE INTO user_profile (id, name, theme_color, dark_mode, subscription_tier)
            VALUES (1, NULL, 'blue', 0, 'free')
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                message_id INTEGER,
                name TEXT NOT NULL,
                extension TEXT,
                path TEXT,
                extracted_text TEXT,
                char_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attachment_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attachment_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)


# --- Conversations ---

def create_conversation(title="New chat"):
    now = time.time()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now)
        )
        return cur.lastrowid


def touch_conversation(conversation_id, title=None):
    with _connect() as conn:
        if title:
            conn.execute(
                "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
                (time.time(), title, conversation_id)
            )
        else:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (time.time(), conversation_id)
            )


def list_conversations(limit=30):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at, is_private FROM conversations "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def search_conversations(query, limit=50):
    """Matches on chat title OR any message content in the chat."""
    like = f"%{query}%"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.is_private
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.title LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC LIMIT ?
            """,
            (like, like, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def set_conversation_private(conversation_id, is_private):
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET is_private = ? WHERE id = ?",
            (1 if is_private else 0, conversation_id)
        )


def get_most_recent_conversation_id():
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM conversations ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None


def get_conversation_title(conversation_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return row["title"] if row else None


def get_conversation_is_private(conversation_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT is_private FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return bool(row["is_private"]) if row else False


def delete_conversation(conversation_id):
    with _connect() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


# --- Messages ---

def save_message(conversation_id, role, content=None, tool_calls=None, tool_call_id=None, metadata=None):
    """
    tool_calls: real OpenAI-style tool_calls list, only used when replaying
                model context (see load_messages).
    metadata:   Dev Chamber display info (plan_text/tools_used/stats) — never
                sent back to the model, purely for the UI.
    """
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls, tool_call_id, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id, role, content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                json.dumps(metadata) if metadata else None,
                time.time()
            )
        )
        message_id = cur.lastrowid
    touch_conversation(conversation_id)
    return message_id


def set_message_feedback(message_id, feedback):
    """feedback: 'like' / 'dislike' / None (clears it)."""
    with _connect() as conn:
        conn.execute("UPDATE messages SET feedback = ? WHERE id = ?", (feedback, message_id))


def load_messages(conversation_id):
    """Returns messages in the OpenAI-style dict format core.py already uses.
    `metadata` (Dev Chamber info) is intentionally NOT included here — it's
    UI-only and should never be replayed into the model's context."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id FROM messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()

    history = []
    for r in rows:
        msg = {"role": r["role"], "content": r["content"]}
        if r["tool_calls"]:
            msg["tool_calls"] = json.loads(r["tool_calls"])
        if r["tool_call_id"]:
            msg["tool_call_id"] = r["tool_call_id"]
        history.append(msg)
    return history


def load_messages_with_metadata(conversation_id):
    """Same as load_messages but includes id/feedback/parsed metadata — use
    this when rebuilding the GUI's chat bubbles, not for model context."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, tool_calls, tool_call_id, metadata, feedback FROM messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()

    history = []
    for r in rows:
        msg = {"id": r["id"], "role": r["role"], "content": r["content"], "feedback": r["feedback"]}
        if r["tool_calls"]:
            msg["tool_calls"] = json.loads(r["tool_calls"])
        if r["tool_call_id"]:
            msg["tool_call_id"] = r["tool_call_id"]
        if r["metadata"]:
            msg["metadata"] = json.loads(r["metadata"])
        history.append(msg)
    return history


def auto_title_from_first_message(text, max_len=40):
    """Dumb fallback: used only if the LLM title call (see core.py) fails."""
    text = text.strip().replace("\n", " ")
    return text[:max_len] + ("…" if len(text) > max_len else "")


# --- User profile / settings ---

def get_profile():
    with _connect() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
        return dict(row) if row else {}


def update_profile(**fields):
    """update_profile(name='Shrey', age=14, theme_color='purple', dark_mode=True)"""
    if not fields:
        return
    allowed = {"name", "age", "bio", "email", "theme_color", "dark_mode", "subscription_tier", "byo_api_key"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "dark_mode" in fields:
        fields["dark_mode"] = 1 if fields["dark_mode"] else 0
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [1]
    with _connect() as conn:
        conn.execute(f"UPDATE user_profile SET {set_clause} WHERE id = ?", values)

# --- Long-term task memory (POC: keyword overlap, no embeddings yet) ---

_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "for", "in", "on", "with", "my",
    "me", "is", "it", "this", "that", "please", "can", "you", "i", "do",
    "make", "file", "up", "at", "as", "be", "get", "into"
}

def _extract_keywords(text):
    words = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return sorted(set(w for w in words if len(w) > 2 and w not in _STOPWORDS))


def save_task_memory(task_summary, plan_text, outcome_summary):
    keywords = " ".join(_extract_keywords(f"{task_summary} {plan_text or ''}"))
    with _connect() as conn:
        conn.execute(
            "INSERT INTO task_memories (task_summary, plan_text, outcome_summary, keywords, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_summary, plan_text, outcome_summary, keywords, time.time())
        )


def find_similar_task_memories(query_text, limit=2, min_overlap=2):
    """Cheap keyword-overlap retrieval. Not real semantic search — good
    enough for a POC. Returns best-matching past tasks, most relevant first."""
    query_keywords = set(_extract_keywords(query_text))
    if not query_keywords:
        return []

    with _connect() as conn:
        rows = conn.execute(
            "SELECT task_summary, plan_text, outcome_summary, keywords, created_at "
            "FROM task_memories ORDER BY created_at DESC LIMIT 200"  # cap scan for POC
        ).fetchall()

    scored = []
    for r in rows:
        row_keywords = set(r["keywords"].split()) if r["keywords"] else set()
        overlap = len(query_keywords & row_keywords)
        if overlap >= min_overlap:
            scored.append((overlap, dict(r)))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [mem for _, mem in scored[:limit]]

_RAG_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "for", "in", "on", "with", "my",
    "me", "is", "it", "this", "that", "can", "you", "i", "do", "be", "get",
    "at", "as", "or", "if", "by", "we", "he", "she", "they", "are", "was",
    "were", "has", "have", "had", "not", "but", "from", "up", "out", "so",
    "its", "into", "than", "then", "will", "would", "could", "should", "also"
}

def _tokenize(text):
    tokens = set(re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower()))
    return tokens - _RAG_STOPWORDS


def chunk_text(text, chunk_size=CHUNK_CHARS, overlap=CHUNK_OVERLAP):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def save_conversation_attachments(conversation_id, message_id, files):
    """files = [{name, extension, contents, path}, ...]"""
    conn = sqlite3.connect(_DB_PATH)
    saved_ids = []
    now = time.time()
    for item in files or []:
        text = (item.get("contents") or "")[:MAX_FILE_CHARS]
        cur = conn.execute(
            """
            INSERT INTO attachments
                (conversation_id, message_id, name, extension, path, extracted_text, char_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                message_id,
                item.get("name") or "untitled",
                item.get("extension") or "",
                item.get("path") or "",
                text,
                len(text),
                now,
            ),
        )
        attachment_id = cur.lastrowid
        for i, chunk in enumerate(chunk_text(text)):
            conn.execute(
                """
                INSERT INTO attachment_chunks
                    (attachment_id, conversation_id, chunk_index, content)
                VALUES (?, ?, ?, ?)
                """,
                (attachment_id, conversation_id, i, chunk),
            )
        saved_ids.append(attachment_id)
    conn.commit()
    conn.close()
    return saved_ids


def latest_user_message_id(conversation_id):
    conn = sqlite3.connect(_DB_PATH)
    row = conn.execute(
        """
        SELECT id FROM messages
        WHERE conversation_id = ? AND role = 'user'
        ORDER BY id DESC LIMIT 1
        """,
        (conversation_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def find_relevant_chunks(conversation_id, query, limit=8):
    """
    Improved retrieval:
    - TF-IDF-style scoring: tokens that appear in few chunks score higher
    - Diversity: won't return 5 consecutive chunks from same file when another
      file is more relevant
    - Falls back to first N chunks if nothing scores
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.id, c.attachment_id, c.chunk_index, c.content, a.name
        FROM attachment_chunks c
        JOIN attachments a ON a.id = c.attachment_id
        WHERE c.conversation_id = ?
        ORDER BY a.id DESC, c.chunk_index ASC
        """,
        (conversation_id,),
    ).fetchall()
    conn.close()

    chunks = [dict(r) for r in rows]
    if not chunks:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return chunks[:limit]

    total = len(chunks)

    # Build IDF: how many chunks contain each token
    doc_freq = {}
    for chunk in chunks:
        for tok in _tokenize(chunk["content"]):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1

    import math
    def idf(tok):
        df = doc_freq.get(tok, 0)
        return math.log((total + 1) / (df + 1)) + 1  # smoothed IDF

    def score_chunk(chunk):
        chunk_tokens = _tokenize(chunk["content"])
        if not chunk_tokens:
            return 0.0
        # TF * IDF for each query token found in chunk
        score = 0.0
        for tok in query_tokens:
            if tok in chunk_tokens:
                tf = 1.0  # binary TF (present/absent) — simple but effective
                score += tf * idf(tok)
        # Bonus: reward chunks where query tokens are dense (hit ratio)
        hit_ratio = len(query_tokens & chunk_tokens) / len(query_tokens)
        score *= (1.0 + hit_ratio)
        return score

    scored = [(score_chunk(c), c) for c in chunks]
    scored.sort(key=lambda x: -x[0])

    # Diversity: pick top chunks but allow at most 3 per attachment_id
    picked = []
    per_file_count = {}
    MAX_PER_FILE = 3
    for score, chunk in scored:
        if score <= 0:
            break
        aid = chunk["attachment_id"]
        if per_file_count.get(aid, 0) >= MAX_PER_FILE:
            continue
        picked.append(chunk)
        per_file_count[aid] = per_file_count.get(aid, 0) + 1
        if len(picked) >= limit:
            break

    # Fallback: if nothing scored, return first N chunks ordered by file/position
    if not picked:
        picked = chunks[:limit]

    # Re-sort picked by (attachment_id, chunk_index) so context reads in order
    picked.sort(key=lambda c: (c["attachment_id"], c["chunk_index"]))
    return picked