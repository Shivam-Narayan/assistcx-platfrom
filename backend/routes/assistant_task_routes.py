"""
Scheduled Tasks routes.
"""

from agents.assistant_services.task_service import AssistantTaskService
from celery_worker import celery as celery_app
from logger import configure_logging
from schemas.assistant_task_schema import (
    AssistantTaskCreate,
    AssistantTaskDetail,
    AssistantTaskStatusResponse,
    AssistantTaskUpdate,
)
from utils.schema_utils import get_schema_db

from repository.chat_thread_repository import ChatThreadRepository
from sqlalchemy.orm import Session

from typing import List, Optional
from uuid import UUID, uuid4
import json
import os
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
from redbeat import RedBeatSchedulerEntry


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """Extract user_id from JWT token."""
    decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
    return decoded_token["sub"]


# =============================================================================
# SECTION 4: SCHEDULED TASKS  (tag: "Assistant Tasks")
# =============================================================================

assistant_task_router = APIRouter(tags=["Assistant Tasks"])


@assistant_task_router.get("/assistant/tasks", response_model=List[AssistantTaskDetail])
@assistant_task_router.get(
    "/assistant/tasks/search",
    response_model=List[AssistantTaskDetail],
    deprecated=True,
    include_in_schema=False,
)
def get_assistant_tasks(
    keyword: Optional[str] = Query(None, description="Search keyword (optional)"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """List or search assistant tasks for the authenticated user.

    If keyword is provided, searches tasks by keyword. Otherwise lists all tasks.
    """
    try:
        user_uuid = get_current_user_id(token)
        chat_thread_repository = ChatThreadRepository(db)

        try:
            request_filters = json.loads(filters) if filters else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid JSON format in filters"
            )

        request_filters["chat_type"] = "task"

        if keyword:
            chat_threads = chat_thread_repository.search_chat_threads_by_user_id(
                user_id=user_uuid,
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=request_filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return [AssistantTaskDetail.from_chat_thread(thread) for thread in chat_threads]
        else:
            chat_threads = chat_thread_repository.get_chat_threads_by_user_id(
                user_id=user_uuid,
                page=page,
                page_size=page_size,
                filters=request_filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return [AssistantTaskDetail.from_chat_thread(thread) for thread in chat_threads]

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_assistant_tasks: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.get("/assistant/tasks/{chat_thread_id}", response_model=AssistantTaskDetail)
def get_assistant_task(
    chat_thread_id: UUID = Path(..., description="Chat thread ID of the Assistant task"),
    db: Session = Depends(get_schema_db),
):
    """Get a single Assistant task by its ID."""
    try:
        chat_thread_repository = ChatThreadRepository(db)
        chat_thread = chat_thread_repository.get_chat_thread_by_id(chat_thread_id)

        if not chat_thread:
            raise HTTPException(status_code=404, detail="Assistant task not found")
        if not chat_thread.chat_type or chat_thread.chat_type != "task":
            raise HTTPException(status_code=400, detail="Not an Assistant task")

        return AssistantTaskDetail.from_chat_thread(chat_thread)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_assistant_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.get(
    "/assistant/tasks/{thread_uuid}/tasks", response_model=List[AssistantTaskDetail]
)
def get_child_tasks(
    thread_uuid: UUID = Path(
        ..., description="Parent thread UUID to get child tasks for"
    ),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
):
    """Get all child tasks for a parent Assistant task thread."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        try:
            request_filters = json.loads(filters) if filters else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail="Invalid JSON format in filters"
            )

        parent_thread = chat_thread_repository.get_chat_thread_by_id(thread_uuid)
        if not parent_thread:
            raise HTTPException(status_code=404, detail="Parent Assistant task not found")
        if not parent_thread.chat_type or parent_thread.chat_type != "task":
            raise HTTPException(status_code=400, detail="Thread is not an Assistant task")

        child_threads = chat_thread_repository.get_child_threads_by_parent_id(
            parent_id=thread_uuid,
            page=page,
            page_size=page_size,
            filters=request_filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return [AssistantTaskDetail.from_chat_thread(thread) for thread in child_threads]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_child_tasks: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.post("/assistant/tasks", response_model=AssistantTaskDetail)
async def create_assistant_task(
    assistant_task_data: AssistantTaskCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """Creates a new Assistant task with scheduling support."""
    try:
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])

        try:
            assistant_task_service = AssistantTaskService()
            schedule_result = assistant_task_service.parse_schedule(assistant_task_data.schedule)
            schedule_type = assistant_task_service.detect_schedule_type(
                assistant_task_data.schedule
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid schedule format: {e}")

        chat_thread_repository = ChatThreadRepository(db)

        chat_metadata = {
            "schedule": assistant_task_data.schedule,
            "schedule_type": schedule_type,
            "task_prompt": assistant_task_data.task_prompt,
            "collections": assistant_task_data.collections,
            "web_search_enabled": assistant_task_data.web_search_enabled,
            "notification_recipients": assistant_task_data.notification_recipients,
            "status": "active",
        }

        chat_thread_data = {
            "title": assistant_task_data.title,
            "user_id": str(user_uuid),
            "id": uuid4(),
            "chat_metadata": chat_metadata,
            "chat_type": "task",
            "is_archived": False,
        }

        chat_thread_data["external_id"] = (
            f"thread-{chat_thread_data['id']}-{int(time.time() * 1000)}"
        )

        result_chat_thread = chat_thread_repository.create_chat_thread(chat_thread_data)

        if not result_chat_thread:
            raise HTTPException(
                status_code=400, detail="Failed to create chat thread for Assistant task."
            )

        parent_update_result = chat_thread_repository.update_chat_thread(
            {
                "chat_thread_uuid": result_chat_thread.id,
                "parent_id": result_chat_thread.id,
            }
        )

        if not parent_update_result:
            chat_thread_repository.delete_chat_thread(result_chat_thread.id)
            raise HTTPException(
                status_code=400, detail="Failed to create parent thread for Assistant task."
            )

        try:
            task_name = f"assistant_task_{result_chat_thread.id}"
            task_kwargs = {
                "chat_thread_id": str(result_chat_thread.id),
                "task_prompt": assistant_task_data.task_prompt,
                "collections": assistant_task_data.collections,
                "web_search_enabled": assistant_task_data.web_search_enabled,
                "user_id": str(user_uuid),
                "org_schema": getattr(request.state, "org_id", "public"),
                "title": assistant_task_data.title,
                "notification_recipients": assistant_task_data.notification_recipients,
            }

            if schedule_type == "cron":
                entry = RedBeatSchedulerEntry(
                    name=task_name,
                    task="process_assistant_task",
                    schedule=schedule_result,
                    kwargs=task_kwargs,
                    enabled=True,
                    app=celery_app,
                )
                entry.save()
                logger.info(
                    f"Assistant task scheduled with RedBeat: {result_chat_thread.id} with cron: {assistant_task_data.schedule}"
                )
            else:
                celery_app.send_task(
                    "process_assistant_task",
                    kwargs=task_kwargs,
                    eta=schedule_result,
                )
                logger.info(
                    f"Assistant task scheduled with ETA: {result_chat_thread.id} at {schedule_result}"
                )

        except Exception as e:
            logger.error(f"Failed to schedule Assistant task: {e}")
            chat_thread_repository.delete_chat_thread(result_chat_thread.id)
            raise HTTPException(
                status_code=500, detail=f"Failed to schedule Assistant task: {e}"
            )

        return AssistantTaskDetail.from_chat_thread(result_chat_thread)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_assistant_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.patch("/assistant/tasks/{chat_thread_id}", response_model=AssistantTaskDetail)
def update_assistant_task(
    chat_thread_id: UUID = Path(..., description="Chat thread ID of the Assistant task"),
    assistant_task_data: AssistantTaskUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """Update an Assistant task."""
    try:
        chat_thread_repository = ChatThreadRepository(db)
        chat_thread = chat_thread_repository.get_chat_thread_by_id(chat_thread_id)

        if not chat_thread:
            raise HTTPException(status_code=404, detail="Assistant task not found")
        if not chat_thread.chat_type or chat_thread.chat_type != "task":
            raise HTTPException(status_code=400, detail="Not an Assistant task")

        update_data = {"chat_thread_uuid": chat_thread_id}
        updated_metadata = chat_thread.chat_metadata.copy()
        scheduler_needs_update = False
        assistant_task_service = None

        if assistant_task_data.title is not None:
            update_data["title"] = assistant_task_data.title

        if assistant_task_data.task_prompt is not None:
            updated_metadata["task_prompt"] = assistant_task_data.task_prompt
            scheduler_needs_update = True

        updated_fields = assistant_task_data.model_dump(exclude_unset=True)
        if "collections" in updated_fields:
            updated_metadata["collections"] = assistant_task_data.collections
            scheduler_needs_update = True

        if assistant_task_data.notification_recipients is not None:
            updated_metadata["notification_recipients"] = (
                assistant_task_data.notification_recipients
            )
            scheduler_needs_update = True

        if assistant_task_data.web_search_enabled is not None:
            updated_metadata["web_search_enabled"] = assistant_task_data.web_search_enabled
            scheduler_needs_update = True

        if assistant_task_data.schedule is not None:
            try:
                if not assistant_task_service:
                    assistant_task_service = AssistantTaskService()
                new_schedule_result = assistant_task_service.parse_schedule(
                    assistant_task_data.schedule
                )
                new_schedule_type = assistant_task_service.detect_schedule_type(
                    assistant_task_data.schedule
                )
                updated_metadata["schedule"] = assistant_task_data.schedule
                updated_metadata["schedule_type"] = new_schedule_type
                scheduler_needs_update = True
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid schedule format: {e}"
                )

        update_data["chat_metadata"] = updated_metadata
        result = chat_thread_repository.update_chat_thread(update_data)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to update Assistant task")

        if scheduler_needs_update:
            task_name = f"assistant_task_{chat_thread_id}"

            try:
                current_schedule = updated_metadata.get("schedule")
                current_schedule_type = updated_metadata.get("schedule_type")
                old_schedule_type = chat_thread.chat_metadata.get(
                    "schedule_type", "cron"
                )

                if not assistant_task_service:
                    assistant_task_service = AssistantTaskService()
                parsed_schedule = assistant_task_service.parse_schedule(current_schedule)

                task_kwargs = {
                    "chat_thread_id": str(chat_thread_id),
                    "task_prompt": updated_metadata.get("task_prompt", ""),
                    "collections": updated_metadata.get("collections"),
                    "web_search_enabled": updated_metadata.get(
                        "web_search_enabled", True
                    ),
                    "user_id": str(result.user_id),
                    "org_schema": getattr(request.state, "org_id", "public"),
                    "title": result.title or "",
                    "notification_recipients": updated_metadata.get(
                        "notification_recipients", None
                    ),
                }

                if old_schedule_type == "cron":
                    try:
                        redbeat_key = f"redbeat:{task_name}"
                        old_entry = RedBeatSchedulerEntry.from_key(
                            redbeat_key, app=celery_app
                        )
                        old_entry.delete()
                        logger.info(f"Deleted old RedBeat entry for task: {task_name}")
                    except Exception as e:
                        logger.warning(f"Could not delete old RedBeat entry: {e}")

                if current_schedule_type == "cron":
                    new_entry = RedBeatSchedulerEntry(
                        name=task_name,
                        task="process_assistant_task",
                        schedule=parsed_schedule,
                        kwargs=task_kwargs,
                        enabled=updated_metadata.get("status", "active") == "active",
                        app=celery_app,
                    )
                    new_entry.save()
                    logger.info(
                        f"Updated RedBeat scheduler entry for task: {task_name}"
                    )
                else:
                    celery_app.send_task(
                        "process_assistant_task",
                        kwargs=task_kwargs,
                        eta=parsed_schedule,
                    )
                    logger.info(
                        f"Scheduled one-time task with ETA: {task_name} at {parsed_schedule}"
                    )

            except Exception as e:
                logger.error(f"Failed to update scheduler entry: {e}")

        return AssistantTaskDetail.from_chat_thread(result)

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_assistant_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.post(
    "/assistant/tasks/{chat_thread_id}/status", response_model=AssistantTaskStatusResponse
)
@assistant_task_router.post(
    "/assistant/tasks/{chat_thread_id}/pause",
    response_model=AssistantTaskStatusResponse,
    deprecated=True,
    include_in_schema=False,
)
@assistant_task_router.post(
    "/assistant/tasks/{chat_thread_id}/resume",
    response_model=AssistantTaskStatusResponse,
    deprecated=True,
    include_in_schema=False,
)
def toggle_assistant_task_status(
    chat_thread_id: UUID = Path(..., description="Chat thread ID of the Assistant task"),
    action: Optional[str] = Body(None, description="Action: 'pause' or 'resume'", embed=True),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """Pause or resume an Assistant task.

    Uses 'action' from request body for /status endpoint.
    For deprecated /pause and /resume endpoints, action is inferred from the path.
    """
    try:
        decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])

        # Infer action from path for deprecated endpoints
        if action is None:
            path = request.url.path
            if path.endswith("/pause"):
                action = "pause"
            elif path.endswith("/resume"):
                action = "resume"

        if action not in ("pause", "resume"):
            raise HTTPException(
                status_code=400, detail="action must be 'pause' or 'resume'"
            )

        chat_thread_repository = ChatThreadRepository(db)
        chat_thread = chat_thread_repository.get_chat_thread_by_id(chat_thread_id)

        if not chat_thread:
            raise HTTPException(
                status_code=404, detail="Assistant task not found. Please check and retry."
            )
        if not chat_thread.chat_type or chat_thread.chat_type != "task":
            raise HTTPException(
                status_code=404, detail="Assistant task not found. Please check and retry."
            )

        # For pause: check one-time tasks can't be paused
        if action == "pause":
            schedule_type = chat_thread.chat_metadata.get("schedule_type", "cron")
            if schedule_type == "timestamp":
                raise HTTPException(
                    status_code=400,
                    detail="One time tasks can't be paused. Please try deleting it."
                )

        # Check current status
        current_status = chat_thread.chat_metadata.get("status", "active")
        target_status = "paused" if action == "pause" else "active"
        opposite_status = "active" if action == "pause" else "paused"

        if current_status == target_status:
            raise HTTPException(
                status_code=400, detail=f"Assistant task is already {target_status}"
            )

        # Update metadata
        updated_metadata = chat_thread.chat_metadata.copy()
        updated_metadata["status"] = target_status

        update_result = chat_thread_repository.update_chat_thread(
            {"chat_thread_uuid": chat_thread_id, "chat_metadata": updated_metadata}
        )

        if not update_result:
            raise HTTPException(status_code=500, detail="Failed to update task status")

        # Toggle scheduler entry
        task_name = f"assistant_task_{chat_thread_id}"
        assistant_task_service = AssistantTaskService()
        scheduler_success = assistant_task_service.toggle_scheduler_entry(
            task_name, enabled=(action == "resume")
        )

        if not scheduler_success:
            # Rollback
            updated_metadata["status"] = opposite_status
            chat_thread_repository.update_chat_thread(
                {
                    "chat_thread_uuid": chat_thread_id,
                    "chat_metadata": updated_metadata,
                }
            )
            raise HTTPException(
                status_code=400 if action == "pause" else 500,
                detail=f"Failed to {action} scheduler entry. Please check and retry.",
            )

        return AssistantTaskStatusResponse(
            chat_thread_id=chat_thread_id,
            status=target_status,
            message=f"Assistant task {'paused' if action == 'pause' else 'resumed'} successfully",
        )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in toggle_assistant_task_status: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@assistant_task_router.delete("/assistant/tasks/{chat_thread_id}")
def delete_assistant_task(
    chat_thread_id: UUID = Path(..., description="Chat thread ID of the Assistant task"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """Delete an Assistant task and its scheduler entry."""
    try:
        decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])

        chat_thread_repository = ChatThreadRepository(db)
        chat_thread = chat_thread_repository.get_chat_thread_by_id(chat_thread_id)

        if not chat_thread:
            raise HTTPException(status_code=404, detail="Assistant task not found")
        if not chat_thread.chat_type or chat_thread.chat_type != "task":
            raise HTTPException(status_code=400, detail="Not an Assistant task")

        task_name = f"assistant_task_{chat_thread_id}"
        try:
            redbeat_key = f"redbeat:{task_name}"
            entry = RedBeatSchedulerEntry.from_key(redbeat_key, app=celery_app)
            entry.delete()
            logger.info(f"Deleted scheduler entry: {task_name}")
        except Exception as e:
            logger.warning(f"Failed to delete scheduler entry '{task_name}': {e}")

        result = chat_thread_repository.delete_chat_thread(chat_thread_id)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to delete Assistant task")

        return {"message": "Assistant task deleted successfully"}

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_assistant_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
