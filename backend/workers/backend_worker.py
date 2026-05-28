# Custom libraries
from integrations.office_365.outlook import Outlook
from integrations.office_365.attachment import Attachment
from utils.notification import Notification
from configs.notification_config import NotificationConfig
from utils.task_utils import update_email_status
from utils.email_events import create_email_event, EmailEventType
from utils.thread_utils import create_child_thread_for_execution
from workers.attachment_worker import process_attachment
from workers.agent_worker import dispatch_task
from agents.assistant_services.query_service import AssistantQueryService

# Default libraries
from datetime import datetime
from datetime import timezone
from celery import shared_task
import asyncio
from typing import List, Dict, Any, Optional
import time

# Database modules
from db_pool import DatabasePoolManager
from logger import configure_logging


# Initialize the DatabasePoolManager
db_pool = DatabasePoolManager()
logger = configure_logging(__name__)


# Define tasks for polling mailbox and fetching data
@shared_task(name="process_mailbox")
def process_mailbox(
    organization_schema: str, email_id: str, folder: str, polling_start_time: str = None
):
    """
    Process mailbox and get new emails
    """
    start_time = time.time()

    logger.info(
        f"Received new worker task: backend-worker-process-mailbox, mailbox={email_id}|{folder}"
    )
    try:
        with db_pool.get_session(organization_schema) as db:
            # Use polling_start_time if provided, else generate fresh timestamp
            timestamp = (
                polling_start_time
                if polling_start_time
                else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            )

            outlook = Outlook(db)
            mailbox_data, polling_config, data_store = outlook.poll_mailbox(
                email_id, folder, timestamp
            )
            message_list = []
            if mailbox_data:
                for message in mailbox_data:
                    saved_message = outlook.parse_and_save_email(
                        mailbox_email=email_id,
                        email_data=message,
                        polled_folder=folder,
                        polling_config=polling_config,
                        data_store=data_store,
                    )

                    if saved_message is None:
                        logger.info(
                            f"Email could not be processed, skipping message_id {message.get('id')}."
                        )
                        continue

                    create_email_event(
                        db, saved_message.id, EmailEventType.EMAIL_FETCH_SUCCESSFUL
                    )

                    # Log used for counting: new email saved
                    logger.info(
                        f"Saved new email data into database: email_uuid={str(saved_message.id)}"
                    )
                    message_list.append(str(saved_message.id))

                    # Prepare saved message details for attachment processing
                    message_data = {
                        "email_uuid": saved_message.id,
                        "mailbox_email": saved_message.mailbox_email,
                        "mailbox_folder": saved_message.mailbox_folder,
                        "message_id": saved_message.message_id,
                        "conversation_id": saved_message.conversation_id,
                        "timestamp": saved_message.created_at,
                        "polling_config": polling_config,
                        "data_store": data_store,
                    }

                    # Extract priority from polling_config (0=highest/default, 9=lowest)
                    priority = (
                        polling_config.get("mailbox_priority", 0)
                        if polling_config
                        else 0
                    )

                    attachment_instance = Attachment(db)
                    attachment_output = attachment_instance.has_attachments(
                        message_data
                    )
                    logger.info(
                        f"Attachment info for email_uuid {message_data['email_uuid']}: {attachment_output}"
                    )
                    if attachment_output.get("has_attachments", False):
                        # Add attachment count to message data for timeout calculation
                        attachment_count = attachment_output.get("count", 0)
                        message_data["attachment_count"] = attachment_count

                        # Create email event
                        create_email_event(
                            db,
                            saved_message.id,
                            EmailEventType.ATTACHMENT_PROCESS_QUEUED,
                        )

                        logger.info(
                            f"Attachment processing task queued for email_uuid: {saved_message.id} with priority: {priority}"
                        )

                        # Queue task for attachment processing with priority
                        process_attachment.apply_async(
                            args=(organization_schema, message_data),
                            priority=priority,
                        )
                    else:
                        # Create email event
                        create_email_event(
                            db,
                            saved_message.id,
                            EmailEventType.AGENT_WORKER_QUEUED,
                        )

                        logger.info(
                            f"Skipping attachment processing for email_uuid: {message_data['email_uuid']}, dispatching with priority: {priority}"
                        )
                        dispatch_task.apply_async(
                            args=(organization_schema, message_data["email_uuid"]),
                            priority=priority,
                        )

                    # Update task progress status
                    # update_task_progress(
                    #     db, saved_message.id, "email_fetched", "SUCCESSFUL", started_at
                    # )

                    # Update email task status
                    update_email_status(db, saved_message.id, "EXECUTING")

                if len(message_list) > 0:
                    logger.info(
                        f"Processed and saved new email batch. Total emails: {len(message_list)}, Email UUIDs: {message_list}"
                    )

            elapsed_time = time.time() - start_time

            logger.info(
                f"Mailbox processing successful, mailbox={email_id}|{folder}, emails_fetched={len(message_list)}, total_time={elapsed_time:.2f}s"
            )

            return {
                "status": "SUCCESS",
                "summary": f"{len(message_list)} emails fetched from {email_id}|{folder}",
                "data": {
                    "email_id": email_id,
                    "folder": folder,
                    "count": len(message_list),
                    "email_uuids": message_list,
                },
            }

    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Mailbox processing failed, mailbox={email_id}|{folder}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        return {
            "status": "FAILED",
            "summary": f"Failed: {email_id}|{folder}",
            "data": {"email_id": email_id, "folder": folder},
            "error": str(e),
        }


@shared_task(
    name="process_assistant_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def process_assistant_task(
    self,
    chat_thread_id: str,
    task_prompt: str,
    collections: Optional[List[Dict[str, Any]]],
    web_search_enabled: bool,
    user_id: str,
    org_schema: str,
    title: str,
    notification_recipients: Optional[List[str]] = None,
):
    """
    Process Assistant task - Create child thread and execute Assistant query.
    Retry config: max_retries=1 (2 total attempts), default_retry_delay=30s.
    """
    start_time = time.time()

    logger.info(
        f"Received new worker task: backend-worker-process-assistant-task, title={title}, parent_thread_id={chat_thread_id}, user_id={user_id}"
    )

    async def execute_assistant_task():
        # Get database session from pool
        with db_pool.get_session(org_schema) as db:
            # Create child thread for this execution
            child_thread_id = create_child_thread_for_execution(
                parent_thread_id=chat_thread_id, user_id=user_id, title=title, db=db
            )

            logger.info(f"Created child thread {child_thread_id} for execution")

            # Initialize Assistant service
            assistant_service = AssistantQueryService(
                db=db, org_schema=org_schema, user_id=user_id
            )

            logger.info(
                f"Executing Assistant query: prompt={task_prompt[:100]}..., web_search={web_search_enabled}, collections={collections}"
            )

            # Execute Assistant query using child thread
            response = await assistant_service.execute_query_direct(
                query=task_prompt,
                user_id=user_id,
                chat_id=child_thread_id,  # Use child thread instead of parent
                collections=collections,
                user_context={"org_schema": org_schema, "task_type": "scheduled"},
                web_search_enabled=web_search_enabled,
                timeout=120,
            )
            logger.info(
                f"Assistant query completed: answer_preview={response.get('answer', 'No answer')[:100]}..."
            )

            # Send email notification with task results
            # Note: Wrapped in try/except to prevent notification failures from triggering
            # a retry of the entire task (which would duplicate the query execution)
            if response.get("answer") and notification_recipients:
                try:
                    notification = Notification(db=db)

                    # Process Assistant response into email data
                    task_details = notification.prepare_task_notification_data(
                        answer=response.get("answer"),
                        title=title,
                        task_prompt=task_prompt,
                    )

                    # Add continue chat URL if available
                    chat_id = response.get("chat_id")
                    if chat_id:
                        task_details["continue_chat_url"] = (
                            NotificationConfig.get_chat_url(chat_id)
                        )

                    # Send the email
                    notification.send_task_notification(
                        notification_recipients=notification_recipients,
                        task_details=task_details,
                    )
                except Exception as notif_err:
                    # Log but don't fail the task - query succeeded, only notification failed
                    logger.error(
                        f"Failed to send notification for task '{title}': {notif_err}",
                        exc_info=True,
                    )

            return child_thread_id, response

    try:
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            child_thread_id, response = loop.run_until_complete(
                execute_assistant_task()
            )
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

        elapsed_time = time.time() - start_time

        logger.info(
            f"Assistant Task processing successful: title={title}, response={response.get('answer', 'No answer')[:200]}, total_time={elapsed_time:.2f}s"
        )

        return {
            "status": "SUCCESS",
            "summary": f"Assistant: {title[:30]}... for {user_id}",
            "data": {
                "parent_thread_id": chat_thread_id,
                "child_thread_id": child_thread_id,
                "user_id": user_id,
                "title": title,
            },
        }

    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Assistant Task processing failed: title={title}, total_time={elapsed_time:.2f}s, error={str(e)}",
            exc_info=True,
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Assistant Task failed, retrying: title={title}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Assistant Task failed after all retries: title={title}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        return {
            "status": "FAILED",
            "summary": f"Assistant Failed: {title[:30]}...",
            "data": {
                "parent_thread_id": chat_thread_id,
                "child_thread_id": None,
                "user_id": user_id,
                "title": title,
            },
            "error": str(e),
        }
