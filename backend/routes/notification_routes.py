# Custom libraries
import logging

# Database modules
from utils.schema_utils import get_schema_db
from schemas.notification_schema import (
    NotificationCreate,
    NotificationUpdate,
    NotificationDetail,
)
from schemas.user_schema import Message
from repository.notification_repository import NotificationRepository

# Default libraries
from typing import List, Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

notification_router = APIRouter(tags=["Notifications"])


@notification_router.get(
    "/notifications/recipient/{recipient_id}", response_model=List[NotificationDetail]
)
def get_all_notifications_by_recipient_id(
    recipient_id: str = Path(..., description="Recipient ID"),
    page: int = Query(1, description="Page number", ge=1),
    page_size: int = Query(10, description="Items per page", ge=1, le=100),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    filters: Optional[str] = Query(None, description="Optional filter string"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves all notifications for a recipient using optional filters, sorting, and pagination.
    """
    try:
        notification_repository = NotificationRepository(db=db)

        filters = request.state.filters

        return notification_repository.get_all_notifications(
            recipient_id=recipient_id,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@notification_router.get(
    "/notifications/search", response_model=List[NotificationDetail]
)
def search_notifications(
    keyword: Optional[str] = Query(None, description="Search keyword"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    try:
        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        notification_repository = NotificationRepository(db)
        return notification_repository.search_notifications(
            keyword=keyword,
            filters=request.state.filters,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@notification_router.get(
    "/notifications/{notification_id}", response_model=NotificationDetail
)
def get_notification_by_id(notification_id: UUID, db: Session = Depends(get_schema_db)):
    """
    Retrieve a notification by its ID.
    """
    try:
        notification_repository = NotificationRepository(db)
        notification = notification_repository.get_notification_by_id(notification_id)

        if notification:
            return notification
        else:
            raise HTTPException(
                status_code=404,
                detail="Notification not found. Please check and retry",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error

    except Exception as e:
        logger.error(f"Error in get_notification_by_id: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@notification_router.post("/notifications", response_model=NotificationDetail)
def create_notification(
    notification: NotificationCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new notification.
    """
    try:
        notification_repository = NotificationRepository(db)

        saved_notification = notification_repository.create_notification(
            notification.model_dump()
        )

        if saved_notification:
            logger.info(f"Notification created successfully: {saved_notification.id}")
            return saved_notification
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create notification. Plase check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error

    except Exception as e:
        logger.error(f"Error in create_notification: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@notification_router.patch(
    "/notifications/{notification_id}", response_model=NotificationDetail
)
def update_notification(
    notification_id: UUID,
    update_data: NotificationUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    try:
        notification_repository = NotificationRepository(db)

        # Convert Pydantic update_data to dict here
        update_dict = update_data.model_dump()

        result = notification_repository.update_notification(
            notification_id, update_dict
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Notification not found. Please check and retry.",
            )

        return NotificationDetail.model_validate(result)

    except HTTPException as http_err:
        logger.error(f"HTTPException: {http_err.detail}")
        raise http_err

    except Exception as e:
        logger.error(f"Unexpected error during notification update: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@notification_router.delete("/notifications/{notification_id}", response_model=Message)
def delete_notification(notification_id: UUID, db: Session = Depends(get_schema_db)):
    try:
        notification_repository = NotificationRepository(db)
        success = notification_repository.delete_notification(notification_id)
        if not success:
            raise HTTPException(
                status_code=404, detail="Notification not found or delete failed."
            )
        return Message(message="Notification deleted successfully.")
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred during delete_notification: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
