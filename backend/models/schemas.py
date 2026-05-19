"""
backend/models/schemas.py
--------------------------
All Pydantic v2 request / response / internal models for the Research Assistant.

Sections:
  1. Chat / Query models       — request + response for /chat endpoint
  2. Source models             — RAG + web search results
  3. Agent event models        — streaming SSE events
  4. Memory models             — long-term + episodic read/write
  5. Session models            — session list, stats, history
  6. Document / Ingest models  — PDF upload + ingest pipeline
  7. Config / Settings models  — runtime overrides
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


# ===========================================================================
# 1. CHAT / QUERY
# ===========================================================================

class ChatMessage(BaseModel):
    """Single turn in a conversation."""
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1)


class QueryRequest(BaseModel):
    """
    Payload sent by the frontend to POST /chat.
    All fields except query and session_id have sensible defaults.
    """
    query: str = Field(..., min_length=1, description="The user's question or prompt.")
    session_id: str = Field(..., min_length=1, description="Unique conversation identifier.")

    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        description="Previous turns — used when short-term memory is unavailable.",
    )

    model_id: str = Field(
        default="groq/llama-3.3-70b-versatile",
        description="Provider/model string e.g. 'groq/llama-3.3-70b-versatile'.",
    )

    persona: str = Field(
        default="researcher",
        description="Response style: student | researcher | executive | creative",
    )

    image_b64: Optional[str]        = Field(default=None, description="Base64-encoded image (inline upload).")
    image_media_type: Optional[str] = Field(default=None, description="MIME type e.g. 'image/png'.")

    use_web_search:  bool = Field(default=True,  description="Enable DuckDuckGo web search step.")
    use_rag:         bool = Field(default=True,  description="Enable ChromaDB RAG retrieval step.")
    use_episodic:    bool = Field(default=True,  description="Inject episodic memory into system prompt.")
    use_long_term:   bool = Field(default=True,  description="Reload history from SQLite if short-term is empty.")

    @field_validator("persona")
    @classmethod
    def _validate_persona(cls, v: str) -> str:
        allowed = {"student", "researcher", "executive", "creative"}
        if v not in allowed:
            raise ValueError(f"persona must be one of {allowed}")
        return v

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError("model_id must be 'provider/model-name' e.g. 'groq/llama-3.3-70b-versatile'")
        return v

    @model_validator(mode="after")
    def _image_pair(self) -> QueryRequest:
        if bool(self.image_b64) != bool(self.image_media_type):
            raise ValueError("image_b64 and image_media_type must both be set or both be None.")
        return self


class QueryResponse(BaseModel):
    """Non-streaming response envelope (used for testing / non-SSE mode)."""
    session_id:   str
    answer:       str
    sources:      list[Source]          = Field(default_factory=list)
    images:       list[ImagePreview]    = Field(default_factory=list)
    model_id:     str                   = ""
    persona:      str                   = "researcher"
    elapsed_ms:   Optional[float]       = None


# ===========================================================================
# 2. SOURCE MODELS
# ===========================================================================

class Source(BaseModel):
    """One retrieved context chunk (RAG or web)."""
    title:   str           = ""
    content: str
    url:     Optional[str] = None

    # FIX: Removed ge/le constraints — ChromaDB returns cosine distances which
    # can be negative or >1. We clamp the display value in the validator instead.
    score:   Optional[float] = Field(default=None, description="Relevance score (clamped to 0–1 for display).")

    source_type: str       = Field(default="rag", description="'rag' | 'web'")

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: Optional[float]) -> Optional[float]:
        """
        Clamp raw retrieval scores (e.g. ChromaDB cosine distances) to [0, 1].
        ChromaDB distances can be negative or exceed 1.0 — this prevents
        validation errors and ensures the frontend always shows a sane value.
        """
        if v is None:
            return None
        return round(max(0.0, min(1.0, float(v))), 4)


class WebSearchResult(BaseModel):
    """Raw result from DuckDuckGo / web_search tool."""
    title:   str           = ""
    url:     str
    content: str
    score:   float         = 0.7


class ImagePreview(BaseModel):
    """Truncated image reference sent to the frontend (b64 preview only)."""
    filename:   str   = "unknown"
    page:       int   = 0
    media_type: str   = "image/png"
    b64:        str   = Field(..., description="First 100 chars of base64 data — preview only.")


# ===========================================================================
# 3. AGENT EVENT MODELS  (Server-Sent Events streaming)
# ===========================================================================

class AgentStatus(BaseModel):
    """
    One SSE frame emitted by the orchestrator.

    status values:
      'thinking'  — agent is working (shows spinner in UI)
      'streaming' — writer is yielding answer tokens (message = token chunk)
      'done'      — orchestrator finished (includes sources + images)
      'error'     — something went wrong
    """
    agent:   str = Field(..., description="Agent name: orchestrator|retrieval|web_search|vision|writer")
    status:  str = Field(..., pattern=r"^(thinking|streaming|done|error)$")
    message: str = ""

    # Only present on final 'done' event
    sources: list[Source]       = Field(default_factory=list)
    images:  list[ImagePreview] = Field(default_factory=list)


# Keep backward-compatible alias
AgentEvent = AgentStatus


# ===========================================================================
# 4. MEMORY MODELS
# ===========================================================================

# ── Episodic ────────────────────────────────────────────────────────────────

class EpisodeCreate(BaseModel):
    """Body for POST /memory/episodes."""
    session_id:  str
    summary:     str = Field(..., min_length=5)
    event_type:  str = Field(default="fact", description="fact|preference|question|insight|document")
    detail:      str = ""
    tags:        list[str] = Field(default_factory=list)
    importance:  float     = Field(default=0.5, ge=0.0, le=1.0)
    source_role: str       = Field(default="user", pattern=r"^(user|assistant)$")

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        allowed = {"fact", "preference", "question", "insight", "document"}
        if v not in allowed:
            raise ValueError(f"event_type must be one of {allowed}")
        return v


class EpisodeOut(BaseModel):
    """Episode returned from GET /memory/episodes."""
    id:           int
    session_id:   str
    event_type:   str
    summary:      str
    detail:       str
    tags:         list[str]
    importance:   float
    source_role:  str
    created_at:   str
    session_date: str


class EpisodeImportanceUpdate(BaseModel):
    """Body for PATCH /memory/episodes/{id}/importance."""
    importance: float = Field(..., ge=0.0, le=1.0)


# ── Long-term / session ─────────────────────────────────────────────────────

class LongTermMessageOut(BaseModel):
    """One message from GET /memory/sessions/{id}."""
    role:      str
    content:   str
    timestamp: str
    metadata:  dict[str, Any] = Field(default_factory=dict)


class SessionSummaryBody(BaseModel):
    """Body for POST /memory/sessions/{id}/summary."""
    summary: str = Field(..., min_length=10)


# ===========================================================================
# 5. SESSION MODELS
# ===========================================================================

class SessionOut(BaseModel):
    """Row from GET /memory/sessions list."""
    session_id:    str
    persona:       str
    model_id:      str
    created_at:    str
    updated_at:    str
    message_count: int
    summary:       str


class SessionHistoryOut(BaseModel):
    """Response from GET /memory/sessions/{id}."""
    session_id: str
    messages:   list[LongTermMessageOut]


class SessionStatsOut(BaseModel):
    """Detailed stats for one session."""
    session_id:    str
    persona:       str
    model_id:      str
    created_at:    str
    updated_at:    str
    message_count: int
    summary:       str


class SearchResult(BaseModel):
    """One hit from GET /memory/search."""
    session_id: str
    role:       str
    content:    str
    timestamp:  str


class SearchResponse(BaseModel):
    query:   str
    results: list[SearchResult]


# ===========================================================================
# 6. DOCUMENT / INGEST MODELS
# ===========================================================================

class IngestRequest(BaseModel):
    """
    Metadata sent alongside a file upload to POST /ingest.
    The actual file bytes come as multipart/form-data.
    """
    filename:    str
    description: str = ""
    tags:        list[str] = Field(default_factory=list)
    chunk_size:  int = Field(default=500,  ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0,   le=500)


class IngestResponse(BaseModel):
    """Response after successfully ingesting a document."""
    filename:      str
    chunks_stored: int
    pages:         int
    images_found:  int
    message:       str = "Ingestion complete."


class DocumentChunk(BaseModel):
    """One chunk stored in / retrieved from ChromaDB."""
    chunk_id:   str
    content:    str
    source:     str
    page:       int   = 0
    score:      float = 0.0
    metadata:   dict[str, Any] = Field(default_factory=dict)


# ===========================================================================
# 7. CONFIG / SETTINGS MODELS
# ===========================================================================

class ModelInfo(BaseModel):
    """Describes one available model."""
    model_id:       str
    provider:       str
    display_name:   str
    supports_vision: bool = False
    context_window:  int  = 8192


class PersonaInfo(BaseModel):
    name:        str
    description: str


class HealthResponse(BaseModel):
    status:    str = "ok"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    version:   str = "1.0.0"