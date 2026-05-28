from celery import shared_task, chord, group
from celery.exceptions import SoftTimeLimitExceeded
from logger import configure_logging
from integrations.office_365.attachment import Attachment
from utils.task_utils import update_email_status, update_email_execution_time
from utils.email_events import create_email_event, EmailEventType
from utils.notification import Notification
from workers.agent_worker import dispatch_task
from db_pool import DatabasePoolManager
import time
from utils.external_task import ExternalTask

# Initialize the DatabasePoolManager
db_pool = DatabasePoolManager()
logger = configure_logging(__name__)


# Define tasks for the attachment-worker queue
@shared_task(
    name="process_attachment",
    queue="attachment_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def process_attachment(self, organization_schema: str, message_data: dict):
    email_uuid = message_data.get("email_uuid") or message_data.get(
        "saved_message", {}
    ).get("id")
    attachment_count = message_data.get("attachment_count", 1)
    start_time = time.time()

    logger.info(
        f"Received new worker task: attachment-worker-staging, email_uuid={email_uuid}, attachment_count={attachment_count}"
    )

    try:
        with db_pool.get_session(organization_schema) as db:
            # Stage attachments using service helper
            attachment_service = Attachment(db)
            staged_ids = attachment_service.stage_attachments(message_data)
            elapsed_time = time.time() - start_time
            if not staged_ids:
                logger.error(
                    f"Attachment processing failed: email_uuid={email_uuid}, total_time={elapsed_time:.2f}s, attachments=0, parts=0, status=failed"
                )

                # Create email event
                create_email_event(
                    db,
                    email_uuid,
                    EmailEventType.ATTACHMENT_PROCESS_FAILED,
                )

                # Update email status to FAILED
                update_email_status(db, email_uuid, "FAILED")

                # Send email failure notification
                notification = Notification(db=db)
                notification.notify_email_failure(
                    email_id=email_uuid, failed_process="Attachment Processing"
                )

                return {
                    "status": "FAILED",
                    "summary": "Attachment staging failed",
                    "data": {"email_uuid": email_uuid},
                    "error": "0 attachments staged",
                }

            update_email_execution_time(db, email_uuid, elapsed_time)

            # Build task chains - vision correction now handled in PDF parser
            polling_config = message_data.get("polling_config") or {}

            # Extract priority for task routing (0=highest/default, 9=lowest)
            priority = (
                polling_config.get("mailbox_priority", 0) if polling_config else 0
            )

            # Pass through the complete polling config - vision correction handled in PDF parser
            task_sigs = []
            for staged_id in staged_ids:
                task_sigs.append(
                    parse_attachment.s(
                        organization_schema, staged_id, email_uuid, polling_config
                    )
                )

            # When all chains complete, dispatch email routing with priority
            dispatch_callback = dispatch_task.si(organization_schema, email_uuid).set(
                priority=priority
            )
            chord_result = chord(group(task_sigs))(dispatch_callback)

            # Log chord creation for debugging
            logger.info(
                f"Created chord for dispatch task: email_uuid={email_uuid}, "
                f"attachment_count={len(staged_ids)}, "
                f"priority={priority}, "
                f"chord_id={chord_result.id if hasattr(chord_result, 'id') else 'N/A'}"
            )

            staging_time = time.time() - start_time
            logger.info(
                f"Attachment staging successful: email_uuid={email_uuid}, parts={len(staged_ids)}, time={staging_time:.2f}s"
            )

            # Create email event
            create_email_event(
                db,
                email_uuid,
                EmailEventType.AGENT_WORKER_QUEUED,
            )

            return {
                "status": "SUCCESS",
                "summary": f"{len(staged_ids)} attachments staged",
                "data": {
                    "email_uuid": email_uuid,
                    "staged_count": len(staged_ids),
                    "staged_ids": staged_ids,
                },
            }

    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Attachment processing failed: email_uuid={email_uuid}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Attachment processing failed, retrying: email_uuid={email_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Attachment processing failed after all retries: email_uuid={email_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        with db_pool.get_session(organization_schema) as db:
            create_email_event(
                db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_FAILED
            )
            update_email_status(db, email_uuid, "FAILED")
            notification = Notification(db=db)
            notification.notify_email_failure(
                email_id=email_uuid, failed_process="Attachment Processing"
            )

        return {
            "status": "FAILED",
            "summary": "Attachment staging failed",
            "data": {"email_uuid": email_uuid},
            "error": str(e),
        }


@shared_task(
    name="parse_attachment",
    queue="attachment_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def parse_attachment(
    self,
    organization_schema: str,
    attachment_uuid: str,
    email_uuid: str,
    polling_config: dict = None,
):
    """Thin wrapper around Attachment.parse_attachment."""
    logger.info(
        f"Received new worker task: attachment-worker-parse, attachment_uuid={attachment_uuid}"
    )
    start_time = time.time()
    try:
        with db_pool.get_session(organization_schema) as db:
            # Create email event
            create_email_event(
                db,
                email_uuid,
                EmailEventType.ATTACHMENT_PROCESS_EXECUTING,
            )

            service = Attachment(db)
            service_result = service.parse_attachment(
                attachment_uuid, polling_config or {}
            )
            elapsed_time = time.time() - start_time

            update_email_execution_time(db, email_uuid, elapsed_time)

            # Create email event
            create_email_event(
                db,
                email_uuid,
                EmailEventType.ATTACHMENT_PROCESS_SUCCESSFUL,
            )

            # Log used for counting: successful parsing
            logger.info(
                f"Attachment parsing successful: attachment_uuid={attachment_uuid}, total_time={elapsed_time:.2f}s"
            )
            return {
                "status": "SUCCESS",
                "summary": f"Successfully parsed attachment {str(attachment_uuid)}",
                "data": {"attachment_uuid": attachment_uuid},
            }
    except SoftTimeLimitExceeded:
        logger.warning(f"Attachment parsing timeout: attachment_uuid={attachment_uuid}")
        raise Exception("Attachment parsing timeout")

    except Exception as e:
        elapsed_time = time.time() - start_time

        logger.error(
            f"Attachment parsing failed: attachment_uuid={attachment_uuid}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Attachment parsing failed, retrying: attachment_uuid={attachment_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        # Note: Don't update email status here - this is a subtask in a chord.
        # Other attachments may succeed, and dispatch_task will handle the email.
        logger.error(
            f"Attachment parsing failed after all retries: attachment_uuid={attachment_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        with db_pool.get_session(organization_schema) as db:
            create_email_event(
                db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_FAILED
            )

        return {
            "status": "FAILED",
            "summary": "Attachment parsing failed",
            "data": {"attachment_uuid": attachment_uuid, "email_uuid": email_uuid},
            "error": str(e),
        }


@shared_task(
    name="process_task_attachments",
    queue="attachment_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def process_task_attachments(self, organization_schema: str, task_data: dict):
    """
    Shared task for processing external attachments.
    Mimics the structure of process_attachment exactly.
    """
    start_time = time.time()

    saved_message = task_data.get("saved_message")
    if not saved_message:
        logger.error("Missing saved_message in task_data")

    email_uuid = saved_message.get("id")
    logger.info(f"Started external task attachment processing: email_uuid={email_uuid}")

    try:
        with db_pool.get_session(organization_schema) as db:
            # # Create EXECUTING event
            # create_email_event(
            #     db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_EXECUTING
            # )

            # Process external attachments
            external_task = ExternalTask(db=db, organization_schema=organization_schema)
            staged_ids = external_task.process_documents(
                external_task_data=task_data.get("external_task_data"),
                saved_message=saved_message,
            )
            staged_ids = [str(att.id) for att in staged_ids]

            # Build task chain for parsing attachments
            polling_config = (
                task_data.get("external_task_data", {}).get("task_configs") or {}
            )

            # Extract priority for task routing (0=highest/default, 9=lowest)
            priority = (
                polling_config.get("mailbox_priority", 0) if polling_config else 0
            )

            task_sigs = [
                parse_attachment.s(
                    organization_schema, attachment_uuid, email_uuid, polling_config
                )
                for attachment_uuid in staged_ids
            ]

            # Chord to dispatch after parsing all attachments with priority
            dispatch_callback = dispatch_task.si(organization_schema, email_uuid).set(
                priority=priority
            )
            chord_result = chord(group(task_sigs))(dispatch_callback)

            logger.info(
                f"Created chord for external task dispatch: email_uuid={email_uuid}, "
                f"attachment_count={len(staged_ids)}, "
                f"priority={priority}, "
                f"chord_id={getattr(chord_result, 'id', 'N/A')}"
            )

            # # Create SUCCESSFUL and QUEUED events
            # create_email_event(
            #     db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_SUCCESSFUL
            # )
            create_email_event(db, email_uuid, EmailEventType.AGENT_WORKER_QUEUED)

            elapsed_time = time.time() - start_time
            logger.info(
                f"External attachment processing completed: email_uuid={email_uuid}, time={elapsed_time:.2f}s"
            )

            return {
                "status": "SUCCESS",
                "summary": f"{len(staged_ids)} external attachments processed",
                "data": {
                    "email_uuid": email_uuid,
                    "staged_count": len(staged_ids),
                    "staged_ids": staged_ids,
                },
            }

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            f"External task processing failed: email_uuid={email_uuid}, total_time={elapsed_time:.2f}s, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"External task processing failed, retrying: email_uuid={email_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"External task processing failed after all retries: email_uuid={email_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        with db_pool.get_session(organization_schema) as db:
            create_email_event(
                db, email_uuid, EmailEventType.ATTACHMENT_PROCESS_FAILED
            )
            update_email_status(db, email_uuid, "FAILED")

        return {
            "status": "FAILED",
            "summary": "External task processing failed",
            "data": {"email_uuid": email_uuid},
            "error": str(e),
        }
