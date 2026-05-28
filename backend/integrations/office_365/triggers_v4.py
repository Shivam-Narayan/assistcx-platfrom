"""
Outlook trigger handlers for TaskSource polling (v4).

Provider-specific polling logic (Microsoft Graph delta queries).
Persisting into ``event_inbox`` and updating ``task_sources`` is handled by the worker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from configs.auth_schemas_v4 import AUTH_SCHEMAS
from logger import configure_logging
from models.connection_v4 import Connection
from models.task_source_v4 import TaskSource
from repository.connection_repository_v4 import ConnectionRepository
from utils.crypto_utils import decrypt_connection_credentials, decrypt_string, encrypt_string

logger = configure_logging(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ---------------------------------------------------------------------------
# Data contracts between trigger and worker
# ---------------------------------------------------------------------------

@dataclass
class NormalizedEmailEvent:
    external_event_id: str
    payload: Dict[str, Any]


@dataclass
class PollNewEmailsResult:
    events: List[NormalizedEmailEvent] = field(default_factory=list)
    new_cursor: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _user_path_segment(mailbox: str) -> str:
    return quote(mailbox, safe="")


def _connection_is_usable(connection: Connection) -> bool:
    if not connection.is_active:
        return False
    return connection.auth_status in ("valid", "healthy", "ok")


def _try_existing_token(connection: Connection) -> Optional[str]:
    """Attempt to extract a usable access token from the connection's stored token."""
    if not connection.encrypted_token:
        return None
    try:
        token_str = decrypt_string(connection.encrypted_token)
        if not token_str:
            return None
        if token_str.strip().startswith("{"):
            bundle = json.loads(token_str)
            return bundle.get("access_token") or None
        return token_str
    except Exception:
        return None


async def _fetch_client_credentials_token(
    db: AsyncSession,
    connection: Connection,
    creds: Dict[str, Optional[str]],
    auth_schema: Dict[str, Any],
) -> Optional[str]:
    """Exchange client credentials for a new Graph access token and cache it on the connection."""
    preset = auth_schema.get("preset") or {}
    token_url_tpl = preset.get("token_url") or ""
    tenant_id = (creds.get("tenant_id") or "common").strip()
    token_url = token_url_tpl.format(tenant_id=tenant_id) if token_url_tpl else ""

    if not token_url:
        return None

    form = {
        "client_id": creds.get("client_id"),
        "client_secret": creds.get("client_secret"),
        "grant_type": "client_credentials",
        "scope": preset.get("scope", "https://graph.microsoft.com/.default"),
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                token_url,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            access = resp.json().get("access_token")
            if access:
                repo = ConnectionRepository(db)
                await repo.update_connection({
                    "connection_id": connection.id,
                    "encrypted_token": encrypt_string(access),
                })
            return access
    except httpx.HTTPStatusError as e:
        logger.error(
            "Graph token request failed connection=%s status=%s body=%s",
            connection.id,
            e.response.status_code if e.response else None,
            (e.response.text or "")[:800] if e.response else None,
        )
        return None
    except Exception as e:
        logger.error("Graph token request error connection=%s err=%s", connection.id, e)
        return None


async def _get_graph_access_token(db: AsyncSession, connection: Connection) -> Optional[str]:
    """Resolve a valid Graph API access token for the connection."""
    token = _try_existing_token(connection)
    if token:
        return token

    auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key)
    if not auth_schema:
        logger.warning("Unknown auth_schema_key: %s", connection.auth_schema_key)
        return None

    creds = decrypt_connection_credentials(connection.encrypted_credentials)
    grant_type = (auth_schema.get("preset", {}).get("grant_type") or "").strip()

    if grant_type == "client_credentials" or connection.auth_schema_key == "microsoft_graph_client_credentials":
        return await _fetch_client_credentials_token(db, connection, creds, auth_schema)

    return None


async def _resolve_folder_id(
    client: httpx.AsyncClient, token: str, mailbox: str, folder_name: str,
) -> Optional[str]:
    """Look up a mail folder's Graph ID by display name. Returns None on failure."""
    seg = _user_path_segment(mailbox)
    url = f"{GRAPH_BASE}/users/{seg}/mailFolders"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Failed to list mail folders for %s: %s", mailbox, e)
        return None

    for folder_item in resp.json().get("value", []):
        if (folder_item.get("displayName") or "").lower() == folder_name.lower():
            return folder_item["id"]

    logger.warning("Folder '%s' not found for mailbox %s", folder_name, mailbox)
    return None


def _build_message_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    party = item.get("from") or {}
    ea = party.get("emailAddress") if isinstance(party, dict) else {}
    if not isinstance(ea, dict):
        ea = {}
    return {
        "id": item.get("id"),
        "subject": item.get("subject"),
        "received_at": item.get("receivedDateTime"),
        "web_link": item.get("webLink"),
        "sender_email": (ea.get("address") or "").strip().lower() or None,
        "sender_name": ea.get("name"),
    }


# ---------------------------------------------------------------------------
# Public trigger class (referenced by triggers_v4.py config)
# ---------------------------------------------------------------------------

class OutlookTriggers:

    async def poll_new_emails(
        self,
        db: AsyncSession,
        task_source: TaskSource,
        connection: Connection,
        *,
        polling_start_time: Optional[str] = None,
    ) -> PollNewEmailsResult:

        if not _connection_is_usable(connection):
            logger.warning("Connection %s is not usable (active=%s, auth=%s)",
                connection.id, connection.is_active, connection.auth_status)
            return PollNewEmailsResult()

        rc = task_source.resource_config or {}
        mailbox = (rc.get("mailbox_email") or "").strip()
        folder_name = (rc.get("folder") or "Inbox").strip()
        if not mailbox:
            logger.error("task_source %s missing resource_config.mailbox_email", task_source.id)
            return PollNewEmailsResult()

        token = await _get_graph_access_token(db, connection)
        if not token:
            logger.error("Failed to obtain Graph token for connection %s", connection.id)
            return PollNewEmailsResult()

        cursor = dict(task_source.cursor or {})
        delta_link = cursor.get("delta_link")

        # On first poll, use polling_start_time as watermark (or now)
        initial_sync_watermark: Optional[datetime] = None
        if not delta_link:
            if polling_start_time:
                try:
                    initial_sync_watermark = datetime.strptime(
                        polling_start_time, "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    initial_sync_watermark = datetime.now(timezone.utc)
            else:
                initial_sync_watermark = datetime.now(timezone.utc)

        events: List[NormalizedEmailEvent] = []
        new_cursor: Dict[str, Any] = dict(cursor)

        async with httpx.AsyncClient(timeout=120.0) as client:
            headers = {"Authorization": f"Bearer {token}"}

            folder_id = await _resolve_folder_id(client, token, mailbox, folder_name)
            if not folder_id:
                return PollNewEmailsResult()

            user_seg = _user_path_segment(mailbox)

            if delta_link:
                next_url: Optional[str] = delta_link
            else:
                since_dt = initial_sync_watermark or datetime.now(timezone.utc)
                since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                next_url = (
                    f"{GRAPH_BASE}/users/{user_seg}/mailFolders/{folder_id}/messages/delta"
                    f"?$filter=receivedDateTime ge {since_iso}"
                )

            final_delta: Optional[str] = None

            while next_url:
                try:
                    resp = await client.get(next_url, headers=headers)
                    if resp.status_code == 401:
                        logger.error("Graph 401 during delta poll for connection %s", connection.id)
                        break
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error("Graph delta poll failed status=%s", e.response.status_code)
                    break
                except Exception as e:
                    logger.error("Graph delta poll failed: %s", e)
                    break

                body = resp.json()

                for item in body.get("value", []):
                    if item.get("@removed"):
                        continue
                    mid = item.get("id")
                    if not mid:
                        continue
                    payload = {
                        "provider_key": task_source.provider_key,
                        "trigger_key": task_source.trigger_key,
                        "mailbox_email": mailbox,
                        "folder": folder_name,
                        "message": _build_message_payload(item),
                    }
                    events.append(
                        NormalizedEmailEvent(external_event_id=str(mid), payload=payload)
                    )

                if body.get("@odata.deltaLink"):
                    final_delta = body["@odata.deltaLink"]
                next_url = body.get("@odata.nextLink")

            if final_delta:
                new_cursor["delta_link"] = final_delta

        return PollNewEmailsResult(events=events, new_cursor=new_cursor)
