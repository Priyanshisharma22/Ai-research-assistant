"""
memory/short_term.py
---------------------
In-memory conversation history (fast, RAM-only).
Cleared when server restarts — long_term.py handles persistence.

Added: set_history() so orchestrator can warm the cache from SQLite.
"""

from collections import defaultdict

# In-memory store: { session_id: [ {role, content}, ... ] }
_history: dict[str, list[dict]] = defaultdict(list)


def get_history(session_id: str) -> list[dict]:
    """Return conversation history for a session (empty list if none)."""
    return _history[session_id].copy()


def add_message(session_id: str, role: str, content: str) -> None:
    """Append one message to the in-memory history."""
    if not content or not content.strip():
        return
    _history[session_id].append({"role": role, "content": content})


def set_history(session_id: str, messages: list[dict]) -> None:
    """
    Overwrite the in-memory history for a session.
    Used by orchestrator to warm the cache after reloading from SQLite.

    Args:
        session_id : The session to populate.
        messages   : List of {'role': ..., 'content': ...} dicts.
    """
    _history[session_id] = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") and m.get("content")
    ]


def clear_history(session_id: str) -> None:
    """Clear in-memory history for a session."""
    _history[session_id] = []


def get_all_sessions() -> list[str]:
    """Return all active session IDs currently in RAM."""
    return list(_history.keys())