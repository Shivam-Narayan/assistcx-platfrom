# Custom libraries
from logger import configure_logging
from schemas.class_group_schema import (
    ClassGroupCreate,
    ClassGroupDetail,
    ClassGroupUpdate,
)
from schemas.user_schema import Message
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db

# Database modules
from repository.class_group_repository import ClassGroupRepository
from repository.version_history_repository import VersionHistoryRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union, List
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
import os
from jwt import decode

logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

class_group_router = APIRouter(tags=["Class Groups"])


@class_group_router.get("/class-groups", response_model=List[ClassGroupDetail])
def get_class_groups(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves class group information based on specified criteria.
    """
    try:
        class_group_repository = ClassGroupRepository(db)

        filters = request.state.filters

        return class_group_repository.get_all_class_groups(
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


@class_group_router.get("/class-groups/search", response_model=List[ClassGroupDetail])
def search_class_groups(
    keyword: str = Query(..., description="Search keyword"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves class group information based on specified keyword.
    """
    try:
        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        class_group_repository = ClassGroupRepository(db)

        filters = request.state.filters

        return class_group_repository.search_class_groups(
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


@class_group_router.get(
    "/class-groups/{class_group_identifier}", response_model=ClassGroupDetail
)
def get_class_group(
    class_group_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves class group information based on class_group_identifier.
    """
    try:
        class_group_repository = ClassGroupRepository(db)

        class_group = class_group_repository.get_class_group_by_id(
            parse_identifier(class_group_identifier)
        )

        if not class_group:
            raise HTTPException(
                status_code=404, detail="Class group not found. Please check and retry."
            )

        return ClassGroupDetail.model_validate(class_group)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@class_group_router.post("/class-groups", response_model=ClassGroupDetail)
def create_class_group(
    class_group_data: ClassGroupCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new class group.
    """
    try:
        class_group_repository = ClassGroupRepository(db)

        class_group = class_group_repository.create_class_group(
            class_group_data.model_dump()
        )

        if class_group:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data for version history excluding some fields
            config_data = ClassGroupDetail.model_validate(class_group).model_dump(
                exclude={"id", "created_at", "updated_at"}
            )

            # Create a version history entry
            version_history_repository = VersionHistoryRepository(db)
            version_history = version_history_repository.create_version_history(
                {
                    "entity_type": "class_group",
                    "entity_id": class_group.id,
                    "config_data": config_data,
                    "user_id": user_id,
                }
            )
            if not version_history:
                logger.error(
                    f"Failed to create version history for class group: {class_group.id}"
                )

            logger.info(f"Class Group created successfully: {class_group.id}")
            return ClassGroupDetail.model_validate(class_group)

        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Class Group.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@class_group_router.patch(
    "/class-groups/{class_group_uuid}", response_model=ClassGroupDetail
)
def update_class_group(
    class_group_uuid: UUID,
    class_group_data: ClassGroupUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Updates an existing class group based on its class_group_uuid.
    """
    try:
        class_group_repository = ClassGroupRepository(db)

        # Get existing class group state before update
        existing_class_group = class_group_repository.get_class_group_by_id(class_group_uuid)
        if not existing_class_group:
            raise HTTPException(
                status_code=404,
                detail="Class Group not found. Please check and retry.",
            )

        # Capture old config data for comparison
        old_config_data = ClassGroupDetail.model_validate(existing_class_group).model_dump(
            exclude={"id", "created_at", "updated_at"}
        )

        # Filter out fields that are None
        update_data = {
            k: v for k, v in class_group_data.model_dump().items() if v is not None
        }

        # Append the UUID to the update data
        update_data["class_group_uuid"] = class_group_uuid

        updated_class_group = class_group_repository.update_class_group_by_id(
            update_data
        )

        if updated_class_group:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data excluding fields
            config_data = ClassGroupDetail.model_validate(
                updated_class_group
            ).model_dump(exclude={"id", "created_at", "updated_at"})

            # Only create version history if there are actual changes
            if config_data != old_config_data:
                version_history_repository = VersionHistoryRepository(db)
                version_history = version_history_repository.create_version_history(
                    {
                        "entity_type": "class_group",
                        "entity_id": updated_class_group.id,
                        "config_data": config_data,
                        "user_id": user_id,
                    }
                )
                if not version_history:
                    logger.error(
                        f"Failed to create version history for class group: {updated_class_group.id}"
                    )

            logger.info(f"Class Group updated successfully: {updated_class_group.id}")
            return ClassGroupDetail.model_validate(updated_class_group)

        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Class Group. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_class_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@class_group_router.delete(
    "/class-groups/{class_group_identifier}", response_model=Message
)
def delete_class_group(
    class_group_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing class group based on its class_group_identifier. Only allowed for ROOT user.
    """
    try:
        class_group_repository = ClassGroupRepository(db)

        deleted_class_group = class_group_repository.delete_class_group(
            parse_identifier(class_group_identifier)
        )

        if not deleted_class_group:
            raise HTTPException(status_code=404, detail="Class Group not found.")

        logger.info(f"Class Group deleted successfully: {class_group_identifier}")
        return Message(message="Class Group deleted successfully.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_class_group: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
