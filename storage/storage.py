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

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),  -- single row
            name TEXT,
            age INTEGER,
            bio TEXT,                          -- the "3 sentences about yourself"
            theme_color TEXT DEFAULT 'blue',
            dark_mode INTEGER DEFAULT 0,
            subscription_tier TEXT DEFAULT 'free',
            byo_api_key TEXT
        );
        """)
        # Ensure the single profile row exists
        conn.execute("""
            INSERT OR IGNORE INTO user_profile (id, name, theme_color, dark_mode, subscription_tier)
            VALUES (1, NULL, 'blue', 0, 'free')
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
            "SELECT id, title, created_at, updated_at FROM conversations "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


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
        conn.execute(
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
    touch_conversation(conversation_id)


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
    """Same as load_messages but includes parsed `metadata` — use this when
    rebuilding the GUI's chat bubbles on app relaunch, not for model context."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, metadata FROM messages "
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
    allowed = {"name", "age", "bio", "theme_color", "dark_mode", "subscription_tier", "byo_api_key"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "dark_mode" in fields:
        fields["dark_mode"] = 1 if fields["dark_mode"] else 0
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [1]
    with _connect() as conn:
        conn.execute(f"UPDATE user_profile SET {set_clause} WHERE id = ?", values)