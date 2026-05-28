"""
Celery task ``task_source_worker`` (v4): periodic task-source poll.

Scheduled via RedBeat with args:
  [organization_schema, task_source_id, polling_start_time]
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from celery import shared_task
from fastapi import HTTPException

from db_pool import AsyncDatabasePoolManager
from logger import configure_logging
from repository.connection_repository_v4 import ConnectionRepository
from repository.event_inbox_repository_v4 import EventInboxRepository
from repository.task_source_repository_v4 import TaskSourceRepository
from schemas.event_inbox_schema_v4 import EventInboxCreate
from utils.task_source_utils_v4 import (
    build_event_inbox_dedupe_key,
    default_event_inbox_status,
    resolve_trigger,
)

logger = configure_logging(__name__)

async_db_pool = AsyncDatabasePoolManager()


async def _record_error(
    ts_repo: TaskSourceRepository,
    task_source_id: UUID,
    current_error_count: int,
    message: str,
) -> None:
    now = datetime.now(timezone.utc)
    await ts_repo.update_task_source({
        "task_source_id": task_source_id,
        "last_checked_at": now,
        "error_count": current_error_count + 1,
        "last_error": message,
    })


async def _record_success(
    ts_repo: TaskSourceRepository,
    task_source_id: UUID,
    new_cursor: Optional[Dict],
) -> None:
    now = datetime.now(timezone.utc)
    update: Dict[str, Any] = {
        "task_source_id": task_source_id,
        "last_checked_at": now,
        "last_success_at": now,
        "error_count": 0,
        "last_error": None,
    }
    if new_cursor is not None:
        update["cursor"] = new_cursor
    await ts_repo.update_task_source(update)


async def _ingest_events(
    inbox_repo: EventInboxRepository,
    task_source_id: UUID,
    events: List,
) -> Tuple[int, int]:
    """Insert events into event_inbox, returning (inserted, duplicates)."""
    inserted = 0
    duplicates = 0
    for event in events:
        dedupe = build_event_inbox_dedupe_key(task_source_id, event.external_event_id)
        create_data = EventInboxCreate(
            task_source_id=task_source_id,
            external_event_id=(event.external_event_id or "")[:255],
            dedupe_key=dedupe,
            payload=event.payload,
            status=default_event_inbox_status(),
            event_inbox_metadata={"ingested_by": "task_source_worker_v4"},
        )
        try:
            await inbox_repo.create_event_inbox(create_data)
            inserted += 1
        except HTTPException as he:
            # EventInboxRepository raises 409 on duplicate dedupe_key
            if he.status_code == 409:
                duplicates += 1
            else:
                raise
    return inserted, duplicates


@shared_task(name="task_source_worker")
def task_source_worker(
    organization_schema: str,
    task_source_id: str,
    polling_start_time: Optional[str] = None,
) -> Dict[str, Any]:
    """Poll one task source and ingest new events into event_inbox."""
    start_time = time.time()

    logger.info(
        "task_source_worker started schema=%s task_source_id=%s",
        organization_schema,
        task_source_id,
    )

    async def _execute() -> Dict[str, Any]:
        async with async_db_pool.get_session(organization_schema) as db:
            ts_uuid = UUID(task_source_id)
            ts_repo = TaskSourceRepository(db)
            conn_repo = ConnectionRepository(db)
            inbox_repo = EventInboxRepository(db)

            task_source = await ts_repo.get_task_source_by_id(ts_uuid)
            if not task_source:
                return {"status": "error", "reason": "task_source_not_found"}
            if not task_source.enabled:
                return {"status": "skipped", "reason": "disabled"}

            connection = await conn_repo.get_connection_by_id(task_source.connection_id)
            if not connection:
                return {"status": "error", "reason": "connection_not_found"}

            trigger_fn = resolve_trigger(task_source.trigger_key)
            if not trigger_fn:
                await _record_error(
                    ts_repo, ts_uuid, task_source.error_count or 0,
                    f"Unsupported trigger_key: {task_source.trigger_key}",
                )
                return {"status": "skipped", "reason": "unsupported_trigger"}

            poll_result = await trigger_fn(
                db, task_source, connection,
                polling_start_time=polling_start_time,
            )

            inserted, duplicates = await _ingest_events(
                inbox_repo, ts_uuid, poll_result.events,
            )

            new_cursor = poll_result.new_cursor or (task_source.cursor or {})
            await _record_success(ts_repo, ts_uuid, new_cursor)

            return {
                "status": "ok",
                "inserted": inserted,
                "duplicates": duplicates,
                "events_seen": len(poll_result.events),
            }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_execute())
        finally:
            # Dispose and clear cached async engines/sessions so the next
            # invocation on this forked worker creates fresh ones on its own loop.
            loop.run_until_complete(async_db_pool.dispose_all())
            async_db_pool._engines.clear()
            async_db_pool._session_factories.clear()
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

        elapsed = time.time() - start_time
        logger.info(
            "task_source_worker completed schema=%s task_source_id=%s elapsed=%.2fs status=%s",
            organization_schema, task_source_id, elapsed, result.get("status"),
        )
        return result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            "task_source_worker failed schema=%s task_source_id=%s elapsed=%.2fs error=%s",
            organization_schema, task_source_id, elapsed, str(e),
        )
        return {"status": "error", "error": str(e)}
