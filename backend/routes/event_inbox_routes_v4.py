# Custom libraries
from logger import configure_logging
from schemas.event_inbox_schema_v4 import (
    EventInboxCreate,
    EventInboxDetail,
    EventInboxResponse,
    EventInboxUpdate,
)
from schemas.user_schema import Message
from repository.event_inbox_repository_v4 import EventInboxRepository
from repository.task_source_repository_v4 import TaskSourceRepository
from utils.schema_utils import get_async_schema_db

# Database modules
from sqlalchemy.ext.asyncio import AsyncSession

# Default libraries
from typing import List, Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request


logger = configure_logging(__name__)

event_inbox_router = APIRouter(tags=["Event Inbox"])


@event_inbox_router.get("/event-inboxes", response_model=EventInboxResponse)
async def get_event_inboxes(
    keyword: Optional[str] = Query(
        None, description="Search keyword for external_event_id, dedupe_key"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: AsyncSession = Depends(get_async_schema_db),
    request: Request = None,
):
    """
    Retrieves event inbox information for all event inboxes based on specified criteria.
    """
    try:
        event_inbox_repository = EventInboxRepository(db)

        filters = request.state.filters

        event_inbox_items = await event_inbox_repository.get_all_event_inbox(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return EventInboxResponse(event_inboxes=event_inbox_items)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_event_inboxes: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@event_inbox_router.get(
    "/event-inboxes/{event_inbox_id}", response_model=EventInboxDetail
)
async def get_event_inbox(
    event_inbox_id: UUID = Path(..., description="Event Inbox UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Retrieves event inbox information based on event_inbox_id.
    """
    try:
        event_inbox_repository = EventInboxRepository(db)

        event_inbox = await event_inbox_repository.get_event_inbox_by_id(event_inbox_id)

        if event_inbox is not None:
            return EventInboxDetail.model_validate(event_inbox)
        else:
            raise HTTPException(
                status_code=404,
                detail="Event Inbox not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_event_inbox: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@event_inbox_router.post("/event-inboxes", response_model=EventInboxDetail)
async def create_event_inbox(
    event_inbox_data: EventInboxCreate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Creates a new event inbox.
    """
    try:
        # Validate task_source_id exists before create
        task_source_repository = TaskSourceRepository(db)
        task_source = await task_source_repository.get_task_source_by_id(
            event_inbox_data.task_source_id
        )
        if task_source is None:
            raise HTTPException(
                status_code=404,
                detail="Task source not found. Please check and retry.",
            )

        event_inbox_repository = EventInboxRepository(db)
        event_inbox = await event_inbox_repository.create_event_inbox(event_inbox_data)

        if event_inbox:
            logger.info(f"Event inbox created successfully: {event_inbox.id}")
            return EventInboxDetail.model_validate(event_inbox)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create event inbox.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in create_event_inbox: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@event_inbox_router.patch(
    "/event-inboxes/{event_inbox_id}", response_model=EventInboxDetail
)
async def update_event_inbox(
    event_inbox_id: UUID = Path(..., description="Event Inbox UUID"),
    event_inbox_data: EventInboxUpdate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Updates an existing event inbox based on its event_inbox_id.
    """
    try:
        event_inbox_repository = EventInboxRepository(db)

        # Get existing event inbox by id before update
        existing_event_inbox = await event_inbox_repository.get_event_inbox_by_id(
            event_inbox_id
        )
        if not existing_event_inbox:
            raise HTTPException(
                status_code=404,
                detail="Event Inbox not found. Please check and retry.",
            )

        update_data = {
            k: v for k, v in event_inbox_data.model_dump().items() if v is not None
        }
        update_data["event_inbox_id"] = event_inbox_id

        event_inbox = await event_inbox_repository.update_event_inbox(update_data)
        if event_inbox:
            logger.info(f"Event Inbox updated successfully: {event_inbox.id}")
            return EventInboxDetail.model_validate(event_inbox)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Event Inbox. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in update_event_inbox: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@event_inbox_router.delete("/event-inboxes/{event_inbox_id}", response_model=Message)
async def delete_event_inbox(
    event_inbox_id: UUID = Path(..., description="Event Inbox UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Deletes an existing event inbox based on its event_inbox_id.
    """
    try:
        event_inbox_repository = EventInboxRepository(db)

        deleted = await event_inbox_repository.delete_event_inbox(event_inbox_id)

        if deleted:
            logger.info(f"Event Inbox deleted successfully: {event_inbox_id}")
            return Message(message="Event Inbox deleted successfully.")
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Event Inbox. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in delete_event_inbox: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
