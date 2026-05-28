# Custom libraries
from logger import configure_logging
from schemas.api_key_schema import (
    ApiKeyCreate,
    ApiKeyDetail,
    ApiKeyUpdate,
)
from schemas.user_schema import Message
from utils.api_key_authentication import APIKeyAuthentication
from utils.common_utils import parse_identifier
from utils.schema_utils import get_current_schema, get_schema_db

# Database modules
from repository.api_key_repository import ApiKeyRepository
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

api_key_router = APIRouter(tags=["api keys"])


@api_key_router.get("/api-keys", response_model=List[ApiKeyDetail])
def get_api_keys(
    filters: Optional[Json] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(
        None, ge=1, le=100, description="Number of items per page"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves API key information based on specified criteria.
    """
    try:
        api_key_repository = ApiKeyRepository(db)

        filters = request.state.filters

        return api_key_repository.get_api_keys(
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
        logger.error(f"Error in get_api_keys: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@api_key_router.get("/api-keys/search", response_model=List[ApiKeyDetail])
def search_api_keys(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[Json] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(
        None, ge=1, le=100, description="Number of items per page"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves API key information based on specified keyword.
    """
    try:
        api_key_repository = ApiKeyRepository(db)

        filters = request.state.filters

        if not keyword:
            raise HTTPException(status_code=400, detail="No keyword provided.")

        return api_key_repository.search_api_keys(
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
        logger.error(f"Error in search_api_keys: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@api_key_router.get("/api-keys/{api_key_identifier}", response_model=ApiKeyDetail)
def get_api_key(
    api_key_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves API key information based on api_key_identifier.
    """
    try:
        api_key_repository = ApiKeyRepository(db)

        api_key = api_key_repository.get_api_key_by_id(
            parse_identifier(api_key_identifier)
        )

        if api_key:
            return ApiKeyDetail.model_validate(api_key)
        else:
            raise HTTPException(
                status_code=404,
                detail="API Key not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_api_key: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@api_key_router.post("/api-keys", response_model=ApiKeyDetail)
def create_api_key(
    api_key_data: ApiKeyCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new API key.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])
        user_role = decoded_token["user_role"]

        if user_role == "ROOT":
            user_uuid = None
        
        # Get current organization schema
        organization_schema = get_current_schema(db)

        api_key_authentication = APIKeyAuthentication()

        # Generate API Key
        generated_api_key = api_key_authentication.generate_api_key(organization_schema)

        # Generate API Key Hint
        api_key_hint = api_key_authentication.generate_api_key_hint(generated_api_key)

        # Generate API Key Hash
        api_key_hash = api_key_authentication.generate_api_key_hash(generated_api_key)

        api_key_repository = ApiKeyRepository(db)

        api_key_data = api_key_data.model_dump()

        api_key_data["user_id"] = user_uuid
        api_key_data["key_hint"] = api_key_hint
        api_key_data["key_hash"] = api_key_hash

        saved_api_key = api_key_repository.create_api_key(api_key_data)

        if saved_api_key:
            saved_api_key.api_key = generated_api_key
            logger.info(f"API Key created successfully: {saved_api_key.id}")
            return ApiKeyDetail.model_validate(saved_api_key)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create API Key.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_api_key: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@api_key_router.patch("/api-keys/{api_key_uuid}", response_model=ApiKeyDetail)
def update_api_key(
    api_key_uuid: UUID,
    api_key_data: ApiKeyUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing API key based on its api_key_uuid.
    """
    try:
        api_key_repository = ApiKeyRepository(db)

        update_data = {
            k: v for k, v in api_key_data.model_dump().items() if v is not None
        }

        # Append api_key_uuid to update_data
        update_data["api_key_uuid"] = api_key_uuid

        updated_api_key = api_key_repository.update_api_key(update_data)

        if updated_api_key:
            logger.info(f"API Key updated successfully: {updated_api_key.id}")
            return ApiKeyDetail.model_validate(updated_api_key)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update API Key. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in update_api_key: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@api_key_router.delete("/api-keys/{api_key_identifier}", response_model=Message)
def delete_api_key(
    api_key_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an API key based on api_key_identifier.
    """
    try:
        api_key_repository = ApiKeyRepository(db)

        deleted_api_key = api_key_repository.delete_api_key_by_id(
            parse_identifier(api_key_identifier)
        )

        if not deleted_api_key:
            raise HTTPException(status_code=404, detail="API Key not found.")

        return Message(message="API Key deleted successfully.")

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_api_key: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
