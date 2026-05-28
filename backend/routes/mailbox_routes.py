# Custom libraries
from celery_worker import celery
from integrations.office_365.attachment import Attachment
from logger import configure_logging
from schemas.agent_task_schema import AgentTaskResponse
from schemas.email_schema import (
    EmailArchive,
    EmailDelete,
    EmailExport,
    EmailExportResponse,
    EmailMailboxFilters,
    EmailResponse,
    EmailRetryTask,
    EmailTagsUpdate,
)
from schemas.task_event_schema import TaskEventDetail
from schemas.user_schema import Message
from utils.task_utils import (
    export_emails_to_excel,
    update_email_status,
    update_email_execution_time,
)
from utils.schema_utils import get_current_schema, get_schema_db
from utils.email_events import create_email_event, EmailEventType

# Database modules
from repository.activity_log_repository import ActivityLogRepository
from repository.agent_repository import AgentRepository
from repository.agent_task_repository import AgentTaskRepository
from repository.email_repository import EmailRepository
from repository.mailbox_polling_repository import MailboxPollingRepository
from repository.task_event_repository import TaskEventRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime
import os
from typing import List, Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")

mailbox_router = APIRouter(tags=["Mailbox and Tasks"])


@mailbox_router.get("/emails", response_model=EmailResponse)
def get_emails(
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    from_date: float = Query(None, description="Start date as Unix timestamp"),
    to_date: float = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves email information based on specified criteria.
    """
    try:
        email_repository = EmailRepository(db)

        filters = request.state.filters

        if keyword:
            # Search emails
            emails, total = email_repository.search_emails(
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                from_date=(datetime.fromtimestamp(from_date) if from_date else None),
                to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            )

            if emails:
                return EmailResponse(emails=emails, total=total)
            else:
                return EmailResponse(emails=[], total=0)
        else:
            # Fetch all emails
            emails, total = email_repository.get_all_emails(
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                from_date=(datetime.fromtimestamp(from_date) if from_date else None),
                to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            )

            return EmailResponse(emails=emails, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.get("/emails/search", response_model=EmailResponse)
def search_emails(
    keyword: str = Query(None, description="Search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves email information based on specified keyword.
    """
    try:
        email_repository = EmailRepository(db)

        filters = request.state.filters

        # Search emails
        if keyword:
            emails, total = email_repository.search_emails(
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if emails:
                return EmailResponse(emails=emails, total=total)
            else:
                return EmailResponse(emails=[], total=0)
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


@mailbox_router.post("/emails/export", response_model=EmailExportResponse)
def export_emails(
    keyword: str = Query(None, description="Search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    from_date: float = Query(None, description="Start date as Unix timestamp"),
    to_date: float = Query(None, description="End date as Unix timestamp"),
    export_data: EmailExport = Body(None),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves and exports email information to an Excel file based on specified criteria.
    """
    try:
        email_repository = EmailRepository(db)
        agent_task_repository = AgentTaskRepository(db)
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

        # Step 3: Fetch all tasks for all emails (DB operation in API layer)
        email_ids = [email.id for email in emails]
        tasks_map = agent_task_repository.get_tasks_by_email_ids(email_ids)

        # Step 4: Pure data transformation (no DB operations)
        return export_emails_to_excel(emails, tasks_map)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.get("/emails/{email_uuid}", response_model=EmailResponse)
def get_email(
    email_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves email information based on email_uuid.
    """
    try:
        email_repository = EmailRepository(db)

        # Check if email exists using email_uuid
        existing_email = email_repository.get_email_by_id(email_uuid)

        if existing_email:
            return EmailResponse(emails=[existing_email], total=1)
        else:
            raise HTTPException(
                status_code=404,
                detail="Email not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_email: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.get("/emails/filters", response_model=EmailMailboxFilters)
def get_mailbox_filters(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves unique mailbox_emails and agents in separate lists.
    """
    try:
        email_repository = EmailRepository(db)

        filters = request.state.filters

        return email_repository.get_mailbox_filters(filters=filters)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.post("/emails/archive", response_model=Message)
def archive_emails(
    archive_data: EmailArchive = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """
    Archives multiple existing emails based on their email_ids and logs the activity.
    """
    try:
        # Extract user_id from the token
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_id = UUID(decoded_token["sub"])

        if not archive_data.email_ids:
            raise HTTPException(status_code=400, detail="No emails provided.")

        email_repository = EmailRepository(db)
        activity_log_repository = ActivityLogRepository(db)

        archived_count = 0
        for email_id in archive_data.email_ids:
            archived_email = email_repository.archive_email_by_id(email_id)
            if archived_email:
                archived_count += 1
                # Log the archive action
                activity_log_data = {
                    "user_id": user_id,
                    "entity_type": "email",
                    "entity_id": email_id,
                    "activity_type": "email_archive",
                    "previous_state": {
                        "status": "",
                    },
                    "new_state": {
                        "status": "ARCHIVED",
                    },
                    "note": (
                        archive_data.note if hasattr(archive_data, "note") else None
                    ),
                }
                activity_log_repository.create_activity_log(activity_log_data)
                logger.info(f"Email {email_id} archived by user {user_id}.")

        if archived_count > 0:
            logger.info(
                f"{archived_count} of {len(archive_data.email_ids)} Emails archived successfully."
            )
            return {
                "message": f"{archived_count} of {len(archive_data.email_ids)} Emails archived successfully."
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to archive Emails. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in archive_emails: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.post("/emails/{agent_task_uuid}/retry/{agent_uuid}")
def retry_task(
    agent_task_uuid: UUID,
    agent_uuid: UUID,
    retry_task_data: EmailRetryTask = Body(None),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retries an agent task by creating a new task based on the existing one and logs the activity.
    """
    try:
        # Get user_id from request.state if not API key auth
        user_id = None
        user = getattr(request.state, "user_id", None)
        if user and getattr(request.state, "auth_type", None) != "api_key":
            user_id = UUID(user) if isinstance(user, str) else user if isinstance(user, UUID) else None

        # Query agent task data
        agent_task_repository = AgentTaskRepository(db)
        existing_task = agent_task_repository.get_task_by_id(agent_task_uuid)
        if not existing_task:
            raise HTTPException(status_code=404, detail="Agent task not found.")

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
        agent_uuid = agent_data.id if agent_data else None
        
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
                    retry_task_data.note
                    if retry_task_data and retry_task_data.note
                    else ""
                )
            },
            "finalize_email": True,
            "disable_auto_retry": True,  # Manual retry - don't auto-retry on failure
            # "update_exec_time": False,  # Don't update execution time for retries
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
                retry_task_data.note
                if retry_task_data and retry_task_data.note
                else None
            ),
        }
        activity_log_repository = ActivityLogRepository(db)
        activity_log_repository.create_activity_log(activity_log_data)
        logger.info(
            f"Agent Task {agent_task_uuid} retried and queued with status QUEUED."
        )

        return {
            "message": "Task successfully queued for execution",
            "agent_task_uuid": str(existing_task.id),
        }

    except HTTPException as http_error:
        # Catch and re-raise FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise
    except Exception as e:
        logger.error(f"Error in retry_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.delete("/emails/bulk", response_model=Message)
def delete_emails(
    delete_data: EmailDelete = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Deletes multiple existing emails and all its agent outputs, task events, agent tasks, attachments and task progress based on their email_ids.
    """
    try:
        if not delete_data.email_ids:
            raise HTTPException(status_code=400, detail="No emails provided.")

        email_repository = EmailRepository(db)

        deleted_count = 0
        for email_id in delete_data.email_ids:
            deleted_email = email_repository.delete_email_by_id(email_id)
            if deleted_email:
                deleted_count += 1

        if deleted_count > 0:
            logger.info(
                f"{deleted_count} of {len(delete_data.email_ids)} Emails deleted successfully"
            )
            return {
                "message": f"{deleted_count} of {len(delete_data.email_ids)} Emails deleted successfully."
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Emails. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_emails: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.delete("/emails", response_model=Message)
def delete_all_emails(
    db: Session = Depends(get_schema_db),
):
    """
    Deletes all email related data. Only allowed for ROOT user.
    """
    try:
        email_repository = EmailRepository(db)

        deleted_emails = email_repository.delete_all_emails()

        if deleted_emails:
            logger.info(f"All emails have been permanently deleted")
            return {"message": "All emails have been permanently deleted."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete emails. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_emails: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.get(
    "/emails/{email_uuid}/agent-tasks", response_model=AgentTaskResponse
)
def get_agent_tasks_by_email(
    email_uuid: UUID,
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("asc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent task information for a specific email based on specified criteria.
    """
    try:
        agent_task_repository = AgentTaskRepository(db)

        filters = request.state.filters

        # Fetch all agent task for an email
        return agent_task_repository.get_agent_task_details_by_email(
            email_uuid=email_uuid,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.get(
    "/emails/{email_uuid}/task-events", response_model=List[TaskEventDetail]
)
def get_task_events_by_email(
    email_uuid: UUID,
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("asc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves task event information for a specific email based on specified criteria.
    """
    try:
        task_event_repository = TaskEventRepository(db)

        filters = request.state.filters

        # Fetch all task events for an email
        return task_event_repository.get_task_events_by_email(
            email_uuid=email_uuid,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.patch("/emails/{email_uuid}/tags", response_model=Message)
def update_email_tags(
    email_uuid: UUID,
    email_tags_data: EmailTagsUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates multiple tags for an email based on their tag_ids.
    """
    try:
        email_repository = EmailRepository(db)
        updated_email_tags = email_repository.update_email_tags(
            email_id=email_uuid, tag_ids=email_tags_data.tag_ids
        )

        if not updated_email_tags:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Email Tags. Please check and retry.",
            )

        return {"message": "Email Tags updated successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_router.post("/emails/{email_uuid}/reprocess", response_model=Message)
def reprocess_email(
    email_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Reprocess an email by sending it to the appropriate worker queue.
    - Checks if email has agent tasks (if yes, throws error)
    - If no agent tasks, checks for attachments
    - Routes to process_attachments if has attachments, else to dispatch_task
    """
    try:
        email_repository = EmailRepository(db)
        email = email_repository.get_email_by_id(email_uuid)
        if not email:
            raise HTTPException(
                status_code=404,
                detail="Email not found. Please check and retry.",
            )

        agent_task_repository = AgentTaskRepository(db)
        email_agent_tasks = agent_task_repository.get_agent_tasks_by_email(email_uuid)
        if email_agent_tasks and email_agent_tasks.agent_tasks:
            raise HTTPException(
                status_code=400,
                detail="Email has tasks. Please try retrying the tasks.",
            )

        # Get organization schema
        organization_schema = get_current_schema(db=db)

        # Get polling config and data store
        mailbox_polling_repository = MailboxPollingRepository(db)
        mailbox_polling = None
        if email.mailbox_email and email.mailbox_folder:
            mailbox_polling = mailbox_polling_repository.get_mailbox_polling(
                f"{email.mailbox_email}|{email.mailbox_folder}"
            )

        # Prepare message data
        message_data = {
            "email_uuid": email.id,
            "mailbox_email": email.mailbox_email,
            "mailbox_folder": email.mailbox_folder,
            "message_id": email.message_id,
            "conversation_id": email.conversation_id,
            "timestamp": email.created_at,
            "polling_config": (
                mailbox_polling.polling_config if mailbox_polling else None
            ),
            "data_store": mailbox_polling.data_store if mailbox_polling else None,
        }

        attachment_instance = Attachment(db)
        attachment_output = attachment_instance.has_attachments(message_data)

        # Send to attachment queue if email has attachments
        # NOTE: Currently updating attachment data, future approach may delete existing ones and reprocess
        if attachment_output.get("has_attachments"):
            update_email_execution_time(db, email_uuid)
            update_email_status(db, email_uuid, "EXECUTING")
            create_email_event(db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_QUEUED)
            celery.send_task(
                "process_attachment",
                args=[organization_schema, message_data],
                queue="attachment_queue",
            )
            logger.info(
                f"Email sent to attachment queue for processing attachments: {email_uuid}"
            )
            return {"message": "Email queued for reprocessing successfully."}

        # No attachments to process, send to agent queue for dispatch
        update_email_status(db, email_uuid, "EXECUTING")
        create_email_event(db, email_uuid, EmailEventType.AGENT_WORKER_QUEUED)
        celery.send_task(
            "dispatch_task",
            args=[organization_schema, email_uuid],
            queue="agent_queue",
        )
        logger.info(
            f"Email has no attachments, sent to agent queue for dispatching tasks: {email_uuid}"
        )
        return {"message": "Email queued for reprocessing successfully."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred in reprocess_email: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in reprocess_email: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @mailbox_router.get("/poll_mailbox")
# def poll_mailbox(
#     email_id: str = Query(...),
#     folder: str = Query(...),
# ):
#     """
#     ###Mostly stale route###
#     Endpoint to initiate mailbox polling for new emails in a specific folder.
#     """
#     try:
#         # Call the poll_mailbox method from MSGraphAPI class
#         outlook = Outlook()
#         response = outlook.poll_mailbox(
#             email_id, folder, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
#         )

#         if response:
#             return response
#         else:
#             raise HTTPException(
#                 status_code=422,
#                 detail="Failed poll mailbox.",
#             )
#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @mailbox_router.get("/emails/search", response_model=EmailResponse)
# def search_emails(
#     keyword: str = Query(None, description="Search keyword"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves email information based on specified keyword.
#     """
#     try:
#         email_repository = EmailRepository(db)

#         filters = request.state.filters

#         # Search emails
#         if keyword:
#             emails, total = email_repository.search_email(
#                 keyword=keyword,
#                 page=page,
#                 page_size=page_size,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if emails:
#                 return EmailResponse(emails=emails, total=total)
#             else:
#                 return EmailResponse(emails=[], total=0)
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
