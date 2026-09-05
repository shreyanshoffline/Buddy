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
import math
import hashlib
from pathlib import Path
from contextlib import contextmanager
import re

import models


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _safe_embed(texts):
    """Best-effort embedding — returns None on any failure so callers can
    fall back to keyword-based retrieval instead of breaking the feature."""
    try:
        return models.embed_texts(texts)
    except Exception:
        return None
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
            is_favorite INTEGER NOT NULL DEFAULT 0,
            is_archived INTEGER NOT NULL DEFAULT 0,
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
            embedding TEXT,                 -- JSON-encoded vector for semantic search
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
            buddy_user_id TEXT,
            byo_api_key TEXT,
            privacy_pin_hash TEXT,             -- sha256 hex digest; NULL = no PIN set
            has_seen_intro_tip INTEGER DEFAULT 0,
            favorite_apps TEXT,                -- comma-separated, user's own "usual apps"
            quick_links TEXT                   -- comma-separated "Name: URL" pairs
            ,auth_provider TEXT
            ,hackclub_verified INTEGER DEFAULT 0
            ,hackclub_verification_status TEXT
            ,onboarding_complete INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'image',
            content TEXT NOT NULL,
            conversation_id INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
        );
        """)
        # migration: add email column for older dbs created before this existed
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(user_profile)")]
        if "email" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN email TEXT")
        if "privacy_pin_hash" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN privacy_pin_hash TEXT")
        if "has_seen_intro_tip" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN has_seen_intro_tip INTEGER DEFAULT 0")
        if "favorite_apps" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN favorite_apps TEXT")
        if "quick_links" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN quick_links TEXT")
        if "buddy_user_id" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN buddy_user_id TEXT")
        if "auth_provider" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN auth_provider TEXT")
        if "hackclub_verified" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN hackclub_verified INTEGER DEFAULT 0")
        if "hackclub_verification_status" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN hackclub_verification_status TEXT")
        if "onboarding_complete" not in cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN onboarding_complete INTEGER DEFAULT 0")
        # migration: add is_private column for older dbs
        conv_cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)")]
        if "is_private" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0")
        conv_cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)")]
        if "is_favorite" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        if "is_archived" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
        # migration: add feedback column for older dbs
        msg_cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)")]
        if "feedback" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN feedback TEXT")
        mem_cols = [r["name"] for r in conn.execute("PRAGMA table_info(task_memories)")]
        if "embedding" not in mem_cols:
            conn.execute("ALTER TABLE task_memories ADD COLUMN embedding TEXT")
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
                embedding TEXT,             -- JSON-encoded vector for semantic search
                FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        # migration: embedding column for attachment_chunks — must run after
        # the CREATE TABLE above, since older dbs already have this table
        # but not the column, while brand-new dbs get it from CREATE TABLE directly.
        chunk_cols = [r["name"] for r in conn.execute("PRAGMA table_info(attachment_chunks)")]
        if "embedding" not in chunk_cols:
            conn.execute("ALTER TABLE attachment_chunks ADD COLUMN embedding TEXT")


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


def list_conversations(limit=30, exclude_private=False, filter_mode="all"):
    """filter_mode: 'all' (excludes archived), 'favorites' (favorited,
    non-archived), or 'archived' (archived only)."""
    with _connect() as conn:
        query = "SELECT id, title, created_at, updated_at, is_private, is_favorite, is_archived FROM conversations WHERE 1=1 "
        if exclude_private:
            query += "AND is_private = 0 "
        if filter_mode == "favorites":
            query += "AND is_favorite = 1 AND is_archived = 0 "
        elif filter_mode == "archived":
            query += "AND is_archived = 1 "
        else:
            query += "AND is_archived = 0 "
        query += "ORDER BY updated_at DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]


def set_conversation_favorite(conversation_id, is_favorite):
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET is_favorite = ? WHERE id = ?",
            (1 if is_favorite else 0, conversation_id)
        )


def set_conversation_archived(conversation_id, is_archived):
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET is_archived = ? WHERE id = ?",
            (1 if is_archived else 0, conversation_id)
        )


def search_conversations(query, limit=50, filter_mode="all"):
    """Matches on chat title OR any message content in the chat."""
    like = f"%{query}%"
    with _connect() as conn:
        sql = """
            SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.is_private, c.is_favorite, c.is_archived
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE (c.title LIKE ? OR m.content LIKE ?) """
        if filter_mode == "favorites":
            sql += "AND c.is_favorite = 1 AND c.is_archived = 0 "
        elif filter_mode == "archived":
            sql += "AND c.is_archived = 1 "
        else:
            sql += "AND c.is_archived = 0 "
        sql += "ORDER BY c.updated_at DESC LIMIT ?"
        rows = conn.execute(sql, (like, like, limit)).fetchall()
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


def save_artifact(title, content, kind="image", conversation_id=None):
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO artifacts (title, kind, content, conversation_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (title or "Untitled artifact", kind, content, conversation_id, time.time()),
        )
        return cur.lastrowid


def list_artifacts(limit=100):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, kind, content, conversation_id, created_at FROM artifacts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def delete_artifact(artifact_id):
    with _connect() as conn:
        conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))


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
        profile = dict(row) if row else {}
        # Never leak the raw hash to callers — presence is exposed via has_privacy_pin()
        profile.pop("privacy_pin_hash", None)
        return profile


def get_or_create_buddy_user_id():
    """Stable anonymous ID identifying this Buddy install to the billing
    backend — generated once, stored locally, never tied to real identity
    beyond what Stripe Checkout itself collects (email, card)."""
    import uuid
    profile = get_profile()
    uid = profile.get("buddy_user_id")
    if uid:
        return uid
    uid = uuid.uuid4().hex
    update_profile(buddy_user_id=uid)
    return uid


def update_profile(**fields):
    """update_profile(name='Alex', age=14, theme_color='purple', dark_mode=True)"""
    if not fields:
        return
    allowed = {
        "name", "age", "bio", "email", "theme_color", "dark_mode",
        "subscription_tier", "byo_api_key", "has_seen_intro_tip",
        "favorite_apps", "quick_links", "buddy_user_id",
        "auth_provider", "hackclub_verified", "hackclub_verification_status",
        "onboarding_complete",
    }
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "dark_mode" in fields:
        fields["dark_mode"] = 1 if fields["dark_mode"] else 0
    if "has_seen_intro_tip" in fields:
        fields["has_seen_intro_tip"] = 1 if fields["has_seen_intro_tip"] else 0
    if "hackclub_verified" in fields:
        fields["hackclub_verified"] = 1 if fields["hackclub_verified"] else 0
    if "onboarding_complete" in fields:
        fields["onboarding_complete"] = 1 if fields["onboarding_complete"] else 0
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [1]
    with _connect() as conn:
        conn.execute(f"UPDATE user_profile SET {set_clause} WHERE id = ?", values)


def _hash_pin(pin):
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def set_privacy_pin(pin):
    """Set (or clear, if pin is falsy) the PIN required to open private chats."""
    pin_hash = _hash_pin(pin) if pin else None
    with _connect() as conn:
        conn.execute("UPDATE user_profile SET privacy_pin_hash = ? WHERE id = 1", (pin_hash,))


def has_privacy_pin():
    with _connect() as conn:
        row = conn.execute("SELECT privacy_pin_hash FROM user_profile WHERE id = 1").fetchone()
        return bool(row and row["privacy_pin_hash"])


def verify_privacy_pin(pin):
    with _connect() as conn:
        row = conn.execute("SELECT privacy_pin_hash FROM user_profile WHERE id = 1").fetchone()
        if not row or not row["privacy_pin_hash"]:
            return False
        return _hash_pin(pin or "") == row["privacy_pin_hash"]

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
    embedding = _safe_embed([f"{task_summary}\n{plan_text or ''}"])
    emb_json = json.dumps(embedding[0]) if embedding else None
    with _connect() as conn:
        conn.execute(
            "INSERT INTO task_memories (task_summary, plan_text, outcome_summary, keywords, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_summary, plan_text, outcome_summary, keywords, emb_json, time.time())
        )


def find_similar_task_memories(query_text, limit=2, min_overlap=2):
    """Real vector search when memory embeddings exist, falling back to
    keyword overlap if embeddings are missing or the embed call fails."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT task_summary, plan_text, outcome_summary, keywords, embedding, created_at "
            "FROM task_memories ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
    rows = [dict(r) for r in rows]
    if not rows:
        return []

    has_all_embeddings = all(r.get("embedding") for r in rows)
    if has_all_embeddings:
        query_embedding = _safe_embed([query_text])
        if query_embedding:
            q_vec = query_embedding[0]
            scored = [(_cosine(q_vec, json.loads(r["embedding"])), r) for r in rows]
            scored.sort(key=lambda x: -x[0])
            # keep a minimal relevance floor so unrelated memories don't leak in
            return [r for score, r in scored[:limit] if score > 0.3]

    # --- Fallback: keyword overlap ---
    query_keywords = set(_extract_keywords(query_text))
    if not query_keywords:
        return []

    scored = []
    for r in rows[:200]:
        row_keywords = set(r["keywords"].split()) if r["keywords"] else set()
        overlap = len(query_keywords & row_keywords)
        if overlap >= min_overlap:
            scored.append((overlap, r))

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
        chunk_list = chunk_text(text)
        chunk_embeddings = _safe_embed(chunk_list) if chunk_list else None
        for i, chunk in enumerate(chunk_list):
            emb = chunk_embeddings[i] if chunk_embeddings else None
            conn.execute(
                """
                INSERT INTO attachment_chunks
                    (attachment_id, conversation_id, chunk_index, content, embedding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (attachment_id, conversation_id, i, chunk, json.dumps(emb) if emb else None),
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
    Real vector retrieval when chunk embeddings are available (cosine
    similarity against an embedded query), with graceful fallback to the
    TF-IDF-style scorer below if embeddings are missing or the embed call
    fails — so a flaky/unavailable embeddings endpoint never breaks RAG.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.id, c.attachment_id, c.chunk_index, c.content, c.embedding, a.name
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

    has_all_embeddings = all(c.get("embedding") for c in chunks)
    if has_all_embeddings:
        query_embedding = _safe_embed([query])
        if query_embedding:
            q_vec = query_embedding[0]
            scored = []
            for c in chunks:
                vec = json.loads(c["embedding"])
                scored.append((_cosine(q_vec, vec), c))
            scored.sort(key=lambda x: -x[0])
            picked, per_file_count = [], {}
            for score, c in scored:
                if len(picked) >= limit:
                    break
                count = per_file_count.get(c["attachment_id"], 0)
                if count >= 3:
                    continue
                picked.append(c)
                per_file_count[c["attachment_id"]] = count + 1
            if picked:
                return picked

    # --- Fallback: TF-IDF-style keyword scoring (no embeddings available) ---
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