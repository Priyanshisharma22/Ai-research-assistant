"""
routers/profile.py
-------------------
REST endpoints for the user profile system.

GET    /api/profile          → returns all known facts about the user
DELETE /api/profile          → clears all profile facts (fresh start)
GET    /api/profile/name     → returns just the user's known name (or null)
POST   /api/profile/manual   → save a manually entered profile from the UI form
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from memory.user_profile import get_profile_summary, get_known_name
from memory.episodic import get_user_profile, delete_episode, save_episode

router = APIRouter(prefix="/api/profile", tags=["profile"])

# Session ID used for all manually entered profile facts
MANUAL_SESSION_ID = "manual_profile"


# ── Request model ─────────────────────────────────────────────────────────────

class ManualProfileRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    field: Optional[str] = None
    organisation: Optional[str] = None
    bio: Optional[str] = None
    topics: Optional[List[str]] = []
    response_style: Optional[List[str]] = []
    technical_depth: Optional[str] = None
    primary_goal: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_profile():
    """
    Return all known facts about the user, grouped by type.
    Used by the frontend to show a 'What I know about you' panel.
    """
    facts = get_profile_summary()

    grouped = {
        "identity": [],
        "preferences": [],
        "projects": [],
        "other": [],
    }

    for f in facts:
        et = f["event_type"]
        if et == "fact":
            grouped["identity"].append(f)
        elif et == "preference":
            grouped["preferences"].append(f)
        elif et == "insight":
            grouped["projects"].append(f)
        else:
            grouped["other"].append(f)

    return {
        "total": len(facts),
        "profile": grouped,
        "raw": facts,
    }


@router.get("/name")
async def get_name():
    """Return the user's known name, or null if not yet known."""
    name = get_known_name()
    return {"name": name}


@router.delete("")
async def clear_profile():
    """
    Delete all stored profile facts.
    Call this if the user wants to reset what the assistant knows about them.
    """
    episodes = get_user_profile(limit=200)
    deleted = 0
    for ep in episodes:
        if delete_episode(ep["id"]):
            deleted += 1

    return {
        "deleted": deleted,
        "message": f"Cleared {deleted} profile facts.",
    }


@router.post("/manual")
async def save_manual_profile(data: ManualProfileRequest):
    """
    Save a manually entered profile from the UI form.
    Each field is stored as a separate episode in episodic memory
    using save_episode(), so the chat system uses them exactly like
    auto-extracted facts.

    importance=0.9 ensures they pass the 0.6 threshold in get_user_profile()
    and always appear in the memory context injected into the prompt.
    """
    saved = []

    def store(summary: str, event_type: str, tags: List[str]):
        save_episode(
            session_id=MANUAL_SESSION_ID,
            summary=summary,
            event_type=event_type,
            tags=tags,
            importance=0.9,       # high importance — manually set by user
            source_role="user",
        )

    # Identity facts
    if data.name and data.name.strip():
        store(
            summary=f"User's name is {data.name.strip()}",
            event_type="fact",
            tags=["name", "identity"],
        )
        saved.append("name")

    if data.role and data.role.strip():
        store(
            summary=f"User's role/occupation: {data.role.strip()}",
            event_type="fact",
            tags=["role", "identity"],
        )
        saved.append("role")

    if data.field and data.field.strip():
        store(
            summary=f"User's field/domain: {data.field.strip()}",
            event_type="fact",
            tags=["field", "domain", "identity"],
        )
        saved.append("field")

    if data.organisation and data.organisation.strip():
        store(
            summary=f"User's institution/organisation: {data.organisation.strip()}",
            event_type="fact",
            tags=["organisation", "identity"],
        )
        saved.append("organisation")

    if data.bio and data.bio.strip():
        store(
            summary=f"User bio: {data.bio.strip()}",
            event_type="fact",
            tags=["bio", "identity"],
        )
        saved.append("bio")

    # Preferences
    if data.topics:
        store(
            summary=f"User is interested in: {', '.join(data.topics)}",
            event_type="preference",
            tags=["topics", "interests"] + data.topics,
        )
        saved.append("topics")

    if data.response_style:
        store(
            summary=f"User prefers responses that are: {', '.join(data.response_style)}",
            event_type="preference",
            tags=["response_style", "preferences"],
        )
        saved.append("response_style")

    if data.technical_depth and data.technical_depth.strip():
        store(
            summary=f"User's preferred technical depth: {data.technical_depth.strip()}",
            event_type="preference",
            tags=["technical_depth", "preferences"],
        )
        saved.append("technical_depth")

    # Goals (stored as insight → shows under "Projects & Goals" in sidebar)
    if data.primary_goal and data.primary_goal.strip():
        store(
            summary=f"User's primary goal: {data.primary_goal.strip()}",
            event_type="insight",
            tags=["goal", "projects"],
        )
        saved.append("primary_goal")

    return {
        "saved": saved,
        "count": len(saved),
        "message": f"Profile saved with {len(saved)} facts.",
    }