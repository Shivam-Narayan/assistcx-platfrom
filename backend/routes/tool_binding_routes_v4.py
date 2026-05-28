# Custom libraries
from logger import configure_logging
from schemas.tool_binding_schema_v4 import (
    ToolBindingCreate,
    ToolBindingDetail,
    ToolBindingResponse,
    ToolBindingUpdate,
)
from schemas.user_schema import Message
from repository.tool_binding_repository_v4 import ToolBindingRepository
from repository.connection_repository_v4 import ConnectionRepository
from utils.schema_utils import get_async_schema_db

# Database modules
from models.agent import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Default libraries
from uuid import UUID
from typing import Optional

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request


logger = configure_logging(__name__)

tool_binding_router = APIRouter(tags=["Tool Bindings"])


@tool_binding_router.get("/tool-bindings", response_model=ToolBindingResponse)
async def get_tool_bindings(
    keyword: Optional[str] = Query(
        None, description="Search keyword for provider_key, tool_key"
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
    Retrieves tool binding information for all tool bindings based on specified criteria.
    """
    try:
        tool_binding_repository = ToolBindingRepository(db)

        filters = request.state.filters

        bindings = await tool_binding_repository.get_all_tool_bindings(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return ToolBindingResponse(tool_bindings=bindings)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_tool_bindings: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tool_binding_router.get(
    "/tool-bindings/{tool_binding_id}", response_model=ToolBindingDetail
)
async def get_tool_binding(
    tool_binding_id: UUID = Path(..., description="Tool Binding UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Retrieves tool binding information based on tool_binding_id.
    """
    try:
        tool_binding_repository = ToolBindingRepository(db)

        binding = await tool_binding_repository.get_tool_binding_by_id(tool_binding_id)

        if binding:
            return ToolBindingDetail.model_validate(binding)
        else:
            raise HTTPException(
                status_code=404,
                detail="Tool Binding not found. Please check and retry.",
            )
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_tool_binding: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tool_binding_router.post("/tool-bindings", response_model=ToolBindingDetail)
async def create_tool_binding(
    data: ToolBindingCreate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Creates a new tool binding.
    """
    try:
        # Validate connection_id exists before create
        connection_repository = ConnectionRepository(db)
        connection = await connection_repository.get_connection_by_id(
            data.connection_id
        )
        if connection is None:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )
        # Validate agent_id exists before create (async query; AgentRepository is sync)
        result = await db.execute(select(Agent).where(Agent.id == data.agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(
                status_code=404,
                detail="Agent not found. Please check and retry.",
            )

        tool_binding_repository = ToolBindingRepository(db)
        binding = await tool_binding_repository.create_tool_binding(data)

        if binding:
            logger.info(f"Tool binding created successfully: {binding.id}")
            return ToolBindingDetail.model_validate(binding)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create tool binding.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in create_tool_binding: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tool_binding_router.patch(
    "/tool-bindings/{tool_binding_id}", response_model=ToolBindingDetail
)
async def update_tool_binding(
    tool_binding_id: UUID = Path(..., description="Tool Binding UUID"),
    data: ToolBindingUpdate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Updates an existing tool binding based on its tool_binding_id.
    """
    try:
        # Validate connection_id if provided
        if data.connection_id is not None:
            connection_repository = ConnectionRepository(db)
            connection = await connection_repository.get_connection_by_id(
                data.connection_id
            )
            if connection is None:
                raise HTTPException(
                    status_code=404,
                    detail="Connection not found. Please check and retry.",
                )
        # Validate agent_id if provided
        if data.agent_id is not None:
            result = await db.execute(select(Agent).where(Agent.id == data.agent_id))
            agent = result.scalar_one_or_none()
            if agent is None:
                raise HTTPException(
                    status_code=404,
                    detail="Agent not found. Please check and retry.",
                )
        tool_binding_repository = ToolBindingRepository(db)

        # Get existing tool binding by id before update
        existing_binding = await tool_binding_repository.get_tool_binding_by_id(
            tool_binding_id
        )
        if not existing_binding:
            raise HTTPException(
                status_code=404,
                detail="Tool Binding not found. Please check and retry.",
            )

        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        update_data["tool_binding_id"] = tool_binding_id

        binding = await tool_binding_repository.update_tool_binding(update_data)
        if binding:
            logger.info(f"Tool Binding updated successfully: {binding.id}")
            return ToolBindingDetail.model_validate(binding)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Tool Binding. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in update_tool_binding: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@tool_binding_router.delete("/tool-bindings/{tool_binding_id}", response_model=Message)
async def delete_tool_binding(
    tool_binding_id: UUID = Path(..., description="Tool Binding UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Deletes an existing tool binding based on its tool_binding_id.
    """
    try:
        tool_binding_repository = ToolBindingRepository(db)

        deleted = await tool_binding_repository.delete_tool_binding(tool_binding_id)

        if deleted:
            logger.info(f"Tool Binding deleted successfully: {tool_binding_id}")
            return Message(message="Tool Binding deleted successfully.")
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Tool Binding. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in delete_tool_binding: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
