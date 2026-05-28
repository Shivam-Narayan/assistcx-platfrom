# Custom libraries
from builders.agent_builder.service import AgentBuilderService
from builders.agent_builder.schemas import AgentBuilderInput
from logger import configure_logging
from schemas.agent_schema import (
    AgentBuilder,
    AgentBuilderDetail,
    AgentCreate,
    AgentExport,
    AgentExportBase,
    AgentImport,
    AgentPreview,
    AgentPreviewResponse,
    AgentResponse,
    AgentDetail,
    AgentUpdate,
    DataStore,
    AgentArchive,
)
from schemas.user_schema import Message
from utils.common_utils import (
    get_storage_region,
    parse_identifier,
    sanitize_data_store,
    get_human_reviewers_by_uuid,
)
from utils.schema_utils import get_schema_db, get_current_schema

# Database modules
from repository.agent_repository import AgentRepository
from repository.agent_tool_repository import AgentToolRepository
from repository.data_template_repository import DataTemplateRepository
# from repository.intent_repository import IntentRepository  # intent_repository.py commented out
from repository.version_history_repository import VersionHistoryRepository
from repository.activity_log_repository import ActivityLogRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Optional, Union
from uuid import UUID
import asyncio
import os

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

agent_router = APIRouter(tags=["Agents"])


@agent_router.get("/agents", response_model=AgentResponse)
@agent_router.get("/task-api/agents", response_model=AgentResponse)
def get_agents(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent information based on specified criteria.
    """
    try:
        agent_repository = AgentRepository(db)

        filters = request.state.filters

        # Fetch all agents
        agents, total = agent_repository.get_all_agents(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return AgentResponse(agents=agents, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.get("/agents/search", response_model=AgentResponse)
@agent_router.get("/task-api/agents/search", response_model=AgentResponse)
def search_agents(
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
    Searches and retrieves agent information based on specified keyword.
    """
    try:
        agent_repository = AgentRepository(db)

        filters = request.state.filters

        # Search agents
        if keyword:
            agents, total = agent_repository.search_agents(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if agents:
                return AgentResponse(agents=agents, total=total)
            else:
                return AgentResponse(agents=[], total=0)
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


@agent_router.get("/agents/preview", response_model=AgentPreviewResponse)
def get_agent_preview(
    agent_identifier: Optional[Union[UUID, str]] = Query(
        None, description="Agent Identifier"
    ),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent preview information for an agent or all agents based on the agent_identifier.
    """
    try:
        agent_repository = AgentRepository(db)
        filters = request.state.filters

        # Inherited data filters use "agent_id" key (for AgentTask/Email models).
        # Agent model uses "id", so remap the key for agent queries.
        if filters and "agent_id" in filters:
            filters = {
                **{k: v for k, v in filters.items() if k != "agent_id"},
                "id": filters["agent_id"],
            }

        # Fetch agent previews based on the agent_identifier
        if agent_identifier:
            agent_preview = agent_repository.get_agent(
                parse_identifier(agent_identifier)
            )
            if not agent_preview:
                raise HTTPException(
                    status_code=404, detail="Agent not found. Please check and retry."
                )
            # Verify access if restricted to specific agents
            if filters and "id" in filters:
                if str(agent_preview.id) not in filters["id"]:
                    raise HTTPException(status_code=403, detail="Access denied.")
            agent_previews = [agent_preview]
        else:
            agent_previews, total = agent_repository.get_all_agents(
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        return AgentPreviewResponse(
            agent_previews=[
                AgentPreview.model_validate(agent) for agent in agent_previews
            ],
            total=total if not agent_identifier else 1,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.get("/agents/{agent_identifier}", response_model=AgentResponse)
@agent_router.get("/task-api/agents/{agent_identifier}", response_model=AgentResponse)
def get_agent(
    agent_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves agent information based on agent_identifier.
    """
    try:
        agent_repository = AgentRepository(db)

        if agent_identifier:
            # Fetch a single agent by ID
            agent = agent_repository.get_agent(parse_identifier(agent_identifier))

            if agent is not None:
                agent_detail = AgentDetail.model_validate(agent)
                agent_config = agent_detail.agent_config or {}
                human_reviewers = get_human_reviewers_by_uuid(
                    db, agent_config.get("human_review_users") or []
                )
                if human_reviewers:
                    updated_agent_config = dict(agent_config)
                    updated_agent_config["human_review_users"] = human_reviewers
                    agent_data = agent_detail.model_dump()
                    agent_data["agent_config"] = updated_agent_config
                    agent_detail = AgentDetail.model_validate(agent_data)
                agent_repository.resolve_plan_tools(agent_detail)
                tool_repo = AgentToolRepository(db)
                tools_out = []
                for t in agent_detail.tools:
                    row = tool_repo.get_agent_tool(t.action)
                    if row:
                        tools_out.append(
                            t.model_copy(
                                update={
                                    "icon": row.icon,
                                    "integration_key": row.integration_key,
                                    "is_default": bool(row.is_default),
                                }
                            )
                        )
                    else:
                        tools_out.append(t)
                agent_detail = agent_detail.model_copy(update={"tools": tools_out})
                return AgentResponse(
                    agents=[agent_detail],
                    total=1,
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Agent not found. Please check and retry.",
                )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.get("/agents/{agent_identifier}/export", response_model=AgentExportBase)
def export_agent(
    agent_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Exports an agent based on the specified agent_uuid.
    """
    try:
        agent_repository = AgentRepository(db)

        # Fetch agent using agent_identifier
        agent = agent_repository.get_agent(parse_identifier(agent_identifier))

        if agent:
            return AgentExportBase.model_validate(agent)

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


@agent_router.post("/agents", response_model=AgentDetail)
def create_agent(
    agent_data: AgentCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Creates a new agent.
    """
    try:
        if agent_data.data_store and agent_data.data_store.storage_type == "remote":
            storage_region = get_storage_region(
                db=db, data_store=agent_data.data_store.model_dump()
            )
            if storage_region:
                agent_data.data_store.storage_region = storage_region
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Unable to retrieve storage region. Please check and retry.",
                )

        agent_repository = AgentRepository(db)
        agent_tool_repository = AgentToolRepository(db)

        # Validate all agent tools associated with the agent
        missing_agent_tools = [
            tool.action
            for tool in agent_data.tools
            if not agent_tool_repository.get_agent_tool(tool.action)
        ]
        if missing_agent_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Required Agent Tools: {missing_agent_tools} not yet configured. Please check and retry.",
            )

        result_agent = agent_repository.create_agent(agent_data)

        if result_agent:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data for agent version history excluding some fields
            config_data = AgentDetail.model_validate(result_agent).model_dump(
                exclude={
                    "id",
                    "created_at",
                    "updated_at",
                }
            )

            # Create a version history for the new agent
            version_history_repository = VersionHistoryRepository(db)
            version_history = version_history_repository.create_version_history(
                {
                    "entity_type": "agent",
                    "entity_id": result_agent.id,
                    "config_data": config_data,
                    "user_id": user_id,
                }
            )
            if not version_history:
                logger.error(
                    f"Failed to create version history for agent: {result_agent.id}"
                )

            logger.info(f"Agent created successfully: {result_agent.id}")
            return AgentDetail.model_validate(result_agent)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Agent.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.put("/agents/{agent_uuid}", response_model=AgentDetail)
def update_agent(
    agent_uuid: UUID,
    agent_data: AgentUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Updates an existing agent based on its agent_uuid.
    """
    try:
        if agent_data.data_store and agent_data.data_store.storage_type == "remote":
            storage_region = get_storage_region(
                db=db, data_store=agent_data.data_store.model_dump()
            )
            if storage_region:
                agent_data.data_store.storage_region = storage_region
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Unable to retrieve storage region. Please check and retry.",
                )

        agent_repository = AgentRepository(db)
        agent_tool_repository = AgentToolRepository(db)

        # Validate all agent tools associated with the agent
        missing_agent_tools = [
            tool.action
            for tool in agent_data.tools
            if not agent_tool_repository.get_agent_tool(tool.action)
        ]
        if missing_agent_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Required Agent Tools: {missing_agent_tools} not yet configured. Please check and retry.",
            )

        # Get existing agent state before update
        existing_agent = agent_repository.get_agent(agent_uuid)
        if not existing_agent:
            raise HTTPException(
                status_code=404,
                detail="Agent not found. Please check and retry.",
            )

        # Capture old config data for comparison
        old_config_data = AgentDetail.model_validate(existing_agent).model_dump(
            exclude={"id", "created_at", "updated_at"}
        )

        update_data = agent_data.model_dump()

        # Append agent_uuid to update_data
        update_data["agent_uuid"] = agent_uuid

        result_agent = agent_repository.update_agent(update_data)

        if result_agent:
            user = getattr(request.state, "user_id", None)
            user_id = UUID(user) if isinstance(user, str) else user

            # Prepare config data for agent version history excluding some fields
            config_data = AgentDetail.model_validate(result_agent).model_dump(
                exclude={
                    "id",
                    "created_at",
                    "updated_at",
                }
            )

            # Only create version history if there are actual changes
            if config_data != old_config_data:
                version_history_repository = VersionHistoryRepository(db)
                version_history = version_history_repository.create_version_history(
                    {
                        "entity_type": "agent",
                        "entity_id": result_agent.id,
                        "config_data": config_data,
                        "user_id": user_id,
                    }
                )
                if not version_history:
                    logger.error(
                        f"Failed to create version history for agent: {result_agent.id}"
                    )

            logger.info(f"Agent updated successfully: {result_agent.id}")
            return AgentDetail.model_validate(result_agent)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Agent. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.post("/agents/import", response_model=Message)
def import_agent(
    agent_data: AgentImport = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Imports an agent along with its associated data templates.
    """
    try:
        agent_repository = AgentRepository(db)
        # intent_repository = IntentRepository(db)
        data_template_repository = DataTemplateRepository(db)
        agent_tool_repository = AgentToolRepository(db)

        # Sanitize and update agent data_store, resolving the storage_region if remote
        if agent_data.agent and agent_data.agent.data_store:
            data_store = sanitize_data_store(agent_data.agent.data_store.model_dump())
            agent_data.agent.data_store = DataStore(**data_store)

            if agent_data.agent.data_store.storage_type == "remote":
                storage_region = get_storage_region(
                    db=db, data_store=agent_data.agent.data_store.model_dump()
                )
                if storage_region:
                    agent_data.agent.data_store.storage_region = storage_region
                else:
                    raise HTTPException(
                        status_code=422,
                        detail="Unable to retrieve storage region. Please check and retry.",
                    )

        # Validate all agent tools associated with the agent
        missing_agent_tools = [
            tool.action
            for tool in agent_data.agent.tools
            if not agent_tool_repository.get_agent_tool(tool.action)
        ]
        if missing_agent_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Required Agent Tools not yet configured. Please check and retry.",
            )

        # # Create intent associated with the agent if it not exists (IntentRepository commented out)
        # if agent_data.intent:
        #     intent = intent_repository.get_intent(agent_data.intent.intent_class)
        #     if not intent:
        #         intent_repository.create_intent(agent_data.intent)

        # Create data templates associated with the agent if it does not exist
        if agent_data.data_templates:
            for template in agent_data.data_templates:
                data_template = data_template_repository.get_template(
                    template.template_class
                )
                if not data_template:
                    data_template_repository.create_template(template)

        # Create agent
        agent = agent_repository.create_agent(agent_data.agent)

        if agent:
            # Extract user from token
            decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
            user_id = UUID(decoded_token["sub"])

            # Prepare config data for agent version history excluding some fields
            config_data = AgentDetail.model_validate(agent).model_dump(
                exclude={
                    "id",
                    "created_at",
                    "updated_at",
                }
            )

            # Create a version history for the imported agent
            version_history_repository = VersionHistoryRepository(db)
            version_history = version_history_repository.create_version_history(
                {
                    "entity_type": "agent",
                    "entity_id": agent.id,
                    "config_data": config_data,
                    "user_id": user_id,
                }
            )
            if not version_history:
                logger.error(f"Failed to create version history for agent: {agent.id}")

            logger.info(f"Agent imported successfully: {agent.id}")
            return {"message": f"Agent {agent.name} imported successfully."}

        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to import Agent.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.post("/agents/build", response_model=AgentBuilderDetail)
def build_agent(
    agent_data: AgentBuilder = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Generates agent configuration based on business use case and tools.
    """
    try:
        agent_tool_repository = AgentToolRepository(db)

        # Validate all agent tools
        tools_data = []
        missing_tools = []
        for tool in agent_data.tools:
            db_tool = agent_tool_repository.get_agent_tool(tool.action)
            if not db_tool:
                missing_tools.append(tool.action)
            else:
                tools_data.append(
                    {
                        "name": db_tool.name,
                        "action": db_tool.action,
                        "description": db_tool.description,
                    }
                )

        if missing_tools:
            raise HTTPException(
                status_code=400,
                detail=f"Required Agent Tools: {missing_tools} not yet configured. Please check and retry.",
            )

        organization_schema = get_current_schema(db)

        # Log tool count for plan generation decision
        tool_count = len(tools_data)

        agent_builder_service = AgentBuilderService(organization_schema, db)
        result_agent = asyncio.run(
            agent_builder_service.generate_agent_config(
                AgentBuilderInput(
                    name=agent_data.name,
                    business_usecase=agent_data.business_usecase,
                    previous_config=agent_data.previous_config,
                    user_instructions=agent_data.user_instructions,
                    tools=tools_data,
                )
            )
        )

        if result_agent:
            return AgentBuilderDetail.model_validate(result_agent)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to build Agent.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in build_agent: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.post("/agents/archive", response_model=Message)
def archive_agents(
    archive_data: AgentArchive = Body(...),
    db=Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Archives multiple existing agents based on their agent_ids and logs the activity.
    """
    try:
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_id = UUID(decoded_token["sub"])

        if not archive_data.agent_ids:
            raise HTTPException(status_code=400, detail="No agents provided.")

        agent_repository = AgentRepository(db)
        activity_log_repository = ActivityLogRepository(db)

        archived_count = 0
        for agent_id in archive_data.agent_ids:
            archived_agent = agent_repository.archive_agent_by_id(agent_id)
            if archived_agent:
                archived_count += 1
                activity_log_data = {
                    "user_id": user_id,
                    "entity_type": "agent",
                    "entity_id": agent_id,
                    "activity_type": "agent_archive",
                    "previous_state": {"status": ""},
                    "new_state": {"status": "ARCHIVED"},
                    "note": (
                        archive_data.note if hasattr(archive_data, "note") else None
                    ),
                }
                activity_log_repository.create_activity_log(activity_log_data)
                logger.info(f"Agent {agent_id} archived by user {user_id}.")

        if archived_count > 0:
            logger.info(
                f"{archived_count} of {len(archive_data.agent_ids)} Agents archived successfully."
            )
            return {
                "message": f"{archived_count} of {len(archive_data.agent_ids)} Agents archived successfully."
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to archive Agents. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in archive_agents: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_router.delete("/agents/{agent_identifier}", response_model=Message)
def delete_agent(
    agent_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing agent based on its agent_identifier. Only allowed for root user.
    """
    try:
        agent_repository = AgentRepository(db)

        deleted_agent = agent_repository.delete_agent(
            parse_identifier(agent_identifier)
        )

        if deleted_agent:
            logger.info(f"Agent deleted successfully: {agent_identifier}")
            return {"message": "Agent deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Agent. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_agent: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
