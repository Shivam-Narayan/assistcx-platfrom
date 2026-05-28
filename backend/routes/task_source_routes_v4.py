# Custom libraries
from logger import configure_logging
from schemas.task_source_schema_v4 import (
    TaskSourceCreate,
    TaskSourceDetail,
    TaskSourceResponse,
    TaskSourceUpdate,
)
from schemas.user_schema import Message
from repository.task_source_repository_v4 import TaskSourceRepository
from repository.connection_repository_v4 import ConnectionRepository
from utils.schema_utils import get_async_schema_db, get_current_schema_async
from utils.crypto_utils import decrypt_connection_credentials
from utils.integration_validator_v4 import IntegrationValidatorV4

# Database modules
from models.agent import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Default libraries
from uuid import UUID
from typing import Optional
from datetime import datetime

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from celery.schedules import schedule as CelerySchedule
from redbeat import RedBeatSchedulerEntry

from celery_worker import celery


logger = configure_logging(__name__)

task_source_router = APIRouter(tags=["Task Sources"])


@task_source_router.get("/task-sources", response_model=TaskSourceResponse)
async def get_task_sources(
    keyword: Optional[str] = Query(
        None, description="Search keyword for name, provider_key, trigger_key"
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
    Retrieves task source information for all task sources based on specified criteria.
    """
    try:
        task_source_repository = TaskSourceRepository(db)

        filters = request.state.filters

        task_sources = await task_source_repository.get_all_task_sources(
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return TaskSourceResponse(task_sources=task_sources)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_task_sources: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.get(
    "/task-sources/{task_source_id}", response_model=TaskSourceDetail
)
async def get_task_source(
    task_source_id: UUID = Path(..., description="Task Source UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Retrieves task source information based on task_source_id.
    """
    try:
        task_source_repository = TaskSourceRepository(db)

        task_source = await task_source_repository.get_task_source_by_id(task_source_id)

        if task_source:
            return TaskSourceDetail.model_validate(task_source)
        else:
            raise HTTPException(
                status_code=404,
                detail="Task Source not found. Please check and retry.",
            )
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in get_task_source: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.post("/task-sources", response_model=TaskSourceDetail)
async def create_task_source(
    task_source_data: TaskSourceCreate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Creates a new task source.
    """
    try:
        # Validate connection_id exists before create
        connection_repository = ConnectionRepository(db)
        connection = await connection_repository.get_connection_by_id(
            task_source_data.connection_id
        )
        if connection is None:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )
        # Validate agent_id exists before create (async query; AgentRepository is sync)
        result = await db.execute(
            select(Agent).where(Agent.id == task_source_data.agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(
                status_code=404,
                detail="Agent not found. Please check and retry.",
            )

        task_source_repository = TaskSourceRepository(db)
        task_source = await task_source_repository.create_task_source(task_source_data)

        if task_source:
            logger.info(f"Task source created successfully: {task_source.id}")
            return TaskSourceDetail.model_validate(task_source)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create task source.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in create_task_source: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.patch(
    "/task-sources/{task_source_id}", response_model=TaskSourceDetail
)
async def update_task_source(
    task_source_id: UUID = Path(..., description="Task Source UUID"),
    task_source_data: TaskSourceUpdate = Body(...),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Updates an existing task source based on its task_source_id.
    """
    try:
        # Validate connection_id if provided
        if task_source_data.connection_id is not None:
            connection_repository = ConnectionRepository(db)
            connection = await connection_repository.get_connection_by_id(
                task_source_data.connection_id
            )
            if connection is None:
                raise HTTPException(
                    status_code=404,
                    detail="Connection not found. Please check and retry.",
                )
        # Validate agent_id if provided
        if task_source_data.agent_id is not None:
            result = await db.execute(
                select(Agent).where(Agent.id == task_source_data.agent_id)
            )
            agent = result.scalar_one_or_none()
            if agent is None:
                raise HTTPException(
                    status_code=404,
                    detail="Agent not found. Please check and retry.",
                )

        task_source_repository = TaskSourceRepository(db)

        # Get existing task source by id before update
        existing_task_source = await task_source_repository.get_task_source_by_id(
            task_source_id
        )
        if not existing_task_source:
            raise HTTPException(
                status_code=404,
                detail="Task Source not found. Please check and retry.",
            )

        update_data = {
            k: v for k, v in task_source_data.model_dump().items() if v is not None
        }
        update_data["task_source_id"] = task_source_id

        task_source = await task_source_repository.update_task_source(update_data)
        if task_source:
            logger.info(f"Task Source updated successfully: {task_source.id}")
            return TaskSourceDetail.model_validate(task_source)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Task Source. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in update_task_source: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.delete("/task-sources/{task_source_id}", response_model=Message)
async def delete_task_source(
    task_source_id: UUID = Path(..., description="Task Source UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Deletes an existing task source based on its task_source_id.
    """
    try:
        task_source_repository = TaskSourceRepository(db)

        deleted = await task_source_repository.delete_task_source(task_source_id)

        if deleted:
            logger.info(f"Task Source deleted successfully: {task_source_id}")
            return Message(message="Task Source deleted successfully.")
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Task Source. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"Error in delete_task_source: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.post(
    "/task-sources/{task_source_id}/polling/start", response_model=TaskSourceDetail
)
async def start_task_source_polling(
    task_source_id: UUID = Path(..., description="Task Source UUID"),
    polling_start_time: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Creates or updates a RedBeat polling schedule for a task source.
    Validates the connection credentials before scheduling.
    """
    try:
        if polling_start_time:
            try:
                datetime.strptime(polling_start_time, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Invalid polling_start_time format. "
                        "Expected: YYYY-MM-DDTHH:MM:SSZ (e.g., '2025-10-08T09:20:00Z')"
                    ),
                )

        task_source_repo = TaskSourceRepository(db)
        connection_repo = ConnectionRepository(db)

        task_source = await task_source_repo.get_task_source_by_id(task_source_id)
        if not task_source:
            raise HTTPException(
                status_code=404,
                detail="Task Source not found. Please check and retry.",
            )

        connection = await connection_repo.get_connection_by_id(task_source.connection_id)
        if not connection:
            raise HTTPException(
                status_code=404,
                detail="Connection not found. Please check and retry.",
            )

        if not connection.encrypted_credentials:
            raise HTTPException(
                status_code=422,
                detail="This connection is missing credentials. Please check and retry.",
            )

        decrypted_creds = decrypt_connection_credentials(connection.encrypted_credentials)

        validator = IntegrationValidatorV4()
        is_valid, error_msg = await validator.validate_credentials(
            provider_key=task_source.provider_key,
            auth_schema_key=connection.auth_schema_key,
            credentials=decrypted_creds,
        )
        if not is_valid:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unable to connect to {task_source.provider_key}: {error_msg}. "
                    "Please verify the connection credentials."
                ),
            )

        organization_schema = await get_current_schema_async(db=db)

        schedule_config = task_source.schedule_config or {}
        poll_schedule = CelerySchedule(run_every=schedule_config.get("interval", 60))
        entry = RedBeatSchedulerEntry(
            name=f"task_source_poll|{task_source_id}",
            task="task_source_worker",
            schedule=poll_schedule,
            args=[
                organization_schema,
                str(task_source_id),
                polling_start_time,
            ],
            app=celery,
        )
        entry.save()

        return TaskSourceDetail.model_validate(task_source)

    except HTTPException as http_error:
        logger.error("HTTPException occurred: %s", http_error.detail)
        raise http_error
    except Exception as e:
        logger.error("Error in start_task_source_polling: %s", e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@task_source_router.post(
    "/task-sources/{task_source_id}/polling/stop", response_model=Message
)
async def stop_task_source_polling(
    task_source_id: UUID = Path(..., description="Task Source UUID"),
    db: AsyncSession = Depends(get_async_schema_db),
):
    """
    Stops and removes the RedBeat polling schedule for a task source.
    """
    try:
        task_source_repo = TaskSourceRepository(db)
        task_source = await task_source_repo.get_task_source_by_id(task_source_id)
        if not task_source:
            raise HTTPException(
                status_code=404,
                detail="Task Source not found. Please check and retry.",
            )

        entry_key = f"redbeat:task_source_poll|{task_source_id}"
        try:
            entry = RedBeatSchedulerEntry.from_key(entry_key, app=celery)
            entry.delete()
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail="No active polling schedule found for this task source.",
            )

        return Message(message="Polling stopped successfully.")

    except HTTPException as http_error:
        logger.error("HTTPException occurred: %s", http_error.detail)
        raise http_error
    except Exception as e:
        logger.error("Error in stop_task_source_polling: %s", e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
