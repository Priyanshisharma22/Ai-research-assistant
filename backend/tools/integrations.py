"""
tools/integrations.py
---------------------
Google Drive & Notion sync - uses direct HTTP requests, no SDK.

Fix applied: Google OAuth token is now refreshed automatically using the
refresh token + client credentials loaded from environment variables.
The original 403 "ACCESS_TOKEN_SCOPE_INSUFFICIENT" error was caused by
using a stale / scope-limited access token. Now the token is always
refreshed at startup using GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, and
GOOGLE_CLIENT_SECRET from the .env file.
"""

import os
import logging
import time
from typing import Optional
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()  # Load .env so all os.getenv() calls below work automatically

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# ─────────────────────────────────────────────
# ENV-BASED CREDENTIALS BUILDER
# ─────────────────────────────────────────────

def build_google_credentials() -> dict:
    """
    Build a credentials dict entirely from environment variables.
    Use this when you have no session/DB credentials to pass in.

    Required .env keys:
        GOOGLE_REFRESH_TOKEN
        GOOGLE_CLIENT_ID
        GOOGLE_CLIENT_SECRET
        GOOGLE_ACCESS_TOKEN  (optional – will be refreshed automatically)
    """
    creds = {
        "refresh_token": os.getenv("GOOGLE_REFRESH_TOKEN", ""),
        "client_id":     os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "access_token":  os.getenv("GOOGLE_ACCESS_TOKEN", ""),
        "expires_at":    0,  # Force a refresh on first use
    }
    missing = [k for k, v in creds.items() if not v and k != "expires_at"]
    if missing:
        logger.warning(f"[GoogleCreds] Missing env vars: {missing}")
    return creds

# ─────────────────────────────────────────────
# GOOGLE OAUTH HELPERS
# ─────────────────────────────────────────────

def _resolve(value: str, env_key: str) -> str:
    """Return value if non-empty, else fall back to the env var."""
    return value or os.getenv(env_key, "")


def refresh_google_access_token(credentials_json: dict) -> dict:
    """
    Exchange a refresh_token for a fresh access_token that includes the
    Drive scope.

    Looks up each credential from credentials_json first, then falls back
    to the corresponding environment variable automatically.

        credentials_json key  →  env var fallback
        ─────────────────────────────────────────
        refresh_token         →  GOOGLE_REFRESH_TOKEN
        client_id             →  GOOGLE_CLIENT_ID
        client_secret         →  GOOGLE_CLIENT_SECRET

    Returns an updated credentials dict with a new access_token.
    """
    refresh_token = _resolve(credentials_json.get("refresh_token", ""), "GOOGLE_REFRESH_TOKEN")
    client_id     = _resolve(credentials_json.get("client_id", ""),     "GOOGLE_CLIENT_ID")
    client_secret = _resolve(credentials_json.get("client_secret", ""), "GOOGLE_CLIENT_SECRET")

    missing = []
    if not refresh_token: missing.append("GOOGLE_REFRESH_TOKEN")
    if not client_id:     missing.append("GOOGLE_CLIENT_ID")
    if not client_secret: missing.append("GOOGLE_CLIENT_SECRET")

    if missing:
        raise ValueError(
            f"Cannot refresh Google token. Missing: {missing}. "
            f"Add them to credentials_json or to your .env file."
        )

    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Failed to refresh Google access token ({resp.status_code}): {resp.text}"
        )

    token_data = resp.json()
    updated = {**credentials_json, **token_data}
    updated["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    # Back-fill resolved values so they're available for subsequent refreshes
    updated.setdefault("refresh_token", refresh_token)
    updated.setdefault("client_id",     client_id)
    updated.setdefault("client_secret", client_secret)
    logger.info("[GoogleOAuth] Access token refreshed successfully.")
    return updated


def get_valid_access_token(credentials_json: dict) -> str:
    """
    Return a valid access token, refreshing automatically when expired or
    about to expire (within 60 seconds).

    If credentials_json has no access_token at all (e.g. first call with
    only env-var credentials), a refresh is forced immediately.
    """
    expires_at    = credentials_json.get("expires_at", 0)
    has_token     = bool(credentials_json.get("access_token", ""))
    token_expired = time.time() >= expires_at - 60

    if not has_token or token_expired:
        logger.info("[GoogleOAuth] Refreshing access token.")
        credentials_json.update(refresh_google_access_token(credentials_json))

    return credentials_json["access_token"]


def verify_token_scopes(access_token: str) -> dict:
    """
    Call Google's tokeninfo endpoint and return the parsed JSON.
    Useful for debugging scope issues.
    """
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v1/tokeninfo",
        params={"access_token": access_token},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────
# GOOGLE DRIVE
# ─────────────────────────────────────────────

def list_google_drive_files(credentials_json: dict, page_size: int = 20) -> list[dict]:
    """
    List files from Google Drive.

    Automatically refreshes the access token if it is expired.
    Returns a filtered list of documents (PDF, plain-text, Google Docs, DOCX).
    Falls back to the full unfiltered list if no matching files are found.
    """
    access_token = get_valid_access_token(credentials_json)

    params = {
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,size)",
        "orderBy": "modifiedTime desc",
    }

    resp = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=20,
    )

    if resp.status_code == 401:
        # Token might have been invalidated externally – force a refresh and retry once
        logger.warning("[GoogleDrive] 401 received – forcing token refresh and retrying.")
        credentials_json["expires_at"] = 0
        access_token = get_valid_access_token(credentials_json)
        resp = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=20,
        )

    if not resp.ok:
        raise RuntimeError(
            f"Google Drive list failed ({resp.status_code}): {resp.text}"
        )

    all_files = resp.json().get("files", [])

    allowed_mime_types = {
        "application/pdf",
        "text/plain",
        "application/vnd.google-apps.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    filtered = [f for f in all_files if f.get("mimeType") in allowed_mime_types]
    return filtered if filtered else all_files


def download_google_drive_file(credentials_json: dict, file_id: str, mime_type: str) -> bytes:
    """
    Download (or export) a file from Google Drive.

    Google Docs (application/vnd.google-apps.document) are exported as PDF.
    All other supported types are downloaded as-is.
    """
    access_token = get_valid_access_token(credentials_json)
    headers = {"Authorization": f"Bearer {access_token}"}

    if mime_type == "application/vnd.google-apps.document":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        resp = requests.get(
            url, headers=headers, params={"mimeType": "application/pdf"}, timeout=60
        )
    else:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        resp = requests.get(url, headers=headers, timeout=60)

    if not resp.ok:
        raise RuntimeError(
            f"Google Drive download failed ({resp.status_code}): {resp.text}"
        )

    return resp.content


def sync_google_drive_file(
    credentials_json: dict,
    file_id: str,
    file_name: str,
    mime_type: str,
    upload_dir: str = "uploads/",
) -> str:
    """
    Download a Drive file and save it locally.  Returns the local file path.
    """
    content = download_google_drive_file(credentials_json, file_id, mime_type)

    if mime_type == "application/vnd.google-apps.document":
        ext = ".pdf"
    else:
        ext = Path(file_name).suffix or ".bin"

    save_path = os.path.join(upload_dir, Path(file_name).stem + ext)
    os.makedirs(upload_dir, exist_ok=True)

    with open(save_path, "wb") as f:
        f.write(content)

    logger.info(f"[GoogleDrive] Saved '{file_name}' -> {save_path}")
    return save_path


# ─────────────────────────────────────────────
# NOTION
# ─────────────────────────────────────────────

def get_notion_headers(notion_token: str) -> dict:
    return {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def list_notion_pages(notion_token: str, page_size: int = 20) -> list[dict]:
    """List recently edited Notion pages."""
    resp = requests.post(
        "https://api.notion.com/v1/search",
        headers=get_notion_headers(notion_token),
        json={
            "filter": {"value": "page", "property": "object"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": page_size,
        },
        timeout=15,
    )
    resp.raise_for_status()

    pages = []
    for page in resp.json().get("results", []):
        pages.append(
            {
                "id": page["id"],
                "title": _extract_notion_title(page),
                "url": page.get("url", ""),
                "last_edited_time": page.get("last_edited_time", ""),
            }
        )
    return pages


def _extract_notion_title(page: dict) -> str:
    props = page.get("properties", {})
    for key in ("Name", "Title", "title"):
        if key in props:
            rich_text = props[key].get("title", props[key].get("rich_text", []))
            if rich_text:
                return "".join(t.get("plain_text", "") for t in rich_text)
    return "Untitled"


def _fetch_notion_blocks(notion_token: str, block_id: str) -> list[dict]:
    """Fetch all child blocks for a given block ID, handling pagination."""
    headers = get_notion_headers(notion_token)
    blocks: list[dict] = []
    cursor: Optional[str] = None

    while True:
        params: dict = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = requests.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        blocks.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return blocks


def _blocks_to_text(blocks: list[dict]) -> str:
    """Convert a flat list of Notion block objects into Markdown-ish plain text."""
    lines: list[str] = []

    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        text = "".join(t.get("plain_text", "") for t in content.get("rich_text", []))

        if btype == "heading_1":
            lines.append(f"\n# {text}\n")
        elif btype == "heading_2":
            lines.append(f"\n## {text}\n")
        elif btype == "heading_3":
            lines.append(f"\n### {text}\n")
        elif btype in ("bulleted_list_item", "numbered_list_item"):
            lines.append(f"  - {text}")
        elif btype == "to_do":
            checked = "[x]" if content.get("checked") else "[ ]"
            lines.append(f"  {checked} {text}")
        elif btype == "code":
            lang = content.get("language", "")
            lines.append(f"\n```{lang}\n{text}\n```\n")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "divider":
            lines.append("\n---\n")
        elif text:
            lines.append(text)

    return "\n".join(lines)


def fetch_notion_page_content(notion_token: str, page_id: str) -> str:
    """Return the full text content of a Notion page."""
    blocks = _fetch_notion_blocks(notion_token, page_id)
    return _blocks_to_text(blocks)


def sync_notion_page(
    notion_token: str,
    page_id: str,
    page_title: str,
    upload_dir: str = "uploads/",
) -> str:
    """
    Fetch a Notion page and save it as a .txt file locally.
    Returns the local file path.
    """
    content = fetch_notion_page_content(notion_token, page_id)

    safe_title = (
        "".join(c if c.isalnum() or c in " _-" else "_" for c in page_title)
        .strip()[:60]
    )
    save_path = os.path.join(upload_dir, f"notion_{safe_title}.txt")
    os.makedirs(upload_dir, exist_ok=True)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(f"# {page_title}\n\n{content}")

    logger.info(f"[Notion] Saved '{page_title}' -> {save_path}")
    return save_path


# ─────────────────────────────────────────────
# UNIFIED ENTRY POINT
# ─────────────────────────────────────────────

def sync_external_source(
    source: str,
    item_id: str,
    item_name: str,
    credentials: dict,
    upload_dir: str = "uploads/",
    mime_type: Optional[str] = None,
) -> dict:
    """
    Unified sync entry point for all supported external sources.

    Parameters
    ----------
    source      : "google_drive" | "notion"
    item_id     : file ID (Drive) or page ID (Notion)
    item_name   : human-readable name used for the local filename
    credentials : dict containing auth credentials for the given source
                  Google Drive: {access_token, refresh_token, client_id, client_secret}
                  Notion:       {notion_token}  OR  notion_token as a top-level key
    upload_dir  : local directory to save synced files
    mime_type   : required for Google Drive; ignored for Notion

    Returns
    -------
    dict with keys: local_path, source, item_name, status
    """
    if source == "google_drive":
        local_path = sync_google_drive_file(
            credentials_json=credentials,
            file_id=item_id,
            file_name=item_name,
            mime_type=mime_type or "application/pdf",
            upload_dir=upload_dir,
        )

    elif source == "notion":
        notion_token = (
            credentials.get("notion_token")
            or credentials.get("token")
            or os.getenv("NOTION_TOKEN", "")
        )
        if not notion_token:
            raise ValueError("Notion token not found in credentials or NOTION_TOKEN env var.")

        local_path = sync_notion_page(
            notion_token=notion_token,
            page_id=item_id,
            page_title=item_name,
            upload_dir=upload_dir,
        )

    else:
        raise ValueError(f"Unsupported source: '{source}'. Expected 'google_drive' or 'notion'.")

    return {
        "local_path": local_path,
        "source": source,
        "item_name": item_name,
        "status": "synced",
    }


# ─────────────────────────────────────────────
# QUICK DEBUG HELPER  (remove in production)
# ─────────────────────────────────────────────

def debug_token_info(credentials_json: dict) -> None:
    """
    Print token scope information.  Call this if you hit a 403 to confirm
    the refreshed token carries the drive.readonly scope.
    """
    access_token = get_valid_access_token(credentials_json)
    info = verify_token_scopes(access_token)
    logger.info(f"[TokenDebug] scope  : {info.get('scope')}")
    logger.info(f"[TokenDebug] email  : {info.get('email')}")
    logger.info(f"[TokenDebug] expires: {info.get('expires_in')}s")
    print(info)