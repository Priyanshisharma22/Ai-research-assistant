# routers/integrations.py
import os
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from tools.integrations import (
    build_google_credentials,
    list_google_drive_files,
    sync_google_drive_file,
    list_notion_pages,
    sync_notion_page,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request models ─────────────────────────────────────────────

class ListRequest(BaseModel):
    page_size: int = 20

class SyncRequest(BaseModel):
    source: str                        # "google_drive" | "notion"
    item_id: str
    item_name: str
    credentials: dict = {}             # frontend sends {} — backend fills from .env
    mime_type: Optional[str] = None    # required for Google Drive


# ── Google Drive ───────────────────────────────────────────────

@router.post("/integrations/google-drive/list")
def list_drive_files(req: ListRequest):
    """
    List Google Drive files using credentials from .env.
    Frontend sends no credentials — everything comes from environment.
    """
    try:
        creds = build_google_credentials()   # reads GOOGLE_* from .env
        files = list_google_drive_files(creds, page_size=req.page_size)
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"[Drive/list] {e}")
        # Return friendly error the frontend can display
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── Notion ─────────────────────────────────────────────────────

@router.post("/integrations/notion/list")
def list_notion(req: ListRequest):
    """
    List Notion pages using NOTION_TOKEN from .env.
    """
    try:
        notion_token = os.getenv("NOTION_TOKEN", "")
        if not notion_token:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail="NOTION_TOKEN not set in .env"
            )
        pages = list_notion_pages(notion_token, page_size=req.page_size)
        return {"pages": pages, "count": len(pages)}
    except Exception as e:
        logger.error(f"[Notion/list] {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── Unified Sync ───────────────────────────────────────────────

@router.post("/integrations/sync")
def sync_item(req: SyncRequest):
    """
    Sync a single file/page into uploads/.
    Frontend sends empty credentials dict — backend fills from .env.
    """
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")

    try:
        if req.source == "google_drive":
            creds = build_google_credentials()   # always from .env
            local_path = sync_google_drive_file(
                credentials_json=creds,
                file_id=req.item_id,
                file_name=req.item_name,
                mime_type=req.mime_type or "application/pdf",
                upload_dir=upload_dir,
            )

        elif req.source == "notion":
            notion_token = os.getenv("NOTION_TOKEN", "")
            if not notion_token:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=500,
                    detail="NOTION_TOKEN not set in .env"
                )
            local_path = sync_notion_page(
                notion_token=notion_token,
                page_id=req.item_id,
                page_title=req.item_name,
                upload_dir=upload_dir,
            )

        else:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Unknown source: {req.source}"
            )

        return {
            "status": "synced",
            "local_path": local_path,
            "source": req.source,
            "item_name": req.item_name,
        }

    except Exception as e:
        logger.error(f"[Sync] {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ───────────────────────────────────────────────

@router.get("/integrations/status")
def integrations_status():
    """Quick check that env credentials are present."""
    return {
        "google_drive": bool(os.getenv("GOOGLE_REFRESH_TOKEN")),
        "notion":        bool(os.getenv("NOTION_TOKEN")),
    }