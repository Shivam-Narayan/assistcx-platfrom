# Custom libraries
from logger import configure_logging
from schemas.agent_output_schema import AgentOutputResponse, AgentOutputUsageResponse
from utils.common_utils import transform_agent_actions
from utils.schema_utils import get_schema_db

# Database modules
from repository.agent_output_repository import AgentOutputRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional
from uuid import UUID
import json

# Installed libraries
from fastapi import APIRouter, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

agent_output_router = APIRouter(tags=["Agent Outputs"])


@agent_output_router.get(
    "/task-outputs/{agent_task_uuid}", response_model=AgentOutputResponse
)
@agent_output_router.get(
    "/task-api/task-outputs/{agent_task_uuid}", response_model=AgentOutputResponse
)
def get_agent_output_by_agent_task(
    agent_task_uuid: UUID,
    agent_output_uuid: Optional[UUID] = Query(None, description="Agent Output UUID"),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves task output information for a specific agent task.
    """
    try:
        agent_output_repository = AgentOutputRepository(db)

        # Fetch agent output for an agent task
        agent_output_details = (
            agent_output_repository.get_agent_output_by_id(agent_output_uuid)
            if agent_output_uuid
            else agent_output_repository.get_agent_output_by_agent_task(agent_task_uuid)
        )

        if agent_output_details.get("agent_output"):
            # Transform agent_actions using the helper function
            return AgentOutputResponse(
                agent_outputs=[
                    transform_agent_actions(agent_output_details["agent_output"])
                ],
                attempts=agent_output_details["attempts"],
                total=agent_output_details["total"],
            )
        else:
            raise HTTPException(
                status_code=404,
                detail="Agent output not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_output_router.get(
    "/task-outputs/{agent_task_uuid}/usage",
    response_model=AgentOutputUsageResponse,
)
@agent_output_router.get(
    "/task-api/task-outputs/{agent_task_uuid}/usage",
    response_model=AgentOutputUsageResponse,
)
def get_agent_output_usage_by_agent_task(
    agent_task_uuid: UUID,
    agent_output_uuid: Optional[UUID] = Query(None, description="Agent Output UUID"),
    db: Session = Depends(get_schema_db),
):
    """
    Credits and token usage for the latest output of a task, or for a specific output when agent_output_uuid is given.
    Resolution matches GET /task-outputs/{agent_task_uuid}.
    """
    try:
        agent_output_repository = AgentOutputRepository(db)

        agent_output_details = (
            agent_output_repository.get_agent_output_by_id(agent_output_uuid)
            if agent_output_uuid
            else agent_output_repository.get_agent_output_by_agent_task(agent_task_uuid)
        )

        row = agent_output_details.get("agent_output")
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Agent output not found. Please check and retry.",
            )

        return AgentOutputUsageResponse(
            agent_task_uuid=agent_task_uuid,
            agent_output_uuid=row.id,
            credits_used=row.credits_used,
            token_usage=row.token_usage,
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_output_router.get(
    "/agent-outputs/{agent_task_uuid}/{agent_uuid}", response_model=AgentOutputResponse
)
def get_agent_outputs_by_agent_task_and_agent(
    agent_task_uuid: UUID,
    agent_uuid: Optional[UUID],
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent output information for a specific agent task and agent based on specified criteria.
    """
    try:
        agent_output_repository = AgentOutputRepository(db)

        filters = request.state.filters

        # Fetch all agent outputs for an agent task
        agent_outputs = agent_output_repository.get_agent_outputs_by_agent_task_and_agent(
            agent_task_id=agent_task_uuid,
            agent_id=agent_uuid,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return AgentOutputResponse(
            agent_outputs=agent_outputs, total=len(agent_outputs)
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_output_router.get(
    "/agent-outputs/{agent_output_uuid}", response_model=AgentOutputResponse
)
def get_agent_output(
    agent_output_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves agent output information based on agent_output_uuid.
    """
    try:
        agent_output_repository = AgentOutputRepository(db)

        # Check if agent output exists using agent_output_uuid
        existing_agent_output = agent_output_repository.get_agent_output_by_id(
            agent_output_uuid
        )

        if existing_agent_output.get("agent_output"):
            return AgentOutputResponse(
                agent_outputs=[existing_agent_output["agent_output"]],
                total=1,
            )
        else:
            raise HTTPException(
                status_code=404,
                detail="Agent Output not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
