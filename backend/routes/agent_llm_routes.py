# Custom libraries
from logger import configure_logging
from schemas.agent_llm_schema import (
    AgentLLMCreate,
    AgentLLMDetail,
    AgentLLMUpdate,
    AgentLLMResponse,
)
from schemas.user_schema import Message
from utils.schema_utils import get_schema_db

# Database modules
from repository.agent_llm_repository import AgentLLMRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import List, Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

logger = configure_logging(__name__)

agent_llm_router = APIRouter(tags=["Agent LLMs"])


def _format_response(agent_llm) -> AgentLLMDetail:
    """Format database model to AgentLLMDetail response schema."""
    return AgentLLMDetail(
        id=agent_llm.id,
        llm_key=agent_llm.llm_key,
        name=agent_llm.data.get("name") if agent_llm.data else None,
        description=agent_llm.data.get("description") if agent_llm.data else None,
        integration_key=agent_llm.data.get("integration_key") if agent_llm.data else None,
        model_name=agent_llm.data.get("model_name") if agent_llm.data else None,
        provider=agent_llm.data.get("provider") if agent_llm.data else None,
        llm_config=agent_llm.data.get("llm_config") if agent_llm.data else None,
        metadata=agent_llm.data.get("metadata") if agent_llm.data else None,
        created_at=agent_llm.created_at,
        updated_at=agent_llm.updated_at,
    )


@agent_llm_router.get("/agent-llms", response_model=AgentLLMResponse)
def get_agent_llms(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent LLM information based on specified criteria.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        filters = request.state.filters

        agent_llms = agent_llm_repository.get_all_agent_llms(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return AgentLLMResponse(
            agent_llms=[_format_response(llm) for llm in agent_llms]
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@agent_llm_router.get("/agent-llms/search", response_model=AgentLLMResponse)
def search_agent_llms(
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
    Searches and retrieves agent LLM information based on specified keyword.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        filters = request.state.filters

        if keyword:
            agent_llms = agent_llm_repository.search_agent_llms(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return AgentLLMResponse(
                agent_llms=[_format_response(llm) for llm in agent_llms]
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_llm_router.get("/agent-llms/{agent_llm_uuid}", response_model=AgentLLMDetail)
def get_agent_llm(
    agent_llm_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves a specific agent LLM by its UUID.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        agent_llm = agent_llm_repository.get_agent_llm_by_id(agent_llm_uuid)

        if not agent_llm:
            raise HTTPException(status_code=404, detail="Agent LLM not found.")

        return _format_response(agent_llm)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_llm_router.post("/agent-llms", response_model=AgentLLMDetail)
def create_agent_llm(
    agent_llm_data: AgentLLMCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new agent LLM.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        agent_llm = agent_llm_repository.create_agent_llm(agent_llm_data.model_dump())

        if agent_llm:
            logger.info(f"Agent LLM created successfully: {agent_llm.id}")
            return _format_response(agent_llm)
        else:
            raise HTTPException(status_code=400, detail="Failed to create Agent LLM.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_llm_router.patch("/agent-llms/{agent_llm_uuid}", response_model=AgentLLMDetail)
def update_agent_llm(
    agent_llm_uuid: UUID,
    agent_llm_data: AgentLLMUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing agent LLM by its UUID.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        existing = agent_llm_repository.get_agent_llm_by_id(agent_llm_uuid)
        if not existing:
            raise HTTPException(status_code=404, detail="Agent LLM not found.")

        update_data = {
            k: v for k, v in agent_llm_data.model_dump().items() if v is not None
        }
        update_data["agent_llm_uuid"] = agent_llm_uuid

        updated_agent_llm = agent_llm_repository.update_agent_llm_by_id(update_data)

        if updated_agent_llm:
            logger.info(f"Agent LLM updated successfully: {updated_agent_llm.id}")
            return _format_response(updated_agent_llm)
        else:
            raise HTTPException(status_code=404, detail="Failed to update Agent LLM.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_agent_llm: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_llm_router.delete("/agent-llms/{agent_llm_uuid}", response_model=Message)
def delete_agent_llm(
    agent_llm_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an agent LLM by its UUID.
    """
    try:
        agent_llm_repository = AgentLLMRepository(db)

        deleted = agent_llm_repository.delete_agent_llm(agent_llm_uuid)

        if not deleted:
            raise HTTPException(status_code=404, detail="Agent LLM not found.")

        logger.info(f"Agent LLM deleted successfully: {agent_llm_uuid}")
        return Message(message="Agent LLM deleted successfully.")

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_agent_llm: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


