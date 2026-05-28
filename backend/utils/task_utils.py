# Custom libraries
from logger import configure_logging

# Default libraries
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Dict
from uuid import UUID
import base64

# Database modules
from models.email import Email
from repository.email_repository import EmailRepository
from repository.agent_task_repository import AgentTaskRepository

# from repository.task_progress_repository import TaskProgressRepository
from sqlalchemy.orm import Session

# Installed libraries
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

# Email events
from utils.email_events import EmailEventType, create_email_event


logger = configure_logging(__name__)


# def update_task_progress(
#     db,
#     email_id: str,
#     step_code: str,
#     status: Optional[str] = None,
#     started_at: Optional[datetime] = None,
# ):
#     try:
#         if status:
#             executed_at = datetime.now()
#             execution_time = None

#             # Prepare task progress data only with non-null values
#             task_progress_data = {
#                 "status": status,
#                 "executed_at": executed_at,
#                 "updated_at": datetime.now(),
#             }

#             # Only add started_at if it's not None
#             if started_at:
#                 execution_time = (executed_at - started_at).total_seconds() * 1000
#                 task_progress_data["started_at"] = started_at
#                 task_progress_data["execution_time"] = execution_time

#             task_progress_repository = TaskProgressRepository(db)
#             updated_task_progress = task_progress_repository.update_task_progress(
#                 email_id, step_code, task_progress_data
#             )
#             if not updated_task_progress:
#                 logger.error(f"Failed to update task progress for email: {email_id}")
#                 return None
#             return updated_task_progress
#         else:
#             return None
#     except SQLAlchemyError as e:
#         logger.error(f"SQLAlchemy Error: {e}")
#         return None
#     except Exception as e:
#         logger.error(f"Unexpected error occurred: {e}")
#         return None


def update_email_events(db, email_id: str, status_entry: Optional[Dict] = None):
    """
    Update the events list of a given email with a new status entry.
    """
    try:
        email_repo = EmailRepository(db)
        email = email_repo.get_email_by_id(email_id)

        if not email:
            logger.error(f"Email not found for updating events: {email_id}")
            return None

        # Always reload existing events
        current_events = list(email.events) if email.events else []
        current_events.append(status_entry)

        update_data = {"events": current_events}

        updated_email = email_repo.update_email(email_id, update_data)

        if not updated_email:
            logger.error(f"Failed to update events for email: {email_id}")
            return None

        return updated_email

    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy Error while updating email events: {e}")
        db.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error while updating email events: {e}")
        db.rollback()
        return None


def update_email_status(db, email_id: str, status: Optional[str] = None):
    try:
        if status:
            email_data = {
                "status": status,
            }
            email_repository = EmailRepository(db)
            updated_email = email_repository.update_email(email_id, email_data)
            if not updated_email:
                logger.error(f"Failed to update task status for email: {email_id}")
                return None
            return updated_email
        else:
            return None
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        return None


def update_email_execution_time(
    db: Session, email_id: str, elapsed_time: Optional[float] = None
) -> Optional[Email]:
    """
    Updates the execution time for an email by accumulating elapsed time or resetting it.

    Args:
        db (Session): SQLAlchemy database session.
        email_id (str): The unique identifier (UUID or message_id) of the email.
        elapsed_time (Optional[float]): The time elapsed to add to the current execution time.
            - If provided (including 0.0), it will be accumulated with the existing execution time.
            - If None, the execution time will be reset to 0.0.

    Returns:
        Optional[Email]: The updated Email object if successful, None otherwise.

    Raises:
        Logs errors for SQLAlchemy exceptions and general exceptions.
    """
    try:
        email_repository = EmailRepository(db)
        email = email_repository.get_email_by_id(email_id)

        if not email:
            logger.error(f"Email not found: {email_id}")
            return None

        additional_data = dict(email.additional_data or {})
        email_execution_time = additional_data.get("execution_time", 0.0)

        # If elapsed_time is provided (including 0.0), accumulate it; otherwise, reset to 0.0
        additional_data["execution_time"] = (
            email_execution_time + elapsed_time if elapsed_time is not None else 0.0
        )

        updated_email = email_repository.update_email(
            email_id, {"additional_data": additional_data}
        )

        if not updated_email:
            logger.error(f"Failed to update execution time for email: {email_id}")
            return None

        return updated_email

    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in update_email_execution_time: {e}")
        return None


def auto_adjust_column_width(worksheet, wrap_limit=40):
    try:
        # Iterate over each column in the worksheet, starting the index from 1 for column labels
        for col_idx, col in enumerate(worksheet.columns, start=1):
            # Calculate the maximum content length in the column
            max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col) + 5

            # Set the column width, constrained by the wrap_limit
            adjusted_width = min(max_len, wrap_limit)

            # Set the width of the current column based on the adjusted width
            worksheet.column_dimensions[get_column_letter(col_idx)].width = (
                adjusted_width
            )

    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred in auto_adjust_column_width: {e}")


def export_emails_to_excel(emails: List[dict], tasks_map: Dict[UUID, any] = None):
    """
    Pure data transformation function to export emails to Excel format.

    Args:
        emails: List of email objects with all related data
        tasks_map: Optional dict mapping email_id to task info (agent_tasks, total)
                   If None, will use email.agent_task_counts for task count

    Returns:
        Dictionary with Excel file data (mime_type, file_name, content)
    """
    try:
        # Convert the emails data into a list of lists with explicit columns
        emails_data = []

        # Use provided tasks_map or fall back to None
        tasks_map = tasks_map or {}

        for email in emails:
            # Extract task details from pre-fetched map or email attributes
            if tasks_map and email.id in tasks_map:
                task_result = tasks_map.get(email.id)
                task_ids = (
                    [str(task.id) for task in task_result.agent_tasks]
                    if task_result
                    else []
                )
                task_ids_str = "[" + ", ".join(task_ids) + "]"
                task_count = task_result.total if task_result else 0
            else:
                # Fall back to using email attributes (for backward compatibility)
                task_ids_str = "[]"
                task_count = (
                    email.agent_task_counts.get("TOTAL", 0)
                    if hasattr(email, "agent_task_counts") and email.agent_task_counts
                    else 0
                )

            # Format received_at
            received_date = (
                email.received_at.strftime("%Y/%m/%d") if email.received_at else None
            )
            received_time = (
                email.received_at.strftime("%I:%M:%S %p") if email.received_at else None
            )

            # Format created_at
            created_date = (
                email.created_at.strftime("%Y/%m/%d") if email.created_at else None
            )
            created_time = (
                email.created_at.strftime("%I:%M:%S %p") if email.created_at else None
            )

            emails_data.append(
                [
                    email.id,
                    task_count,
                    email.email_id,
                    email.mailbox_email,
                    email.subject,
                    email.status,
                    received_date,
                    received_time,
                    created_date,
                    created_time,
                    task_ids_str,
                    email.mailbox_folder,
                    email.sender_name,
                    email.email_body,
                ]
            )

        # Columns in your exact order
        columns = [
            "Email ID",
            "Total Task Count",
            "Sender Email ID",
            "Mailbox Email",
            "Subject",
            "Status",
            "Received At Date",
            "Received At Time",
            "Created At Date",
            "Created At Time",
            "Task Id Array",
            "Mailbox Folder",
            "Sender Name",
            "Email Body",
        ]

        # Create a pandas DataFrame with defined columns
        df = pd.DataFrame(emails_data, columns=columns)

        # Save the DataFrame to an Excel file in memory
        stream = BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Emails")

            # Get the Excel workbook and worksheet objects
            worksheet = writer.sheets["Emails"]

            # Auto-adjust the column widths based on content
            auto_adjust_column_width(worksheet)

        # Set the stream position to the beginning
        stream.seek(0)

        # Now the file has been fully created; encode the file content as base64
        excel_file_base64 = base64.b64encode(stream.getvalue()).decode("utf-8")

        # Define the file name and MIME type
        date_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{date_time}_emails.xlsx"
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return {
            "mime_type": mime_type,
            "file_name": file_name,
            "content": excel_file_base64,
        }

    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")


def export_agent_tasks_to_excel(
    agent_tasks: List[dict], emails: List[dict], outputs_map: Dict[UUID, dict] = None
):
    """
    Pure data transformation function to export agent tasks to Excel format.

    Args:
        agent_tasks: List of agent task objects with all related data
        emails: List of email objects
        outputs_map: Optional dict mapping task_id to output info (attempts)
                     If None, will set attempt count to 0

    Returns:
        Dictionary with Excel file data (mime_type, file_name, content)
    """
    try:
        # Convert the agent tasks data into a list of lists with explicit columns
        agent_tasks_data = []

        # Use provided outputs_map or fall back to empty dict
        outputs_map = outputs_map or {}

        # Create email lookup map for faster access
        email_map = {email.id: email for email in emails}

        for agent_task in agent_tasks:
            # Use email map for O(1) lookup instead of O(N) list search
            email = email_map.get(agent_task.email_data_id)

            attachment_names = [
                attachment.file_name
                for attachment in agent_task.attachment_details.attachments
            ]

            attachment_urls = [
                attachment.remote_url
                for attachment in agent_task.attachment_details.attachments
            ]

            # Get the latest progress status if available
            progress_list = agent_task.progress
            latest_status = progress_list[-1].status if progress_list else None

            # Get attempt count from pre-fetched outputs map
            output_data = outputs_map.get(agent_task.id)
            attempt = (
                len(output_data["attempts"])
                if output_data and output_data.get("attempts")
                else 0
            )

            # openpyxl cannot write timezone-aware datetimes; match email export (strings)
            completed_at = (
                agent_task.completed_at.strftime("%Y/%m/%d %I:%M:%S %p")
                if agent_task.completed_at
                else None
            )

            agent_tasks_data.append(
                [
                    agent_task.id,
                    agent_task.email_data_id,
                    email.email_id if email else None,
                    agent_task.title,
                    agent_task.task_order,
                    latest_status,
                    email.status if email else None,
                    completed_at,
                    attempt,
                    agent_task.agent_name,
                    attachment_names,
                    attachment_urls,
                ]
            )

        # Define the column headers
        columns = [
            "Agent Task ID",
            "Email UUID",
            "Sender Email ID",
            "Title",
            "Task Order",
            "Task Status",
            "Email Status",
            "Completed At",
            "Attempt",
            "Agent",
            "Attachment Names",
            "Attachment URLs",
        ]

        # Create a pandas DataFrame with defined columns
        df = pd.DataFrame(agent_tasks_data, columns=columns)

        # Save the DataFrame to an Excel file in memory
        stream = BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Agent Tasks")

            # Get the Excel workbook and worksheet objects
            worksheet = writer.sheets["Agent Tasks"]

            # Auto-adjust the column widths based on content
            auto_adjust_column_width(worksheet)

        # Set the stream position to the beginning
        stream.seek(0)

        # Now the file has been fully created; encode the file content as base64
        excel_file_base64 = base64.b64encode(stream.getvalue()).decode("utf-8")

        # Define the file name and MIME type
        date_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{date_time}_agent_tasks.xlsx"
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return {
            "mime_type": mime_type,
            "file_name": file_name,
            "content": excel_file_base64,
        }

    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")


def update_task_execution_time(
    db: Session, email_uuid: UUID
) -> Optional[Dict[str, any]]:
    """
    Calculate the total execution time for all tasks related to a specific email.
    Distributes the email's total execution time evenly across all active tasks.

    Args:
        db (Session): SQLAlchemy database session
        email_uuid (UUID): Email UUID to calculate execution time for

    Returns:
        Optional[Dict]: Dictionary containing:
            - email_uuid: str
            - execution_time: float
        Returns None if an error occurs.
    """
    try:
        email_repository = EmailRepository(db)
        email = email_repository.get_email_by_id(email_uuid)
        if not email:
            logger.error(f"Email not found: {email_uuid}")
            return None

        additional_data = email.additional_data or {}
        execution_time = additional_data.get("execution_time", 0.0)

        # Calculate average execution time for tasks and update each task
        agent_task_repository = AgentTaskRepository(db)
        email_agent_tasks = agent_task_repository.get_agent_tasks_by_email(
            email_uuid=email_uuid
        )
        counts = email_agent_tasks.agent_task_counts
        total = counts.get("TOTAL", 0)
        average_execution_time = execution_time / total if total > 0 else 0
        for agent_task in email_agent_tasks.agent_tasks:
            task_additional_data = agent_task.additional_data or {}
            task_additional_data["execution_time"] = average_execution_time
            agent_task_repository.update_task(
                agent_task.id, {"additional_data": task_additional_data}
            )

        return {
            "email_uuid": str(email_uuid),
            "execution_time": execution_time,
        }

    except Exception as exc:
        logger.error(
            f"Failed to finalize email execution time {email_uuid}: {exc}",
            exc_info=True,
        )
        return None


def finalize_email_status(db: Session, email_uuid: UUID) -> Optional[Dict]:
    """
    Determine final email status based on agent task statuses,
    create audit trail events, and return summary details.

    This consolidated function:
    - Considers SUCCESSFUL, RESOLVED, INCOMPLETE, and FAILED task statuses
    - Excludes ARCHIVED tasks from calculations (handled by repository)
    - Sets email status to FAILED if there are no active tasks (total == 0)
    - Creates email events for audit trail
    - Returns detailed summary dict

    Args:
        db (Session): SQLAlchemy database session
        email_uuid (UUID): Email UUID to finalize status for

    Returns:
        Optional[Dict]: Dictionary containing:
            - email_uuid: str
            - final_status: str (SUCCESSFUL/FAILED/INCOMPLETE)
            - successful_tasks: int
            - resolved_tasks: int
            - incomplete_tasks: int
            - failed_tasks: int
            - total_tasks: int
        Returns None if an error occurs.
    """
    try:
        agent_task_repository = AgentTaskRepository(db)
        email_agent_tasks = agent_task_repository.get_agent_tasks_by_email(
            email_uuid=email_uuid
        )

        counts = email_agent_tasks.agent_task_counts
        successful = counts.get("SUCCESSFUL", 0)
        resolved = counts.get("RESOLVED", 0)
        incomplete = counts.get("INCOMPLETE", 0)
        failed = counts.get("FAILED", 0)
        paused = counts.get("PAUSED", 0)
        archived = counts.get("ARCHIVED", 0)
        total = counts.get("TOTAL", 0)

        # Create email events for audit trail
        email_event_counts = [
            (successful, EmailEventType.AGENT_TASK_SUCCESSFUL),
            (incomplete, EmailEventType.AGENT_TASK_INCOMPLETE),
            (failed, EmailEventType.AGENT_TASK_FAILED),
        ]

        for count, event_type in email_event_counts:
            for _ in range(count):
                create_email_event(db, email_uuid, event_type)

        # Determine email status
        if paused > 0:
            # Any task paused for human review → email is paused
            status = "PAUSED"
        elif total == 0 and archived > 0:
            # All tasks are archived
            status = "ARCHIVED"
        elif resolved == total:
            # All active tasks are resolved
            status = "RESOLVED"
        elif successful + resolved == total:
            # All active tasks are successful or resolved
            status = "SUCCESSFUL"
        elif failed == total:
            # All active tasks failed
            status = "FAILED"
        elif total == 0:
            # No active tasks (excludes ARCHIVED) - consider as FAILED
            status = "FAILED"
        else:
            # Mixed status - some tasks succeeded, some failed/incomplete
            status = "INCOMPLETE"

        # Update email status in database
        update_email_status(db, email_uuid, status)

        return {
            "email_uuid": str(email_uuid),
            "final_status": status,
            "successful_tasks": successful,
            "resolved_tasks": resolved,
            "incomplete_tasks": incomplete,
            "failed_tasks": failed,
            "paused_tasks": paused,
            "total_tasks": total,
        }

    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy Error in finalize_email_status: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error in finalize_email_status for email {email_uuid}: {e}",
            exc_info=True,
        )
        return None
