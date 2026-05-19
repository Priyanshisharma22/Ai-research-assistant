"""
routers/integrations.py
-----------------------
FastAPI router for Google Drive and Notion integration endpoints.

All Google credentials are loaded from environment variables (.env).
The frontend does NOT need to supply an access_token for Google Drive —
it only needs to call the endpoint. Tokens are refreshed automatically.

For Notion, the token is still accepted from the frontend OR falls back
to NOTION_TOKEN in .env.
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from tools.integrations import (
    build_google_credentials,
    get_valid_access_token,
    list_google_drive_files,
    list_notion_pages,
    sync_external_source,
)

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])


# ─────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────

class GoogleListRequest(BaseModel):
    # access_token is now OPTIONAL — backend uses .env if not supplied
    access_token: Optional[str] = None
    page_size: int = 20


class NotionListRequest(BaseModel):
    notion_token: Optional[str] = None   # falls back to NOTION_TOKEN env var
    page_size: int = 20


class SyncRequest(BaseModel):
    source: str                          # "google_drive" | "notion"
    item_id: str
    item_name: str
    mime_type: Optional[str] = None
    credentials: Optional[dict] = None  # ignored for Google Drive (uses .env)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _google_creds(access_token: Optional[str] = None) -> dict:
    """
    Build a Google credentials dict from .env, optionally overriding the
    access_token with whatever the frontend sent (usually ignored now).
    The refresh_token / client_id / client_secret always come from .env.
    """
    creds = build_google_credentials()
    if access_token:
        creds["access_token"] = access_token
    return creds


def _notion_token(supplied: Optional[str]) -> str:
    token = supplied or os.getenv("NOTION_TOKEN", "")
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Notion token not found. Set NOTION_TOKEN in .env or pass notion_token in the request.",
        )
    return token


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/google-drive/list")
async def list_drive_files(req: GoogleListRequest):
    """
    List Google Drive files.
    The frontend no longer needs to supply an access_token —
    credentials come from .env automatically.
    """
    try:
        creds = _google_creds(req.access_token)
        files = list_google_drive_files(creds, page_size=req.page_size)
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"[Drive] list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/notion/list")
async def list_notion(req: NotionListRequest):
    """List recently edited Notion pages."""
    try:
        token = _notion_token(req.notion_token)
        pages = list_notion_pages(token, page_size=req.page_size)
        return {"pages": pages, "count": len(pages)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Notion] list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_item(req: SyncRequest):
    """
    Sync a single file/page from Google Drive or Notion into the local
    uploads directory so it can be indexed by the RAG pipeline.
    """
    try:
        if req.source == "google_drive":
            # Always use .env credentials for Google Drive — ignore
            # whatever the frontend put in credentials.access_token
            credentials = _google_creds(
                (req.credentials or {}).get("access_token")
            )
        elif req.source == "notion":
            notion_token = _notion_token(
                (req.credentials or {}).get("notion_token")
            )
            credentials = {"notion_token": notion_token}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported source: {req.source}")

        upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
        result = sync_external_source(
            source=req.source,
            item_id=req.item_id,
            item_name=req.item_name,
            credentials=credentials,
            upload_dir=upload_dir,
            mime_type=req.mime_type,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Sync] failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google-drive/status")
async def google_drive_status():
    """
    Health-check endpoint — verifies the .env Google credentials work
    without needing any input from the frontend.
    """
    try:
        creds = build_google_credentials()
        missing = [
            k for k in ("refresh_token", "client_id", "client_secret")
            if not creds.get(k)
        ]
        if missing:
            return {
                "status": "misconfigured",
                "missing_env_vars": [
                    f"GOOGLE_{k.upper()}" for k in missing
                ],
            }
        # Try to get a valid token (will refresh if needed)
        token = get_valid_access_token(creds)
        return {
            "status": "ok",
            "token_preview": token[:20] + "...",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}