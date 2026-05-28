# Custom libraries
from logger import configure_logging
from schemas.tag_schema import TagCreate, TagDetail, TagUpdate
from schemas.user_schema import Message
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db

# Database modules
from repository.tag_repository import TagRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union, List
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

tag_router = APIRouter(tags=["Tags"])


@tag_router.get("/tags", response_model=List[TagDetail])
def get_tags(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    try:
        tag_repository = TagRepository(db)

        filters = request.state.filters

        return tag_repository.get_all_tags(
            page=page,
            page_size=page_size,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tag_router.get("/tags/search", response_model=List[TagDetail])
def search_tags(
    keyword: str = Query(..., description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    try:
        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        tag_repository = TagRepository(db)

        filters = request.state.filters

        return tag_repository.search_tags(
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
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tag_router.get("/tags/{tag_identifier}", response_model=TagDetail)
def get_tag(
    tag_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    try:
        tag_repository = TagRepository(db)

        tag = tag_repository.get_tag_by_id(parse_identifier(tag_identifier))

        if not tag:
            raise HTTPException(
                status_code=404, detail="Tag not found. Please check and retry."
            )

        return TagDetail.model_validate(tag)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tag_router.post("/tags", response_model=TagDetail)
def create_tag(
    tag_data: TagCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    try:
        tag_repository = TagRepository(db)

        tag = tag_repository.create_tag(tag_data.model_dump())

        if not tag:
            raise HTTPException(
                status_code=400, detail="Failed to create Tag. Please check and retry."
            )

        return TagDetail.model_validate(tag)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tag_router.patch("/tags/{tag_uuid}", response_model=TagDetail)
def update_tag(
    tag_uuid: UUID,
    tag_data: TagUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    try:
        tag_repository = TagRepository(db)

        update_data = {k: v for k, v in tag_data.model_dump().items() if v is not None}
        
        update_data["tag_uuid"] = tag_uuid

        updated_tag = tag_repository.update_tag_by_id(update_data)

        if not updated_tag:
            raise HTTPException(
                status_code=404, detail="Failed to update Tag. Please check and retry."
            )

        return TagDetail.model_validate(updated_tag)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tag_router.delete("/tags/{tag_identifier}", response_model=Message)
def delete_tag(
    tag_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    try:
        tag_repository = TagRepository(db)

        deleted = tag_repository.delete_tag_by_id(parse_identifier(tag_identifier))

        if not deleted:
            raise HTTPException(
                status_code=404, detail="Failed to delete Tag. Please check and retry."
            )

        return Message(message="Tag deleted successfully.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
