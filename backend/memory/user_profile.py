"""
memory/user_profile.py
-----------------------
Automatic user profile extraction and management.

Every time the user sends a message, this module scans it for memorable facts:
  - Name / identity         → "My name is Arjun"
  - Expertise / field       → "I'm a PhD student in ML"
  - Preferences             → "I prefer concise answers"
  - Past topics / interests → "I've been working on RAG systems"
  - Goals                   → "I'm trying to build a research assistant"

Extracted facts are stored in episodic.py with high importance scores so they
survive across sessions and get injected into the system prompt automatically.

Public API:
  extract_and_save(session_id, user_message)  → call after every user message
  build_profile_block(session_id)             → returns system-prompt string
  get_profile_summary()                       → returns list of known facts
"""

import re
from typing import Optional
from memory.episodic import (
    save_episode,
    get_episodes,
    search_episodes,
    update_episode_importance,
    get_user_profile,
)


# ---------------------------------------------------------------------------
# Rule-based fast extractors (no LLM needed — zero latency)
# ---------------------------------------------------------------------------

# Each rule: (regex pattern, event_type, importance, tag_list)
_EXTRACTION_RULES: list[tuple[re.Pattern, str, float, list[str]]] = [

    # ── Identity / name ────────────────────────────────────────────────────
    (re.compile(
        r"(?:my name is|i(?:'m| am) called|call me|you can call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        re.IGNORECASE,
    ), "fact", 0.95, ["name", "identity"]),

    # ── Profession / role ──────────────────────────────────────────────────
    (re.compile(
        r"i(?:'m| am) (?:a |an )?(.{3,60}?(?:student|researcher|professor|engineer|developer|scientist|analyst|doctor|phd|postdoc|undergraduate|graduate|manager|designer|writer|journalist))",
        re.IGNORECASE,
    ), "fact", 0.9, ["profession", "role"]),

    # ── Field / domain ─────────────────────────────────────────────────────
    (re.compile(
        r"(?:i(?:'m| am) (?:studying|working on|researching|specializing in)|my (?:field|area|domain|major|specialization) is)\s+(.{3,80}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "fact", 0.88, ["field", "expertise"]),

    # ── Expertise level ────────────────────────────────────────────────────
    (re.compile(
        r"i(?:'m| am) (?:a )?(beginner|novice|intermediate|advanced|expert|senior|junior|experienced)\s+(?:in\s+)?(.{0,60}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "fact", 0.85, ["expertise_level"]),

    # ── Language / tools ───────────────────────────────────────────────────
    (re.compile(
        r"i(?:\s+mainly)? (?:use|work with|code in|program in|prefer)\s+(.{3,80}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "preference", 0.8, ["tools", "language"]),

    # ── Preferences ────────────────────────────────────────────────────────
    (re.compile(
        r"i (?:prefer|like|want|need|always|usually|tend to)\s+(.{5,120}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "preference", 0.75, ["preference"]),

    # ── Goals / projects ───────────────────────────────────────────────────
    (re.compile(
        r"i(?:'m| am) (?:building|creating|developing|working on|trying to)\s+(.{5,120}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "insight", 0.82, ["project", "goal"]),

    # ── Location ───────────────────────────────────────────────────────────
    (re.compile(
        r"i(?:'m| am) (?:from|based in|located in|living in)\s+(.{3,60}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "fact", 0.7, ["location"]),

    # ── Organization / university ──────────────────────────────────────────
    (re.compile(
        r"(?:i (?:study|work) at|my (?:university|company|organization|school|lab) is|at)\s+([A-Z][a-zA-Z\s]{3,60}?)(?:\.|,|$)",
        re.IGNORECASE,
    ), "fact", 0.8, ["organization"]),
]

# Deduplicate: if a very similar summary already exists, skip saving
_SIMILARITY_THRESHOLD = 0.6   # rough word-overlap ratio


def _word_overlap(a: str, b: str) -> float:
    """Rough word-overlap ratio between two strings (0–1)."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _is_duplicate(summary: str, existing: list[dict]) -> Optional[int]:
    """
    Return the episode_id of a very similar existing episode, or None.
    Used to avoid saving the same fact twice and instead reinforce it.
    """
    for ep in existing:
        if _word_overlap(summary, ep["summary"]) >= _SIMILARITY_THRESHOLD:
            return ep["id"]
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_and_save(session_id: str, user_message: str) -> list[str]:
    """
    Scan a user message for memorable facts and save them to episodic memory.

    Args:
        session_id   : Current session (used for episode storage).
        user_message : The raw user query/message text.

    Returns:
        List of summary strings for facts that were saved or reinforced.
        Empty list if nothing notable was found.
    """
    saved: list[str] = []

    # Load existing profile facts so we can deduplicate
    existing = get_user_profile(limit=50)

    for pattern, event_type, importance, tags in _EXTRACTION_RULES:
        match = pattern.search(user_message)
        if not match:
            continue

        # Build a clean summary from the match
        captured = match.group(1).strip().rstrip(".,;")
        if len(captured) < 3:
            continue   # too short to be meaningful

        # Reconstruct a human-readable summary
        summary = _build_summary(event_type, tags, captured, user_message)
        if not summary:
            continue

        # Check for near-duplicate → reinforce importance instead of re-saving
        dup_id = _is_duplicate(summary, existing)
        if dup_id is not None:
            # Bump importance by 0.05 (up to max 1.0) to reinforce re-mentioned facts
            matching = next((e for e in existing if e["id"] == dup_id), None)
            if matching:
                new_imp = min(1.0, matching["importance"] + 0.05)
                update_episode_importance(dup_id, new_imp)
                saved.append(f"[reinforced] {summary}")
            continue

        # Save new episode
        save_episode(
            session_id=session_id,
            summary=summary,
            event_type=event_type,
            detail=user_message[:500],
            tags=tags,
            importance=importance,
            source_role="user",
        )
        saved.append(summary)

        # Add to existing list so subsequent rules in the same message
        # don't create near-duplicates
        existing.append({"id": -1, "summary": summary, "importance": importance})

    return saved


def build_profile_block(session_id: str) -> str:
    """
    Build the USER PROFILE section for injection into the system prompt.

    Pulls the most important known facts about the user across ALL sessions.
    Always included, regardless of the current query — this is identity memory.

    Returns:
        Formatted string ready to prepend to the system prompt, or '' if empty.
    """
    profile = get_user_profile(limit=20)

    if not profile:
        return ""

    # Group by event_type for readability
    facts       = [e for e in profile if e["event_type"] == "fact"]
    preferences = [e for e in profile if e["event_type"] == "preference"]
    insights    = [e for e in profile if e["event_type"] == "insight"]

    lines = ["USER PROFILE (known facts about the person you are talking to):"]

    if facts:
        lines.append("  Identity & Background:")
        for ep in facts[:8]:
            lines.append(f"    • {ep['summary']}")

    if preferences:
        lines.append("  Preferences:")
        for ep in preferences[:5]:
            lines.append(f"    • {ep['summary']}")

    if insights:
        lines.append("  Current Projects & Goals:")
        for ep in insights[:5]:
            lines.append(f"    • {ep['summary']}")

    lines.append(
        "\n  INSTRUCTION: Use this profile to personalise your responses. "
        "If the user asks about themselves (their name, field, etc.), "
        "answer from this profile — do NOT say you don't know."
    )

    return "\n".join(lines)


def get_profile_summary() -> list[dict]:
    """
    Return all stored user profile facts as a list of dicts.
    Useful for a /profile endpoint or sidebar display.

    Returns:
        List of episode dicts with keys: summary, event_type, importance, session_date.
    """
    episodes = get_user_profile(limit=50)
    return [
        {
            "summary":      ep["summary"],
            "event_type":   ep["event_type"],
            "importance":   ep["importance"],
            "session_date": ep["session_date"],
            "tags":         ep["tags"],
        }
        for ep in episodes
    ]


def get_known_name() -> Optional[str]:
    """
    Quick helper: return the user's known name if we have it, else None.
    Used to personalise greetings.
    """
    name_episodes = search_episodes("name identity", limit=5, min_importance=0.9)
    for ep in name_episodes:
        if "name" in ep.get("tags", []):
            # Extract just the name from the summary
            summary = ep["summary"]
            for prefix in ["User's name is", "User is called", "User name:"]:
                if prefix.lower() in summary.lower():
                    return summary.split(prefix)[-1].strip().split()[0]
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_summary(
    event_type: str,
    tags: list[str],
    captured: str,
    full_message: str,
) -> str:
    """
    Convert a regex capture into a human-readable episode summary.
    """
    captured = captured.strip().rstrip(".,;")

    if "name" in tags:
        return f"User's name is {captured}"

    if "profession" in tags or "role" in tags:
        return f"User is a {captured}"

    if "field" in tags or "expertise" in tags:
        return f"User's field/expertise: {captured}"

    if "expertise_level" in tags:
        return f"User describes their level as: {captured}"

    if "tools" in tags or "language" in tags:
        return f"User works with / prefers: {captured}"

    if "preference" in tags:
        # Only save if it's meaningful (>= 4 words)
        if len(captured.split()) < 4:
            return ""
        return f"User preference: {captured}"

    if "project" in tags or "goal" in tags:
        return f"User is working on: {captured}"

    if "location" in tags:
        return f"User is based in: {captured}"

    if "organization" in tags:
        return f"User's organization: {captured}"

    # Generic fallback
    if len(captured.split()) >= 3:
        return f"User mentioned: {captured}"

    return ""