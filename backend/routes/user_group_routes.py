# Custom libraries
from logger import configure_logging
from schemas.user_group_schema import (
    UserGroupCreate,
    UserGroupDetail,
    UserGroupResponse,
    UserGroupUpdate,
)
from schemas.user_schema import Message
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db

# Database modules
from repository.user_group_repository import UserGroupRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

user_group_router = APIRouter(tags=["User Groups"])


@user_group_router.get("/user-groups", response_model=UserGroupResponse)
async def get_user_groups(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves user group information for all user groups based on specified criteria.
    """
    try:
        user_group_repository = UserGroupRepository(db)

        filters = request.state.filters

        # Fetch all user groups
        user_groups, total = await user_group_repository.get_user_groups(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return UserGroupResponse(user_groups=user_groups, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_user_groups: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_group_router.get("/user-groups/search", response_model=UserGroupResponse)
async def search_user_groups(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves user group information based on specified keyword.
    """
    try:
        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        user_group_repository = UserGroupRepository(db)

        filters = request.state.filters

        # Search user groups
        user_groups, total = await user_group_repository.search_user_groups(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return UserGroupResponse(user_groups=user_groups, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in search_user_groups: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_group_router.get(
    "/user-groups/{user_group_identifier}", response_model=UserGroupDetail
)
async def get_user_group(
    user_group_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves user group information based on user_group_identifier.
    """
    try:
        user_group_repository = UserGroupRepository(db)

        # Fetch a single user group by UUID
        user_group = await user_group_repository.get_user_group_by_id(
            parse_identifier(user_group_identifier)
        )

        if user_group is not None:
            return UserGroupDetail.model_validate(user_group)
        else:
            raise HTTPException(
                status_code=404,
                detail="User Group not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_user_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_group_router.post("/user-groups", response_model=UserGroupDetail)
async def create_user_group(
    user_group_data: UserGroupCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new user group.
    """
    try:
        user_group_repository = UserGroupRepository(db)

        result_user_group = await user_group_repository.create_user_group(
            user_group_data.model_dump()
        )

        if result_user_group:
            logger.info(f"User group created successfully: {result_user_group.id}")
            return UserGroupDetail.model_validate(result_user_group)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create user group.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in create_user_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_group_router.patch("/user-groups/{user_group_uuid}", response_model=UserGroupDetail)
async def update_user_group(
    user_group_uuid: UUID,
    user_group_data: UserGroupUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing user group based on its user_group_uuid.
    """
    try:
        user_group_repository = UserGroupRepository(db)

        update_data = {
            k: v for k, v in user_group_data.model_dump().items() if v is not None
        }

        # Append user_group_uuid to update_data
        update_data["user_group_uuid"] = user_group_uuid

        result_user_group = await user_group_repository.update_user_group_by_id(
            update_data
        )

        if result_user_group:
            logger.info(f"User Group updated successfully: {result_user_group.id}")
            return UserGroupDetail.model_validate(result_user_group)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update User Group. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in update_user_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@user_group_router.delete("/user-groups/{user_group_uuid}", response_model=Message)
async def delete_user_group(
    user_group_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing user group based on its user_group_uuid.
    """
    try:
        user_group_repository = UserGroupRepository(db)

        deleted_user_group = await user_group_repository.delete_user_group_by_id(
            user_group_uuid
        )

        if deleted_user_group:
            logger.info(f"User Group deleted successfully: {user_group_uuid}")
            return Message(message="User Group deleted successfully.")
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete User Group. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_user_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
