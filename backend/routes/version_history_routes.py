# Custom libraries
from logger import configure_logging
from schemas.version_history_schema import (
    VersionHistoryDetail,
)
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db

# Database modules
from repository.version_history_repository import VersionHistoryRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Optional, Union
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

version_history_router = APIRouter(tags=["Version History"])


@version_history_router.get(
    "/version-histories", response_model=List[VersionHistoryDetail]
)
def get_version_histories(
    filters: Optional[str] = Query(None, description="Json-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves version history information for all version histories.
    """
    try:
        version_history_repository = VersionHistoryRepository(db)

        filters = request.state.filters

        return version_history_repository.get_version_histories(
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
        logger.error(f"Error in get_version_histories: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@version_history_router.get(
    "/version-histories/{version_history_identifier}",
    response_model=VersionHistoryDetail,
)
def get_version_history(
    version_history_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves version history information based on version_history_identifier.
    """
    try:
        version_history_repository = VersionHistoryRepository(db)

        version_history = version_history_repository.get_version_history_by_id(
            parse_identifier(version_history_identifier)
        )

        if version_history:
            return VersionHistoryDetail.model_validate(version_history)
        else:
            raise HTTPException(
                status_code=404,
                detail="Version History not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_version_history: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
