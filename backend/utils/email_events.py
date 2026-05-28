# Custom libraries
from logger import configure_logging

# Database modules
from repository.task_event_repository import TaskEventRepository
from sqlalchemy.orm import Session

# Default libraries
from uuid import UUID


logger = configure_logging(__name__)


class EmailEvent:
    """
    Represents an email event with a name, key, and description.

    Attributes:
        name (str): Name of the email event.
        key (str): Unique key derived from the name.
        description (str): Description of the email event.
    """

    def __init__(self, name: str, description: str, event_type: str):
        self.name = name
        self.key = name.lower().replace(" ", "_")
        self.description = description
        self.event_type = event_type


class EmailEventType:
    """
    Predefined email events with name and description for email event tracking.
    """

    # Backend Worker Events
    EMAIL_FETCH_SUCCESSFUL = EmailEvent(
        name="Email fetch successful",
        description="Email successfully retrieved from the mailbox folder.",
        event_type="success",
    )

    # Attachment Worker Events
    ATTACHMENT_PROCESS_QUEUED = EmailEvent(
        name="Attachment process queued",
        description="Email added to the attachment processing queue.",
        event_type="queued",
    )
    ATTACHMENT_PROCESS_EXECUTING = EmailEvent(
        name="Attachment process executing",
        description="Email attachments are currently being analyzed and processed.",
        event_type="execution",
    )
    ATTACHMENT_PROCESS_SUCCESSFUL = EmailEvent(
        name="Attachment process successful",
        description="Email attachments processed successfully and ready for downstream tasks.",
        event_type="success",
    )
    ATTACHMENT_PROCESS_FAILED = EmailEvent(
        name="Attachment process failed",
        description="Email attachment processing encountered an error and could not complete.",
        event_type="failure",
    )

    # Agent Worker Events
    AGENT_WORKER_QUEUED = EmailEvent(
        name="Agent worker queued",
        description="Agent worker processing scheduled and awaiting execution.",
        event_type="queued",
    )
    AGENT_DISPATCH_STARTED = EmailEvent(
        name="Agent dispatch started",
        description="Agent dispatch initiated to process email tasks.",
        event_type="execution",
    )
    AGENT_DISPATCH_SUCCESSFUL = EmailEvent(
        name="Agent dispatch successful",
        description="Agent dispatch completed successfully, tasks assigned for execution.",
        event_type="success",
    )
    AGENT_DISPATCH_FAILED = EmailEvent(
        name="Agent dispatch failed",
        description="Agent dispatch encountered an error and could not proceed.",
        event_type="failure",
    )
    AGENT_TASK_EXECUTING = EmailEvent(
        name="Agent task executing",
        description="Agent is currently performing assigned task(s).",
        event_type="execution",
    )
    AGENT_TASK_SUCCESSFUL = EmailEvent(
        name="Agent task successful",
        description="Agent successfully completed all the assigned task(s).",
        event_type="success",
    )
    AGENT_TASK_INCOMPLETE = EmailEvent(
        name="Agent task incomplete",
        description="Agent did not complete all the assigned task(s).",
        event_type="failure",
    )
    AGENT_TASK_FAILED = EmailEvent(
        name="Agent task failed",
        description="Agent failed to process the assigned task(s) due to some errors.",
        event_type="failure",
    )


def create_email_event(db: Session, email_uuid: UUID, email_event: EmailEvent) -> bool:
    """
    Creates or updates an email event with count tracking for a specific email.

    Args:
        db: Database session.
        email_event: EmailEvent to be created or updated.
        email_uuid: UUID of the email.

    Returns:
        bool: True if successful, otherwise False.
    """
    try:
        task_event_repository = TaskEventRepository(db)

        # Check if an event with the email and key already exists
        existing_task_event = task_event_repository.get_task_event_by_email_and_key(
            email_uuid=email_uuid, key=email_event.key
        )

        # Increment count if task event exists
        if existing_task_event:
            update_data = {"count": existing_task_event.count + 1}
            updated_task_event = task_event_repository.update_task_event(
                event_uuid=existing_task_event.id, update_data=update_data
            )
            if not updated_task_event:
                logger.error(f"Failed to update email event for email: {email_uuid}")
                return False
            return True

        # Create new event if it doesn't exist
        new_event_data = {
            "email_data_id": email_uuid,
            "name": email_event.name,
            "key": email_event.key,
            "description": f"{email_event.description}",
            "count": 1,
            "additional_data": {"event_type": email_event.event_type},
        }
        created_task_event = task_event_repository.create_task_event(new_event_data)
        if not created_task_event:
            logger.error(f"Failed to create email event for email: {email_uuid}")
            return False
        return True

    except Exception as e:
        logger.error(f"Error in create_email_event: {e}")
        return False
