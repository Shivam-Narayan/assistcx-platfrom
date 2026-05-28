# Custom libraries
from logger import configure_logging
from schemas.activity_log_schema import (
    ActivityLogCreate,
    ActivityLogDetail,
)
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db

# Database modules
from repository.activity_log_repository import ActivityLogRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Optional, Union
from uuid import UUID
import os

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
from pydantic import Json


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

activity_log_router = APIRouter(tags=["Activity Logs"])


@activity_log_router.get("/activity-logs", response_model=List[ActivityLogDetail])
def get_activity_logs(
    filters: Optional[Json] = Query(None, description="Json-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves activity log information based on specified criteria.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        filters = request.state.filters

        return activity_log_repository.get_activity_logs(
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
        logger.error(f"Error in get_activity_logs: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.get("/activity-logs/search", response_model=List[ActivityLogDetail])
def search_activity_logs(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[Json] = Query(None, description="Json-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves activity log information based on specified criteria.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        filters = request.state.filters

        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        return activity_log_repository.search_activity_logs(
            keyword=keyword,
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
        logger.error(f"Error in search_activity_logs: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.get(
    "/entities/{entity_id}/activity-logs", response_model=List[ActivityLogDetail]
)
def get_activity_logs_by_entity(
    entity_id: UUID,
    filters: Optional[Json] = Query(None, description="Json-formatted filters"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves activity log information for a specific entity based on specified criteria.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        filters = request.state.filters

        return activity_log_repository.get_activity_logs_by_entity_id(
            entity_id=entity_id,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_activity_logs_by_entity: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.get(
    "/users/{user_id}/activity-logs", response_model=List[ActivityLogDetail]
)
def get_activity_logs_by_user(
    user_id: str,
    filters: Optional[str] = Query(None, description="Json-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves activity log information for a specific user based on specified criteria.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        filters = request.state.filters

        return activity_log_repository.get_activity_logs_by_user_id(
            user_id=user_id,
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
        logger.error(f"Error in get_activity_logs_by_user: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.get(
    "/users/{user_id}/activity-logs/search", response_model=List[ActivityLogDetail]
)
def search_activity_logs_by_user(
    user_id: str,
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[Json] = Query(None, description="Json-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves activity log information for a specific user based on specified criteria.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        filters = request.state.filters

        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        return activity_log_repository.search_activity_logs_by_user_id(
            user_id=user_id,
            keyword=keyword,
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
        logger.error(f"Error in search_activity_logs_by_user: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.get(
    "/activity-logs/{activity_log_identifier}", response_model=ActivityLogDetail
)
def get_activity_log(
    activity_log_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves activity log information based on activity_log_identifier.
    """
    try:
        activity_log_repository = ActivityLogRepository(db)

        existing_activity_log = activity_log_repository.get_activity_log_by_id(
            parse_identifier(activity_log_identifier)
        )

        if existing_activity_log:
            return ActivityLogDetail.model_validate(existing_activity_log)
        else:
            raise HTTPException(
                status_code=404,
                detail="Activity Log not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_activity_log: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@activity_log_router.post("/activity-logs", response_model=ActivityLogDetail)
def create_activity_log(
    activity_log_data: ActivityLogCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new activity log.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])

        activity_log_repository = ActivityLogRepository(db)

        activity_log = activity_log_data.model_dump()

        activity_log["user_id"] = user_uuid

        saved_activity_log = activity_log_repository.create_activity_log(activity_log)

        if saved_activity_log:
            logger.info(f"Activity Log created successfully: {saved_activity_log.id}")
            return ActivityLogDetail.model_validate(saved_activity_log)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Activity Log.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_activity_log: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
