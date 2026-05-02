"""Read-only Gmail via OAuth2 (installed app). Store client JSON + token outside git — see docs/INTEGRATION-GMAIL.md."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import MailMessage

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").lower()
        val = h.get("value") or ""
        if name:
            out[name] = val
    return out


def _parse_internal_date(ms: str | None) -> datetime | None:
    if not ms:
        return None
    try:
        sec = int(ms) / 1000.0
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def fetch_gmail_messages(root: Path, gmail_cfg: dict) -> tuple[list[MailMessage], list[str]]:
    """
    List + metadata-fetch messages. Returns (messages, notes for snapshot footer).
    """
    notes: list[str] = []
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        notes.append(f"Gmail: add Google libraries to your venv (pip install -r requirements.txt). ({e})")
        return [], notes

    cred_path = (os.getenv("GMAIL_OAUTH_CLIENT_JSON") or "").strip() or str(
        gmail_cfg.get("credentials_file") or ""
    ).strip()
    token_path = (os.getenv("GMAIL_TOKEN_JSON") or "").strip() or str(
        gmail_cfg.get("token_file") or "secrets/gmail_token.json"
    ).strip()

    if not cred_path:
        notes.append(
            "Gmail: set gmail.credentials_file in config (repo-relative path) or GMAIL_OAUTH_CLIENT_JSON."
        )
        return [], notes

    credentials_path = Path(cred_path)
    if not credentials_path.is_absolute():
        credentials_path = root / credentials_path
    token_file = Path(token_path)
    if not token_file.is_absolute():
        token_file = root / token_file

    if not credentials_path.is_file():
        notes.append(f"Gmail: OAuth client JSON not found at {credentials_path}")
        return [], notes

    creds: Credentials | None = None
    if token_file.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception as e:
            notes.append(f"Gmail: could not read token file ({e}). Delete it and re-authorize if needed.")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            notes.append(f"Gmail: token refresh failed ({e}). Re-run to sign in again.")
            creds = None

    if not creds or not creds.valid:
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        except Exception as e:
            notes.append(f"Gmail: browser sign-in failed ({e}).")
            return [], notes

    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    except OSError as e:
        notes.append(f"Gmail: could not save token to {token_file} ({e}). Next run may ask to sign in again.")

    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as e:
        notes.append(f"Gmail: API client build failed ({e}).")
        return [], notes

    query = str(gmail_cfg.get("query") or "").strip()
    max_results = int(gmail_cfg.get("max_messages", 25))

    try:
        lst = (
            service.users()
            .messages()
            .list(userId="me", q=query or None, maxResults=max(max_results, 1))
            .execute()
        )
    except Exception as e:
        notes.append(f"Gmail: listing messages failed ({e}).")
        return [], notes

    mids = [m["id"] for m in (lst.get("messages") or []) if m.get("id")]
    out: list[MailMessage] = []

    for mid in mids[:max_results]:
        try:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
        except Exception:
            continue
        payload = msg.get("payload") or {}
        h = _header_map(payload)
        subject = (h.get("subject") or "(no subject)").strip()
        from_addr = (h.get("from") or "").strip()
        snippet = (msg.get("snippet") or "").replace("\r", " ").strip()
        internal = _parse_internal_date(msg.get("internalDate"))
        labels = msg.get("labelIds") or []
        unread = "UNREAD" in labels
        out.append(
            MailMessage(
                id=mid,
                subject=subject[:500],
                from_addr=from_addr[:500],
                snippet=snippet[:300],
                internal_date=internal,
                is_unread=unread,
            )
        )

    return out, notes
