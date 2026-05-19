"""
memory/episodic.py
------------------
Episodic memory — stores discrete, meaningful events / facts extracted from
conversations so the assistant can recall specific things the user said or
asked about, even across sessions.

Tables:
  episodes      — individual memorable events with tags + importance score
  episodes_fts  — FTS5 index for semantic-ish keyword recall
"""

import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).parent.parent / "memory_store" / "episodic.db"


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
    Strips FTS5 syntax characters and wraps tokens in double-quotes.
    Prevents 'syntax error near X' crashes on special characters.
    """
    cleaned = re.sub(r'[^\w\s\-]', ' ', query)
    tokens = cleaned.split()
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens)


def _init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS episodes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   TEXT    NOT NULL,
            event_type   TEXT    NOT NULL DEFAULT 'fact',
            summary      TEXT    NOT NULL,
            detail       TEXT    DEFAULT '',
            tags         TEXT    DEFAULT '[]',
            importance   REAL    DEFAULT 0.5,
            source_role  TEXT    DEFAULT 'user',
            created_at   TEXT    NOT NULL,
            session_date TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_episodes_session
            ON episodes(session_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_episodes_type
            ON episodes(event_type, importance DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
            USING fts5(
                summary,
                detail,
                tags,
                session_id UNINDEXED
            );
    """)
    conn.commit()
    conn.close()


_init_db()


def save_episode(
    session_id: str,
    summary: str,
    event_type: str = "fact",
    detail: str = "",
    tags: Optional[list[str]] = None,
    importance: float = 0.5,
    source_role: str = "user",
) -> int:
    if not summary or not summary.strip():
        raise ValueError("Episode summary cannot be empty.")

    importance  = max(0.0, min(1.0, importance))
    now         = datetime.utcnow().isoformat()
    today       = datetime.utcnow().strftime("%Y-%m-%d")
    tags_json   = json.dumps(tags or [])

    conn = _get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO episodes
                (session_id, event_type, summary, detail, tags,
                 importance, source_role, created_at, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, event_type, summary, detail, tags_json,
              importance, source_role, now, today))

        episode_id = cur.lastrowid

        conn.execute("""
            INSERT INTO episodes_fts (rowid, summary, detail, tags, session_id)
            VALUES (?, ?, ?, ?, ?)
        """, (episode_id, summary, detail, " ".join(tags or []), session_id))

        conn.commit()
        return episode_id
    finally:
        conn.close()


def get_episodes(
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    min_importance: float = 0.0,
    limit: int = 20,
) -> list[dict]:
    conn = _get_conn()
    try:
        conditions = ["importance >= ?"]
        params: list = [min_importance]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where = " AND ".join(conditions)
        params.append(limit)

        rows = conn.execute(f"""
            SELECT id, session_id, event_type, summary, detail, tags,
                   importance, source_role, created_at, session_date
            FROM   episodes
            WHERE  {where}
            ORDER  BY importance DESC, created_at DESC
            LIMIT  ?
        """, params).fetchall()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows]


def search_episodes(
    query: str,
    session_id: Optional[str] = None,
    limit: int = 10,
    min_importance: float = 0.0,
) -> list[dict]:
    safe_query = _sanitize_fts(query)
    conn = _get_conn()
    try:
        if session_id:
            rows = conn.execute("""
                SELECT e.id, e.session_id, e.event_type, e.summary, e.detail,
                       e.tags, e.importance, e.source_role, e.created_at, e.session_date
                FROM   episodes_fts f
                JOIN   episodes e ON e.id = f.rowid
                WHERE  episodes_fts MATCH ?
                  AND  f.session_id = ?
                  AND  e.importance >= ?
                ORDER  BY rank
                LIMIT  ?
            """, (safe_query, session_id, min_importance, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT e.id, e.session_id, e.event_type, e.summary, e.detail,
                       e.tags, e.importance, e.source_role, e.created_at, e.session_date
                FROM   episodes_fts f
                JOIN   episodes e ON e.id = f.rowid
                WHERE  episodes_fts MATCH ?
                  AND  e.importance >= ?
                ORDER  BY rank
                LIMIT  ?
            """, (safe_query, min_importance, limit)).fetchall()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows]


def get_episode_by_id(episode_id: int) -> Optional[dict]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def update_episode_importance(episode_id: int, importance: float) -> bool:
    importance = max(0.0, min(1.0, importance))
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE episodes SET importance = ? WHERE id = ?",
            (importance, episode_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_episode(episode_id: int) -> bool:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
        conn.execute("DELETE FROM episodes_fts WHERE rowid = ?", (episode_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_session_episodes(session_id: str) -> int:
    conn = _get_conn()
    try:
        ids = [
            r["id"] for r in
            conn.execute(
                "SELECT id FROM episodes WHERE session_id = ?", (session_id,)
            ).fetchall()
        ]
        if not ids:
            return 0
        conn.execute("DELETE FROM episodes WHERE session_id = ?", (session_id,))
        for eid in ids:
            conn.execute("DELETE FROM episodes_fts WHERE rowid = ?", (eid,))
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def get_user_profile(limit: int = 30) -> list[dict]:
    """
    Return the most important fact/preference episodes across ALL sessions.
    Only includes importance >= 0.6 to avoid injecting noise into the prompt.
    """
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT id, session_id, event_type, summary, detail, tags,
                   importance, source_role, created_at, session_date
            FROM   episodes
            WHERE  event_type IN ('fact', 'preference')
              AND  importance >= 0.6
            ORDER  BY importance DESC, created_at DESC
            LIMIT  ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows]


def build_memory_context(
    query: str,
    current_session_id: str,
    max_episodes: int = 6,
    min_importance: float = 0.6,
) -> str:
    """
    Build a compact memory-context string to inject into the system prompt.
    Only includes episodes with importance >= 0.6 (filters out junk/noise).
    """
    relevant = search_episodes(query, limit=max_episodes, min_importance=min_importance)

    profile = get_user_profile(limit=10)
    seen_ids = {e["id"] for e in relevant}
    for ep in profile:
        if ep["id"] not in seen_ids and len(relevant) < max_episodes:
            relevant.append(ep)
            seen_ids.add(ep["id"])

    if not relevant:
        return ""

    lines = ["EPISODIC MEMORY (remembered facts about the user and past topics):"]
    for ep in relevant:
        date  = ep["session_date"]
        etype = ep["event_type"].upper()
        imp   = ep["importance"]
        lines.append(f"  [{etype} | {date} | importance={imp:.1f}] {ep['summary']}")

    return "\n".join(lines)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d