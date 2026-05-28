# Custom libraries
from celery_worker import celery
from agents.task_agent.executor import TaskExecutor
from logger import configure_logging
from schemas.agent_task_schema import (
    AgentTaskContinue,
    AgentTaskDetail,
    AgentTaskExport,
    AgentTaskExportResponse,
    AgentTaskResume,
    AgentTaskRetry,
    AgentTaskStatusUpdate,
    AgentTaskTagsUpdate,
)
from schemas.user_schema import Message
from utils.task_utils import export_agent_tasks_to_excel, finalize_email_status
from utils.schema_utils import get_schema_db, get_current_schema

# Database modules
from repository.activity_log_repository import ActivityLogRepository
from repository.agent_repository import AgentRepository
from repository.agent_task_repository import AgentTaskRepository
from repository.agent_output_repository import AgentOutputRepository
from repository.email_repository import EmailRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime, timezone
from typing import Optional
import asyncio
import json
import os

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
from uuid import UUID


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

agent_task_router = APIRouter(tags=["Agent Tasks"])


@agent_task_router.post("/agent-tasks/export", response_model=AgentTaskExportResponse)
def export_agent_tasks(
    keyword: str = Query(None, description="Search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    from_date: float = Query(None, description="Start date as Unix timestamp"),
    to_date: float = Query(None, description="End date as Unix timestamp"),
    export_data: AgentTaskExport = Body(None),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves and exports agent task information to an Excel file based on specified criteria.
    """
    try:
        email_repository = EmailRepository(db)
        agent_task_repository = AgentTaskRepository(db)
        agent_output_repository = AgentOutputRepository(db)
        filters = request.state.filters

        # Step 1: Fetch emails based on request type (DRY - single path)
        if export_data and export_data.email_ids:
            emails = email_repository.get_emails_by_ids(export_data.email_ids)
        elif keyword:
            emails, _ = email_repository.search_emails(
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                from_date=(datetime.fromtimestamp(from_date) if from_date else None),
                to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            )
        else:
            emails, _ = email_repository.get_all_emails(
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                from_date=(datetime.fromtimestamp(from_date) if from_date else None),
                to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            )

        # Step 2: Validate emails found
        if not emails:
            raise HTTPException(
                status_code=404,
                detail="No Emails found. Please check and retry.",
            )

        # Step 3: Batch fetch all tasks for all emails (DB operation in API layer)
        email_ids = [email.id for email in emails]
        all_tasks_map = agent_task_repository.get_tasks_by_email_ids(email_ids)

        # Step 4: Flatten all tasks from all emails
        agent_tasks = []
        for email_id in email_ids:
            if email_id in all_tasks_map:
                agent_tasks.extend(all_tasks_map[email_id].agent_tasks)

        # Step 5: Fetch all outputs for all tasks (DB operation in API layer)
        task_ids = [task.id for task in agent_tasks]
        outputs_map = agent_output_repository.get_outputs_by_task_ids(task_ids)

        # Step 6: Pure data transformation (no DB operations)
        return export_agent_tasks_to_excel(agent_tasks, emails, outputs_map)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_task_router.get("/agent-tasks/{agent_task_uuid}", response_model=AgentTaskDetail)
def get_agent_task_by_id(
    agent_task_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Fetches the details of a specific agent task by its UUID.
    """
    try:
        agent_task_repository = AgentTaskRepository(db)
        agent_task = agent_task_repository.get_agent_task_details_by_id(agent_task_uuid)

        if not agent_task:
            raise HTTPException(status_code=404, detail="Agent Task not found.")

        # Convert to AgentTaskDetail
        return AgentTaskDetail.model_validate(agent_task)

    except HTTPException as http_error:
        # Catch and re-raise FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in get_agent_task_by_id: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_task_router.get("/agent-tasks/{agent_task_uuid}/stream")
async def stream_agent_task_updates(
    agent_task_uuid: str,
    agent_output_uuid: Optional[str] = Query(None),
    db: Session = Depends(get_schema_db),
) -> StreamingResponse:
    """
    Streams real-time updates for an executing agent task based on the specified agent_task_uuid and agent_output_uuid (optional).
    """
    # Initialize thread_id as None
    thread_id = None

    # Try agent_output first if uuid provided
    if agent_output_uuid:
        agent_output_repository = AgentOutputRepository(db)
        output = agent_output_repository.get_agent_output_by_id(agent_output_uuid)
        if output and output.get("agent_output"):
            thread_id = output["agent_output"].thread_id

    # Fallback to agent_task if thread_id not found
    if not thread_id or len(thread_id) < 5:
        agent_task_repository = AgentTaskRepository(db)
        agent_task = agent_task_repository.get_task_by_id(agent_task_uuid)
        if not agent_task:
            raise HTTPException(status_code=404, detail="Agent task not found.")
        thread_id = getattr(agent_task, "thread_id", None)

    # Validate thread_id
    if not thread_id or len(thread_id) < 5:
        raise HTTPException(status_code=400, detail="Invalid thread_id.")

    organization_schema = get_current_schema(db)

    executor = TaskExecutor(db=db, organization_schema=organization_schema)

    async def event_generator():
        """Generate Server-Sent Events for existing thread."""
        try:
            async for state_update in executor.observe_task_execution(
                task_id=agent_task_uuid,
                thread_id=thread_id,
            ):
                event_data = json.dumps(state_update, default=str)
                yield f"data: {event_data}\n\n"
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(
                f"Client disconnected from agent task stream: {agent_task_uuid}"
            )
            raise
        except Exception as e:
            logger.error(f"Error while streaming agent task {agent_task_uuid}: {e}")
            error_event = {
                "error": str(e),
                "agent_task_uuid": agent_task_uuid,
                "thread_id": thread_id,
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@agent_task_router.post("/agent-tasks/{agent_task_uuid}/continue")
@agent_task_router.post("/task-api/agent-tasks/{agent_task_uuid}/continue")
async def continue_agent_task_updates(
    agent_task_uuid: str,
    continue_task_data: AgentTaskContinue = Body(None),
    db: Session = Depends(get_schema_db),
) -> StreamingResponse:
    """
    Streams real-time updates after taking human input for an executing agent task.

    After streaming completes:
    - Task status is updated (SUCCESSFUL/INCOMPLETE/FAILED)
    - AgentOutput is updated (overwrites output/log, accumulates credits/tokens)
    - Email status is finalized based on all task statuses
    """
    # Get agent_task with email_data_id for finalization
    agent_task_repository = AgentTaskRepository(db)
    agent_task = agent_task_repository.get_task_by_id(agent_task_uuid)
    if not agent_task:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    agent_repository = AgentRepository(db)
    agent = agent_repository.get_agent(agent_task.agent_id)
    if not agent.agent_config or not agent.agent_config.get("allow_task_followup"):
        raise HTTPException(
            status_code=400,
            detail=f"Task followup is disabled for agent '{agent.name}'. Enable 'Allow Task Followup' in Agent Settings → Additional Settings.",
        )

    thread_id = getattr(agent_task, "thread_id", None)
    email_data_id = getattr(agent_task, "email_data_id", None)

    # Validate thread_id
    if not thread_id or len(thread_id) < 5:
        raise HTTPException(status_code=400, detail="Invalid thread_id.")

    organization_schema = get_current_schema(db)

    executor = TaskExecutor(db=db, organization_schema=organization_schema)

    async def event_generator():
        """Generate Server-Sent Events for existing thread."""
        try:
            async for state_update in executor.continue_task_execution(
                task_id=agent_task_uuid,
                thread_id=thread_id,
                message=continue_task_data.message if continue_task_data else "",
            ):
                event_data = json.dumps(state_update, default=str)
                yield f"data: {event_data}\n\n"
                await asyncio.sleep(0.001)

            # ─── FINALIZE EMAIL STATUS ───
            # After streaming completes, finalize email status based on all task statuses
            if email_data_id:
                finalize_result = finalize_email_status(db, email_data_id)
                if finalize_result:
                    logger.info(
                        f"Email status finalized for agent_task={agent_task_uuid}: "
                        f"email_uuid={email_data_id}, status={finalize_result.get('final_status')}"
                    )

        except asyncio.CancelledError:
            logger.info(
                f"Client disconnected from agent task stream: {agent_task_uuid}"
            )
            raise
        except Exception as e:
            logger.error(f"Error while streaming agent task {agent_task_uuid}: {e}")
            error_event = {
                "error": str(e),
                "agent_task_uuid": agent_task_uuid,
                "thread_id": thread_id,
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@agent_task_router.post("/agent-tasks/{agent_task_uuid}/resume")
async def resume_agent_task(
    agent_task_uuid: str,
    resume_data: AgentTaskResume = Body(...),
    db: Session = Depends(get_schema_db),
) -> StreamingResponse:
    """
    Resumes a paused agent task with human review input (approve/reject/edit/respond).
    Streams real-time execution updates via Server-Sent Events.
    """
    agent_task_repository = AgentTaskRepository(db)
    agent_task = agent_task_repository.get_task_by_id(agent_task_uuid)
    if not agent_task:
        raise HTTPException(status_code=404, detail="Agent task not found.")

    # Validate task is paused
    progress_list = agent_task.progress
    current_status = progress_list[-1].get("status") if progress_list else None
    if current_status != "PAUSED":
        raise HTTPException(
            status_code=400,
            detail=f"Task is not paused (current status: {current_status}). "
            "Only paused tasks can be resumed with human review input.",
        )

    thread_id = getattr(agent_task, "thread_id", None)
    email_data_id = getattr(agent_task, "email_data_id", None)

    if not thread_id or len(thread_id) < 5:
        raise HTTPException(status_code=400, detail="Invalid thread_id.")

    organization_schema = get_current_schema(db)
    executor = TaskExecutor(db=db, organization_schema=organization_schema)

    # Build human input dict from resume data
    human_input = resume_data.model_dump(exclude_none=True)

    async def event_generator():
        """Generate Server-Sent Events for resumed execution."""
        try:
            async for state_update in executor.resume_task_execution(
                task_id=agent_task_uuid,
                thread_id=thread_id,
                human_input=human_input,
            ):
                event_data = json.dumps(state_update, default=str)
                yield f"data: {event_data}\n\n"
                await asyncio.sleep(0.001)

            # Finalize email status after completion
            if email_data_id:
                finalize_result = finalize_email_status(db, email_data_id)
                if finalize_result:
                    logger.info(
                        f"Email status finalized for agent_task={agent_task_uuid}: "
                        f"email_uuid={email_data_id}, status={finalize_result.get('final_status')}"
                    )

        except asyncio.CancelledError:
            logger.info(
                f"Client disconnected from agent task resume stream: {agent_task_uuid}"
            )
            raise
        except Exception as e:
            logger.error(f"Error while resuming agent task {agent_task_uuid}: {e}")
            error_event = {
                "error": str(e),
                "agent_task_uuid": agent_task_uuid,
                "thread_id": thread_id,
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@agent_task_router.post("/agent-tasks/{agent_task_uuid}/retry")
@agent_task_router.post("/task-api/agent-tasks/{agent_task_uuid}/retry")
def retry_agent_task(
    agent_task_uuid: UUID,
    retry_agent_task_data: Optional[AgentTaskRetry] = Body(None),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retries an agent task based on the specified agent_task_uuid.
    """
    try:
        is_task_api = "/task-api" in (request.url.path if request else "")

        # If not task-api, check if instructions and agent_uuid are provided
        if not is_task_api:
            if (
                not retry_agent_task_data
                or retry_agent_task_data.agent_uuid is None
                or retry_agent_task_data.instructions is None
            ):
                raise HTTPException(
                    422, "Instructions and Agent UUID are required for retrying an agent task."
                )

        # Get user_id from request.state if not API key auth
        user_id = None
        user = getattr(request.state, "user_id", None)
        if user and getattr(request.state, "auth_type", None) != "api_key":
            user_id = (
                UUID(user)
                if isinstance(user, str)
                else user if isinstance(user, UUID) else None
            )

        # Query agent task data
        agent_task_repository = AgentTaskRepository(db)
        existing_task = agent_task_repository.get_task_by_id(agent_task_uuid)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Agent task not found.")

        # Resolve agent from task if task-api, else from request
        if is_task_api:
            if not existing_task.agent_id:
                raise HTTPException(
                    status_code=400,
                    detail="Agent task has no associated agent, hence cannot be retried.",
                )
            agent_uuid = existing_task.agent_id
        else:
            agent_uuid = retry_agent_task_data.agent_uuid

        # Query agent data
        agent_repository = AgentRepository(db)
        agent_data = agent_repository.get_agent(agent_uuid)
        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found.")

        # Get the existing task status
        progress_list = existing_task.progress
        existing_task_status = (
            progress_list[-1].get("status") if progress_list else None
        )

        # Update progress and agent
        progress = [{"status": "QUEUED", "timestamp": str(datetime.now())}]
        agent_task_data = {
            "agent_id": agent_uuid,
            "progress": progress,
        }
        existing_task = agent_task_repository.update_task(
            agent_task_uuid, agent_task_data
        )

        # Synthesize data required for agent execution
        organization_schema = get_current_schema(db=db)
        task_data = {
            "task_id": existing_task.id,
            "email_uuid": existing_task.email_data_id,
            "agent_id": str(agent_uuid),
            "additional_data": {
                "instructions": (
                    retry_agent_task_data.instructions
                    if retry_agent_task_data and retry_agent_task_data.instructions
                    else ""
                )
            },
            "finalize_email": True,
            "disable_auto_retry": True,  # Manual retry - don't auto-retry on failure
        }

        # Add the new task_id to the Celery queue agent_worker
        celery.send_task(
            "execute_task",
            args=[organization_schema, task_data],
            queue="agent_queue",
        )

        # Log the retry action
        activity_log_data = {
            "user_id": user_id,
            "entity_type": "agent_task",
            "entity_id": agent_task_uuid,
            "activity_type": "task_retry",
            "previous_state": {
                "status": existing_task_status,
            },
            "new_state": {
                "status": "QUEUED",
            },
            "note": (
                retry_agent_task_data.instructions
                if retry_agent_task_data and retry_agent_task_data.instructions
                else None
            ),
        }
        activity_log_repository = ActivityLogRepository(db)
        activity_log_repository.create_activity_log(activity_log_data)
        logger.info(
            f"Agent Task {agent_task_uuid} retried and queued with status QUEUED."
        )

        return {
            "message": "Agent Task successfully queued for execution",
            "agent_task_uuid": str(existing_task.id),
        }

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in retry_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_task_router.post("/agent-tasks/{agent_task_uuid}/tags", response_model=Message)
def update_agent_task_tags(
    agent_task_uuid: UUID,
    agent_task_tags_data: AgentTaskTagsUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates multiple tags for an agent task based on their tag_ids.
    """
    try:
        agent_task_repository = AgentTaskRepository(db)
        updated_agent_task_tags = agent_task_repository.update_agent_task_tags(
            agent_task_id=agent_task_uuid, tag_ids=agent_task_tags_data.tag_ids
        )

        if not updated_agent_task_tags:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Agent Task Tags. Please check and retry.",
            )

        return {"message": "Agent Task Tags updated successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@agent_task_router.post("/agent-tasks/status", response_model=Message)
def update_agent_task_status(
    task_status_update_data: AgentTaskStatusUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Updates the status of multiple agent tasks based on their agent_task_ids.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_id = UUID(decoded_token["sub"])

        if not task_status_update_data.agent_task_ids:
            raise HTTPException(status_code=400, detail="No Agent Tasks provided.")

        # Check if the note is provided for SUCCESSFUL, INCOMPLETE or RESOLVED status
        if task_status_update_data.status in [
            "SUCCESSFUL",
            "INCOMPLETE",
            "RESOLVED",
        ] and (
            task_status_update_data.note is None
            or task_status_update_data.note.strip() == ""
        ):
            raise HTTPException(
                status_code=400,
                detail="Note is required for SUCCESSFUL, INCOMPLETE and RESOLVED Agent Task Status.",
            )

        agent_task_repository = AgentTaskRepository(db)
        activity_log_repository = ActivityLogRepository(db)

        # OPTIMIZATION 1: Batch fetch all tasks at once instead of N+1 queries
        tasks_map = agent_task_repository.get_tasks_by_ids(
            task_status_update_data.agent_task_ids
        )

        if not tasks_map:
            raise HTTPException(
                status_code=404,
                detail="None of the provided Agent Tasks were found.",
            )

        # Track results
        successful_updates = []
        failed_updates = []
        affected_email_ids = set()  # Track unique emails to update only once
        activity_logs_batch = []

        # Process each task
        for task_id in task_status_update_data.agent_task_ids:
            existing_task = tasks_map.get(task_id)

            if not existing_task:
                failed_updates.append({"task_id": str(task_id), "reason": "Not found"})
                logger.warning(f"Agent Task not found: {task_id}")
                continue

            # Get the existing task status
            progress_list = existing_task.progress
            existing_task_status = (
                progress_list[-1].get("status") if progress_list else None
            )

            # Prepare description with note
            task_description = existing_task.description
            if task_status_update_data.note:
                note_prefix = f"Status Update Note: {task_status_update_data.note}\n\n"
                task_description = (
                    f"{note_prefix}{existing_task.description}"
                    if existing_task.description
                    else note_prefix
                )

            # Prepare progress entry
            progress = {
                "status": task_status_update_data.status,
                "timestamp": str(datetime.now()),
            }

            # Update task progress and description (each repo method commits)
            agent_task_repository.append_task_progress(task_id, progress)
            update_data = {"description": task_description}
            updated_task = agent_task_repository.update_task(task_id, update_data)

            if updated_task:
                successful_updates.append(str(task_id))
                affected_email_ids.add(existing_task.email_data_id)

                # Prepare activity log for batch creation
                activity_logs_batch.append(
                    {
                        "user_id": user_id,
                        "entity_type": "agent_task",
                        "entity_id": task_id,
                        "activity_type": "task_status_change",
                        "previous_state": {"status": existing_task_status},
                        "new_state": {"status": task_status_update_data.status},
                        "note": task_status_update_data.note,
                    }
                )

                logger.info(
                    f"Agent Task {task_id} updated to {task_status_update_data.status} status."
                )
            else:
                failed_updates.append(
                    {"task_id": str(task_id), "reason": "Update failed"}
                )

        # OPTIMIZATION 2: Batch create all activity logs at once (repo handles commit)
        if activity_logs_batch:
            activity_log_repository.bulk_create_activity_logs(activity_logs_batch)

        # OPTIMIZATION 3: Update each unique email status only once
        for email_id in affected_email_ids:
            email_status_result = finalize_email_status(db, email_id)
            if email_status_result:
                email_status = email_status_result["final_status"]
                logger.info(
                    f"Email status updated to '{email_status}' for email: {email_id}"
                )

        # Prepare response
        success_count = len(successful_updates)
        total_count = len(task_status_update_data.agent_task_ids)

        if success_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Failed to update any Agent Tasks. Please check and retry.",
            )

        # Log detailed results
        logger.info(
            f"{success_count} of {total_count} Agent Tasks updated to {task_status_update_data.status} status."
        )
        if failed_updates:
            logger.warning(f"Failed updates: {failed_updates}")

        return {
            "message": f"{success_count} of {total_count} Agent Tasks updated successfully.",
        }

    except HTTPException as http_error:
        # Catch and re-raise FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in update_agent_task_status: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
