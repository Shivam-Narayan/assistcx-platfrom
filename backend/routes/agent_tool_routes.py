# Custom libraries
from configs.agent_tools_data import AGENT_TOOLS_INTEGRATIONS
from logger import configure_logging
from schemas.agent_tool_schema import (
    AgentToolBulkUpdate,
    AgentToolCreate,
    AgentToolDetail,
    AgentToolResponse,
    AgentToolUpdate,
    AgentToolFilters,
)
from schemas.user_schema import Message
from utils.common_utils import parse_identifier
from utils.schema_utils import get_schema_db
from agents.shared_utils.tools_factory import ToolsFactory

# Database modules
from repository.agent_tool_repository import AgentToolRepository
from repository.agent_repository import AgentRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union, List, Dict, Any
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request


logger = configure_logging(__name__)

agent_tool_router = APIRouter(tags=["Agent Tools"])


@agent_tool_router.get("/agent-tools", response_model=AgentToolResponse)
def get_agent_tools(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent tool information based on specified criteria.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        filters = request.state.filters

        # Fetch all agent tools
        agent_tools, total = agent_tool_repository.get_all_agent_tools(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return AgentToolResponse(agent_tools=agent_tools, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.get("/agent-tools/search", response_model=AgentToolResponse)
def search_agent_tools(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves agent tool information based on specified keyword.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        filters = request.state.filters

        # Search agent tools
        if keyword:
            agent_tools, total = agent_tool_repository.search_agent_tools(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if agent_tools:
                return AgentToolResponse(agent_tools=agent_tools, total=total)
            else:
                return AgentToolResponse(agent_tools=[], total=0)
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.get("/agent-tools/filters", response_model=AgentToolFilters)
def get_agent_tool_filters(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent tool integrations information for filters.
    """
    try:
        return {"integrations": AGENT_TOOLS_INTEGRATIONS}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Unhandled error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_tool_router.get(
    "/agent-tools/{agent_tool_identifier}", response_model=AgentToolDetail
)
def get_agent_tool(
    agent_tool_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves agent tool information based on agent_tool_identifier
    and includes input/tool_call parameter schemas.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        # Check if agent tool exists using agent_tool_identifier
        existing_agent_tool = agent_tool_repository.get_agent_tool(
            parse_identifier(agent_tool_identifier)
        )

        if not existing_agent_tool:
            raise HTTPException(
                status_code=404,
                detail="Agent Tool not found. Please check and retry.",
            )

        # Create minimal runtime context (only needed for schema extraction)
        tool_runtime_context = {}
        tool_generator = ToolsFactory(tool_runtime_context)

        # Convert model to dict - Pass ALL fields from AgentToolDetail schema
        tool_data_dict = AgentToolDetail.model_validate(
            existing_agent_tool
        ).model_dump()

        # Generate StructuredTool instance
        structured_tool = tool_generator.generate(tool_data_dict)

        # Extract input/output schemas
        tool_schemas = ToolsFactory.get_tool_schemas(structured_tool)

        # Add schemas to the response
        agent_tool_detail_data = AgentToolDetail.model_validate(existing_agent_tool)
        agent_tool_detail_data_dict = agent_tool_detail_data.model_dump()

        agent_tool_detail_data_dict["input_schema"] = tool_schemas.get("args", {})
        agent_tool_detail_data_dict["tool_call_schema"] = tool_schemas.get(
            "tool_call_schema", {}
        )

        return AgentToolDetail.model_validate(agent_tool_detail_data_dict)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_agent_tool: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@agent_tool_router.get(
    "/agents/{agent_uuid}/agent-tools", response_model=AgentToolResponse
)
def get_agent_tools_for_agent(
    agent_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Gets all agent tools for a given agent.
    """
    try:
        agent_repository = AgentRepository(db)
        agent = agent_repository.get_agent(agent_uuid)

        if agent is not None:
            agent_tool_repository = AgentToolRepository(db)
            agent_tools = agent_tool_repository.get_agent_tools_by_agent_id(agent_uuid)
            return AgentToolResponse(agent_tools=agent_tools, total=len(agent_tools))
        else:
            raise HTTPException(
                status_code=404,
                detail="Agent not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.post("/agent-tools/{agent_tool_identifier}/test")
def test_agent_tool(
    agent_tool_identifier: Union[UUID, str] = None,
    parameters: Dict[str, Any] = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Tests an agent tool by invoking it with the provided parameters.
    Returns the raw result from the tool execution.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        # Check if agent tool exists using agent_tool_identifier
        existing_agent_tool = agent_tool_repository.get_agent_tool(
            parse_identifier(agent_tool_identifier)
        )

        if not existing_agent_tool:
            raise HTTPException(
                status_code=404,
                detail="Agent Tool not found. Please check and retry.",
            )

        # Create minimal runtime context for tool generation
        tool_runtime_context = {}
        tool_generator = ToolsFactory(tool_runtime_context)

        # Convert model to dict
        tool_data_dict = AgentToolDetail.model_validate(
            existing_agent_tool
        ).model_dump()

        # Generate StructuredTool instance
        structured_tool = tool_generator.generate(tool_data_dict)

        # Invoke the tool with provided parameters
        logger.info(
            f"Testing tool '{structured_tool.name}' with parameters: {parameters}"
        )

        # Invoke the tool synchronously and return raw result
        result = structured_tool.invoke(parameters)

        logger.info(f"Tool test successful for '{structured_tool.name}'")

        return result

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in test_agent_tool: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.post("/agent-tools", response_model=AgentToolDetail)
def create_agent_tool(
    agent_tool_data: AgentToolCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new agent tool.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        saved_agent_tool = agent_tool_repository.create_agent_tool(
            agent_tool_data.model_dump()
        )

        if saved_agent_tool:
            logger.info(f"Agent Tool created successfully: {saved_agent_tool.id}")
            return saved_agent_tool
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Agent Tool.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_agent_tool: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.patch(
    "/agent-tools/{agent_tool_uuid}", response_model=AgentToolDetail
)
def update_agent_tool(
    agent_tool_uuid: UUID,
    agent_tool_data: AgentToolUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing agent tool based on its agent_tool_uuid.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        agent_tool_data = {
            k: v for k, v in agent_tool_data.model_dump().items() if v is not None
        }

        # Append agent_tool_uuid to update_data
        agent_tool_data["agent_tool_uuid"] = agent_tool_uuid

        updated_agent_tool = agent_tool_repository.update_agent_tool_by_id(
            agent_tool_data
        )

        if updated_agent_tool:
            logger.info(f"Agent Tool updated successfully: {updated_agent_tool.id}")
            return AgentToolDetail.model_validate(updated_agent_tool)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Agent Tool. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_agent_tool: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.post("/agent-tools/bulk/{action}", response_model=AgentToolResponse)
def bulk_update_agent_tools(
    action: str = Path(..., description="Action to perform: 'enable' or 'disable'"),
    agent_tool_data: AgentToolBulkUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Bulk enable or disable agent tools based on the action specified in the path.
    """
    if action not in ["enable", "disable"]:
        raise HTTPException(status_code=400, detail="Not Found")

    if not agent_tool_data.agent_tool_ids:
        raise HTTPException(status_code=400, detail="No agent tools provided.")

    is_enabled = action == "enable"

    try:
        agent_tool_repository = AgentToolRepository(db)
        updated_agent_tools = []

        for identifier in agent_tool_data.agent_tool_ids:
            update_data = {
                "agent_tool_uuid": identifier,
                "is_enabled": is_enabled,
            }
            updated_agent_tool = agent_tool_repository.update_agent_tool_by_id(
                update_data
            )
            if updated_agent_tool:
                updated_agent_tools.append(updated_agent_tool)

        if updated_agent_tools:
            return AgentToolResponse(
                agent_tools=updated_agent_tools, total=len(updated_agent_tools)
            )
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Agent Tool. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_tool_router.delete(
    "/agent-tools/{agent_tool_identifier}", response_model=Message
)
def delete_agent_tool(
    agent_tool_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing agent tool based on its agent_tool_uuid. Only allowed for root user.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        deleted_agent_tool = agent_tool_repository.delete_agent_tool(
            parse_identifier(agent_tool_identifier)
        )

        if deleted_agent_tool:
            logger.info(f"Agent Tool deleted successfully: {agent_tool_identifier}")
            return {"message": "Agent Tool deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Agent Tool. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_agent_tool: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")




# Deprecated
# @agent_tool_router.get("/v1/agent-tools", response_model=AgentToolResponse)
# def get_paginated_agent_tools(
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("created_at", description="Field to sort by"),
#     sort_order: str = Query("asc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves paginated agent tool information based on specified criteria.
#     """
#     try:
#         agent_tool_repository = AgentToolRepository(db)

#         filters = request.state.filters

#         # Fetch all agent tools
#         agent_tools, total = agent_tool_repository.paginated_get_all_agent_tools(
#             page=page,
#             page_size=page_size,
#             filters=filters,
#             sort_by=sort_by,
#             sort_order=sort_order,
#         )

#         return AgentToolResponse(agent_tools=agent_tools, total=total)

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @agent_tool_router.get("/v1/agent-tools-search", response_model=AgentToolResponse)
# def search_paginated_agent_tools(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated agent tool information based on specified keyword.
#     """
#     try:
#         agent_tool_repository = AgentToolRepository(db)

#         filters = request.state.filters

#         # Search agent tools
#         if keyword:
#             agent_tools, total = agent_tool_repository.paginated_search_agent_tool(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if agent_tools:
#                 return AgentToolResponse(agent_tools=agent_tools, total=total)
#             else:
#                 return AgentToolResponse(agent_tools=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @agent_tool_router.get("/agent-tools/search", response_model=AgentToolResponse)
# def search_agent_tools(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves agent tool information based on specified keyword.
#     """
#     try:
#         agent_tool_repository = AgentToolRepository(db)

#         filters = request.state.filters

#         # Search agent tools
#         if keyword:
#             agent_tools, total = agent_tool_repository.search_agent_tool(
#                 keyword=keyword,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if agent_tools:
#                 return AgentToolResponse(agent_tools=agent_tools, total=total)
#             else:
#                 return AgentToolResponse(agent_tools=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @agent_tool_router.get("/v1/agent-tools/search", response_model=AgentToolResponse)
# def search_paginated_agent_tools(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated agent tool information based on specified keyword.
#     """
#     try:
#         agent_tool_repository = AgentToolRepository(db)

#         filters = request.state.filters

#         # Search agent tools
#         if keyword:
#             agent_tools, total = agent_tool_repository.paginated_search_agent_tool(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if agent_tools:
#                 return AgentToolResponse(agent_tools=agent_tools, total=total)
#             else:
#                 return AgentToolResponse(agent_tools=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
