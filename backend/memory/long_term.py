"""
memory/long_term.py
-------------------
Persistent long-term memory using SQLite.
Conversations survive server restarts and can be searched by session or keyword.

Tables:
  sessions      — one row per session_id (metadata + summary)
  messages      — every message ever sent / received
  messages_fts  — FTS5 virtual table for full-text keyword search
"""

import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).parent.parent / "memory_store" / "long_term.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _sanitize_fts(query: str) -> str:
    """
    Sanitize a raw user query for safe use in FTS5 MATCH expressions.

    FTS5 treats backslashes, quotes, parentheses, AND/OR/NOT etc. as syntax.
    Passing them raw causes 'Stream error: fts5: syntax error near X'.

    Fix: strip all non-word characters, then wrap each token in double-quotes
    so FTS5 treats them as plain literal matches instead of operators.
    """
    cleaned = re.sub(r'[^\w\s\-]', ' ', query)
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens)


def _init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id     TEXT    PRIMARY KEY,
            persona        TEXT    DEFAULT 'researcher',
            model_id       TEXT    DEFAULT '',
            created_at     TEXT    NOT NULL,
            updated_at     TEXT    NOT NULL,
            summary        TEXT    DEFAULT '',
            message_count  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL
                            REFERENCES sessions(session_id) ON DELETE CASCADE,
            role        TEXT    NOT NULL CHECK(role IN ('user','assistant','system')),
            content     TEXT    NOT NULL,
            timestamp   TEXT    NOT NULL,
            metadata    TEXT    DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, id);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(
                content,
                session_id UNINDEXED
            );
    """)
    conn.commit()
    conn.close()


_init_db()


def save_message(
    session_id: str,
    role: str,
    content: str,
    persona: str = "researcher",
    model_id: str = "",
    metadata: Optional[dict] = None,
) -> None:
    if not content or not content.strip():
        return

    now       = datetime.utcnow().isoformat()
    meta_json = json.dumps(metadata or {})

    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO sessions
                (session_id, persona, model_id, created_at, updated_at, message_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at    = excluded.updated_at,
                persona       = excluded.persona,
                model_id      = excluded.model_id,
                message_count = message_count + 1
        """, (session_id, persona, model_id, now, now))

        cur = conn.execute("""
            INSERT INTO messages (session_id, role, content, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, now, meta_json))

        conn.execute("""
            INSERT INTO messages_fts (rowid, content, session_id)
            VALUES (?, ?, ?)
        """, (cur.lastrowid, content, session_id))

        conn.commit()
    finally:
        conn.close()


def get_session_history(
    session_id: str,
    limit: int = 50,
    as_openai_format: bool = True,
) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT role, content, timestamp, metadata
            FROM   messages
            WHERE  session_id = ?
            ORDER  BY id DESC
            LIMIT  ?
        """, (session_id, limit)).fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))

    if as_openai_format:
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    return [
        {
            "role":      r["role"],
            "content":   r["content"],
            "timestamp": r["timestamp"],
            "metadata":  json.loads(r["metadata"]),
        }
        for r in rows
    ]


def search_history(
    query: str,
    session_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    safe_query = _sanitize_fts(query)
    conn = _get_conn()
    try:
        if session_id:
            rows = conn.execute("""
                SELECT m.session_id, m.role, m.content, m.timestamp
                FROM   messages_fts f
                JOIN   messages m ON m.id = f.rowid
                WHERE  messages_fts MATCH ?
                  AND  f.session_id = ?
                ORDER  BY rank
                LIMIT  ?
            """, (safe_query, session_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT m.session_id, m.role, m.content, m.timestamp
                FROM   messages_fts f
                JOIN   messages m ON m.id = f.rowid
                WHERE  messages_fts MATCH ?
                ORDER  BY rank
                LIMIT  ?
            """, (safe_query, limit)).fetchall()
    finally:
        conn.close()

    return [
        {
            "session_id": r["session_id"],
            "role":       r["role"],
            "content":    r["content"],
            "timestamp":  r["timestamp"],
        }
        for r in rows
    ]


def list_sessions(limit: int = 20) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT session_id, persona, model_id,
                   created_at, updated_at, message_count, summary
            FROM   sessions
            ORDER  BY updated_at DESC
            LIMIT  ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


def delete_session(session_id: str) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def save_session_summary(session_id: str, summary: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("""
            UPDATE sessions SET summary = ?, updated_at = ?
            WHERE session_id = ?
        """, (summary, datetime.utcnow().isoformat(), session_id))
        conn.commit()
    finally:
        conn.close()


def get_session_summary(session_id: str) -> Optional[str]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT summary FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["summary"] if row else None
    finally:
        conn.close()


def get_cross_session_context(
    query: str,
    current_session_id: str,
    limit: int = 5,
) -> list[dict]:
    safe_query = _sanitize_fts(query)
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT m.session_id, m.role, m.content, m.timestamp
            FROM   messages_fts f
            JOIN   messages m ON m.id = f.rowid
            WHERE  messages_fts MATCH ?
              AND  f.session_id != ?
              AND  m.role = 'assistant'
            ORDER  BY rank
            LIMIT  ?
        """, (safe_query, current_session_id, limit)).fetchall()
    finally:
        conn.close()

    return [
        {
            "session_id": r["session_id"],
            "role":       r["role"],
            "content":    r["content"][:500],
            "timestamp":  r["timestamp"],
        }
        for r in rows
    ]


def get_session_stats(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT session_id, persona, model_id,
                   created_at, updated_at, message_count, summary
            FROM   sessions WHERE session_id = ?
        """, (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def prune_old_sessions(keep_latest: int = 100) -> int:
    conn = _get_conn()
    try:
        to_delete = conn.execute("""
            SELECT session_id FROM sessions
            ORDER BY updated_at DESC
            LIMIT -1 OFFSET ?
        """, (keep_latest,)).fetchall()

        deleted = 0
        for row in to_delete:
            sid = row["session_id"]
            conn.execute("DELETE FROM sessions     WHERE session_id = ?", (sid,))
            conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (sid,))
            deleted += 1

        conn.commit()
        return deleted
    finally:
        conn.close()