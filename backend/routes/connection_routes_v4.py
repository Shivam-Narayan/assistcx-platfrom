# Custom libraries
from logger import configure_logging
from schemas.connection_schema_v4 import (
    ConnectionCreate,
    ConnectionCredentials,
    ConnectionDetail,
    ConnectionHealthCheckResponse,
    ConnectionResponse,
    ConnectionUpdate,
)
from schemas.user_schema import Message
from repository.connection_repository_v4 import ConnectionRepository
from utils.schema_utils import get_async_schema_db
from utils.common_utils import get_current_user_async
from utils.crypto_utils import decrypt_string, encrypt_string
from utils.integration_validator_v4 import IntegrationValidatorV4
from configs.auth_schemas_v4 import AUTH_SCHEMAS

# Database modules
from sqlalchemy.ext.asyncio import AsyncSession

# Default libraries
import json
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request


logger = configure_logging(__name__)

connection_router = APIRouter(tags=["Connections"])


@connection_router.get("/connections", response_model=ConnectionResponse)
async def get_connections(
    keyword: Optional[str] = Query(
        None, description="Search keyword for name, provider_key, auth_schema_key"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: AsyncSession = Depends(get_async_schema_db),
    request: Request = None,
):
    """
    Retrieves connection information for all connections based on specified criteria.
    """
    try:
        connection_repository = ConnectionRepository(db)

        filters = request.state.filters

        connections = await connection_repository.get_all_connections(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return ConnectionResponse(connections=connections)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_connections: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.get("/connections/{connection_id}", response_model=ConnectionDetail)
async def get_connection(
    connection_id: UUID = Path(..., description="Connection UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Retrieves connection information based on connection_id.
    """
    try:
        connection_repository = ConnectionRepository(db)

        connection = await connection_repository.get_connection_by_id(connection_id)

        if connection:
            return ConnectionDetail.model_validate(connection)
        else:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_connection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.get(
    "/connections/{connection_id}/credentials",
    response_model=ConnectionCredentials,
)
async def get_connection_credentials(
    connection_id: UUID = Path(..., description="Connection UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Retrieves connection credentials information based on its connection_id.
    """
    try:
        connection_repository = ConnectionRepository(db)
        connection = await connection_repository.get_connection_by_id(connection_id)

        if not connection:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )

        encrypted_credentials = json.loads(connection.encrypted_credentials or "{}")
        decrypted_credentials = {
            key: decrypt_string(value) for key, value in encrypted_credentials.items()
        }

        auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key, {})
        connection_data = {
            "id": connection.id,
            "key": connection.provider_key,
            "preset": auth_schema.get("preset", {}),
            "credentials": decrypted_credentials,
        }
        return ConnectionCredentials(**connection_data)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_connection_credentials: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.post(
    "/connections/{connection_id}/test",
    response_model=ConnectionHealthCheckResponse,
)
async def test_connection(
    connection_id: UUID = Path(..., description="Connection UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Tests an existing connection and updates auth_status as healthy or unhealthy.
    """
    try:
        connection_repository = ConnectionRepository(db)

        connection = await connection_repository.get_connection_by_id(connection_id)
        if not connection:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )

        encrypted_credentials = json.loads(connection.encrypted_credentials or "{}")
        decrypted_credentials = {
            key: decrypt_string(value) for key, value in encrypted_credentials.items()
        }

        validator = IntegrationValidatorV4()
        is_valid, error_message = await validator.validate_credentials(
            provider_key=connection.provider_key,
            auth_schema_key=connection.auth_schema_key,
            credentials=decrypted_credentials,
        )

        auth_status = "healthy" if is_valid else "unhealthy"
        updated_connection = await connection_repository.update_connection(
            {
                "connection_id": connection_id,
                "auth_status": auth_status,
                "last_validated_at": datetime.utcnow(),
            }
        )
        if not updated_connection:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Connection. Please check and retry.",
            )

        if is_valid:
            logger.info(f"Connection health check passed: {connection_id}")
            return ConnectionHealthCheckResponse(
                id=connection_id,
                auth_status=auth_status,
                is_healthy=True,
                message="Connection is healthy.",
            )

        logger.warning(
            f"Connection health check failed for {connection_id}: {error_message}"
        )
        return ConnectionHealthCheckResponse(
            id=connection_id,
            auth_status=auth_status,
            is_healthy=False,
            message="Connection is unhealthy.",
            error=error_message,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in test_connection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.post("/connections", response_model=ConnectionDetail)
async def create_connection(
    connection_data: ConnectionCreate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
    current_user: Dict[str, Any] = Depends(get_current_user_async),
):
    """
    Creates a new connection.
    """
    try:
        user_uuid = current_user["user_uuid"]

        # Step 1: Validate credentials
        validator = IntegrationValidatorV4()
        is_valid, error_message = await validator.validate_credentials(
            provider_key=connection_data.provider_key,
            auth_schema_key=connection_data.auth_schema_key,
            credentials=connection_data.credentials,
        )

        if not is_valid:
            logger.warning(
                f"Connection validation failed for {connection_data.provider_key}: {error_message}"
            )
            raise HTTPException(
                status_code=400, detail=f"Credential validation failed: {error_message}"
            )

        logger.info(
            f"Connection credentials validated successfully for {connection_data.provider_key}"
        )

        # Step 2: Encrypt credentials
        encrypted = {}
        for key, value in connection_data.credentials.items():
            str_value = str(value) if value is not None else ""
            encrypted[key] = encrypt_string(str_value)
        encrypted_credentials_str = json.dumps(encrypted)

        # Step 3: Prepare data for storage
        data = connection_data.model_dump(exclude={"credentials"})
        data["encrypted_credentials"] = encrypted_credentials_str
        data["created_by"] = user_uuid
        data["auth_status"] = "valid"

        connection_repository = ConnectionRepository(db)
        connection = await connection_repository.create_connection(data)

        if connection:
            logger.info(f"Connection created successfully: {connection.id}")
            return ConnectionDetail.model_validate(connection)
        else:
            raise HTTPException(status_code=400, detail="Failed to create Connection.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_connection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.patch(
    "/connections/{connection_id}", response_model=ConnectionDetail
)
async def update_connection(
    connection_id: UUID = Path(..., description="Connection UUID"),
    connection_data: ConnectionUpdate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Updates an existing connection based on its connection_id.
    """
    try:
        connection_repository = ConnectionRepository(db)

        existing_connection = await connection_repository.get_connection_by_id(
            connection_id
        )
        if not existing_connection:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )

        update_data = connection_data.model_dump(exclude_unset=True)

        # If credentials are being updated, validate and encrypt them
        if "credentials" in update_data:
            credentials = update_data.pop("credentials")

            # Use provider_key and auth_schema_key from update_data if provided,
            # otherwise use existing connection values
            provider_key = update_data.get(
                "provider_key", existing_connection.provider_key
            )
            auth_schema_key = update_data.get(
                "auth_schema_key", existing_connection.auth_schema_key
            )

            # Step 1: Validate credentials
            validator = IntegrationValidatorV4()
            is_valid, error_message = await validator.validate_credentials(
                provider_key=provider_key,
                auth_schema_key=auth_schema_key,
                credentials=credentials,
            )

            if not is_valid:
                logger.warning(
                    f"Connection update validation failed for {provider_key}: {error_message}"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Credential validation failed: {error_message}",
                )

            logger.info(
                f"Connection credentials validated successfully for {provider_key}"
            )

            # Step 2: Encrypt credentials
            encrypted = {}
            for key, value in credentials.items():
                str_value = str(value) if value is not None else ""
                encrypted[key] = encrypt_string(str_value)
            update_data["encrypted_credentials"] = json.dumps(encrypted)
            update_data["auth_status"] = "valid"

        update_data["connection_id"] = connection_id

        connection = await connection_repository.update_connection(update_data)
        if connection:
            logger.info(f"Connection updated successfully: {connection.id}")
            return ConnectionDetail.model_validate(connection)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Connection. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_connection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@connection_router.delete("/connections/{connection_id}", response_model=Message)
async def delete_connection(
    connection_id: UUID = Path(..., description="Connection UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Deletes an existing connection based on its connection_id.
    """
    try:
        connection_repository = ConnectionRepository(db)

        deleted = await connection_repository.delete_connection(connection_id)

        if deleted:
            logger.info(f"Connection deleted successfully: {connection_id}")
            return Message(message="Connection deleted successfully.")
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Connection. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in delete_connection: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
