# Default libraries
import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID

# Installed libraries
from celery import shared_task, chord, group

# Custom libraries
from agents.task_dispatcher.dispatcher import TaskDispatcher
from agents.task_agent.executor import TaskExecutor
from db_pool import DatabasePoolManager
from logger import configure_logging
from utils.notification import Notification
from repository.agent_task_repository import AgentTaskRepository
from repository.email_repository import EmailRepository
from utils.task_utils import (
    update_email_status,
    update_email_execution_time,
    update_task_execution_time,
    finalize_email_status,
)
from utils.email_events import create_email_event, EmailEventType
from celery.exceptions import SoftTimeLimitExceeded
import time

# Initialize the DatabasePoolManager
db_pool = DatabasePoolManager()
logger = configure_logging(__name__)


class TaskExecutionError(Exception):
    """Raised when task execution fails (FAILED, INCOMPLETE, TIMEOUT)"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def handle_task_failure(
    organization_schema: str,
    email_uuid: str,
    error: Exception,
    failure_type: str,
    email_event_type: Optional[EmailEventType] = None,
    task_uuid: Optional[UUID] = None,
    update_status: bool = True,
    thread_id: Optional[str] = None,
) -> dict:
    """
    Helper function for handling failures in dispatch_task, execute_task, and finalize_email.

    This function optionally marks the email as FAILED and sends notifications based on
    failure_type. It should only be called when retries are exhausted (final failure state).

    Notification rules (based on failure_type):
        - "Task Dispatch": Uses notify_email_failure
        - "Task Execution": Uses notify_task_failure (requires task_uuid)
        - "Email Finalization": No notifications

    Args:
        organization_schema: Database schema name
        email_uuid: Email UUID
        error: Exception that caused the failure
        failure_type: Type of failure - determines notification behavior:
                      "Task Dispatch" → notify_email_failure
                      "Task Execution" → notify_task_failure
                      "Email Finalization" → no notification
        email_event_type: Optional email event type to create
        task_uuid: Optional task UUID (required for "Task Execution" notifications)
        update_status: Whether to update email status to FAILED (default True).
                       Set to False for execute_task since finalize_email handles email status.
        thread_id: Optional thread ID (for task execution context)

    Returns:
        Standardized failure response dictionary
    """
    with db_pool.get_session(organization_schema) as db:
        email_uuid_obj = UUID(str(email_uuid))

        # Create email event if specified
        if email_event_type:
            create_email_event(db, email_uuid_obj, email_event_type)

        # Update email status to FAILED (skip for execute_task failures)
        if update_status:
            update_email_status(db, email_uuid_obj, "FAILED")

        # Send notification based on failure_type
        if failure_type == "Task Dispatch":
            notification = Notification(db=db)
            notification.notify_email_failure(
                email_id=email_uuid_obj,
                failed_process=failure_type,
            )
        elif failure_type == "Task Execution" and task_uuid:
            notification = Notification(db=db)
            notification.notify_task_failure(
                email_id=email_uuid_obj,
                task_id=task_uuid,
                failed_process=failure_type,
            )
        # "Email Finalization" - no notification sent

    # Return standardized failure response
    return {
        "status": "FAILED",
        "summary": f"{failure_type} failed",
        "data": {
            "email_uuid": str(email_uuid),
            **({"task_uuid": str(task_uuid)} if task_uuid else {}),
            **({"thread_id": thread_id} if thread_id else {}),
        },
        "error": str(error),
    }


@shared_task(
    name="dispatch_task",
    queue="agent_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def dispatch_task(self, organization_schema: str, email_uuid: str):
    """
    Dispatch task that routes email and creates chord with execute tasks.
    Retry config: max_retries=1 (2 total attempts), default_retry_delay=30s.
    """
    start_time = time.time()

    logger.info(
        f"Received new worker task: agent-worker-dispatch, email_uuid={email_uuid}"
    )

    try:
        with db_pool.get_session(organization_schema) as db:
            # Create email event
            create_email_event(db, email_uuid, EmailEventType.AGENT_DISPATCH_STARTED)

            # Use route_task to get task_ids and agent_id
            task_dispatcher = TaskDispatcher(db, organization_schema)
            task_ids, agent_id = task_dispatcher.dispatch_task(email_uuid=email_uuid)

            elapsed_time = time.time() - start_time

            update_email_execution_time(db, email_uuid, elapsed_time)

            if task_ids:
                logger.info(
                    f"Finished agent task dispatch for email_uuid: {email_uuid}. task_count: {len(task_ids)}"
                )

                # Create email event
                create_email_event(
                    db, email_uuid, EmailEventType.AGENT_DISPATCH_SUCCESSFUL
                )

                # Create execute task signatures with agent_id included
                execute_sigs = []
                for task_id in task_ids:
                    task_data = {
                        "task_id": task_id,
                        "email_uuid": email_uuid,
                        "agent_id": str(agent_id),  # Include agent_id
                    }
                    execute_sigs.append(execute_task.s(organization_schema, task_data))

                # Create chord: when all execute tasks complete, finalize email status
                cb = finalize_email.si(organization_schema, email_uuid)
                chord_result = chord(group(execute_sigs))(cb)

                logger.info(
                    f"Created chord for task execution: email_uuid={email_uuid}, "
                    f"task_count={len(task_ids)}, "
                    f"chord_id={chord_result.id if hasattr(chord_result, 'id') else 'N/A'}"
                )

                return {
                    "status": "SUCCESS",
                    "summary": f"{len(task_ids)} agent tasks created",
                    "data": {
                        "email_uuid": email_uuid,
                        "agent_id": str(agent_id),
                        "task_count": len(task_ids),
                        "task_ids": task_ids,
                    },
                }

            else:
                # No agents assigned - raise exception to trigger retry
                logger.warning(
                    f"Agent task dispatch unsuccessful: email_uuid={email_uuid}"
                )
                raise Exception("No Agent assigned for task")

    except Exception as e:
        logger.error(
            f"Agent task dispatch failed: email_uuid={email_uuid}, error={str(e)}"
        )

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Dispatch failed, retrying: email_uuid={email_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Dispatch failed after all retries: email_uuid={email_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        return handle_task_failure(
            organization_schema=organization_schema,
            email_uuid=email_uuid,
            error=e,
            failure_type="Task Dispatch",
            email_event_type=EmailEventType.AGENT_DISPATCH_FAILED,
        )


@shared_task(
    name="execute_task",
    queue="agent_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def execute_task(self, organization_schema: str, task_data: dict):
    """
    Execute task that processes individual tasks without email status updates.
    Retries on exceptions and FAILED/INCOMPLETE status.
    Retry config: max_retries=1 (2 total attempts), default_retry_delay=30s.
    """
    task_uuid = UUID(str(task_data["task_id"]))
    email_uuid = UUID(str(task_data["email_uuid"]))
    agent_id = task_data.get("agent_id")
    thread_id = task_data.get("thread_id")
    additional_data = task_data.get("additional_data", {})
    agent_config = {}
    start_time = time.time()

    logger.info(
        f"Received new worker task: agent-worker-execute, email_uuid={email_uuid}, task_id={task_uuid}, thread_id={thread_id}, agent_id={agent_id}"
    )
    try:
        with db_pool.get_session(organization_schema) as db:
            # Fetch agent config from database using agent_id
            if agent_id:
                from repository.agent_repository import AgentRepository

                agent_repo = AgentRepository(db)
                agent_data = agent_repo.get_agent(UUID(agent_id))
                if agent_data:
                    agent_config = agent_data.agent_config or {}

            # Create email event
            create_email_event(db, email_uuid, EmailEventType.AGENT_TASK_EXECUTING)

            # Run the asynchronous execute_task method with proper cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                executor = TaskExecutor(db=db, organization_schema=organization_schema)
                result_output, task_status = loop.run_until_complete(
                    executor.execute_task(
                        task_id=task_uuid,
                        thread_id=thread_id,
                        additional_data=additional_data,
                    )
                )

            except Exception as e:
                logger.error(f"Error in execute_task: {e}")
                task_repo = AgentTaskRepository(db)
                task_repo.append_task_progress(
                    task_uuid, {"status": "FAILED", "timestamp": str(datetime.now())}
                )
                raise TaskExecutionError(reason=str(e))
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

            # Handle task completion
            if result_output and task_status == "SUCCESSFUL":
                # Log used for counting: successful tasks
                logger.info(
                    f"Task execution completed successfully: task_id={task_uuid}, email_uuid={email_uuid}, output_id={result_output.id}"
                )

                elapsed_time = time.time() - start_time

                update_email_execution_time(db, email_uuid, elapsed_time)

                # Check if we should finalize email status after task completion
                if task_data.get("finalize_email", False):
                    logger.info(
                        f"Triggering email status finalization: email_uuid={email_uuid}"
                    )
                    finalize_email.delay(
                        organization_schema,
                        str(email_uuid),
                    )

                return {
                    "status": task_status,
                    "summary": f"Task executed successfully",
                    "data": {
                        "task_uuid": str(task_uuid),
                        "email_uuid": str(email_uuid),
                        "thread_id": thread_id,
                        "output_id": str(result_output.id),
                        "task_status": task_status,
                    },
                }
            elif task_status == "PAUSED":
                logger.info(
                    f"Task paused for review: task_id={task_uuid}, email_uuid={email_uuid}"
                )

                elapsed_time = time.time() - start_time
                update_email_execution_time(db, email_uuid, elapsed_time)
                update_email_status(db, email_uuid, "PAUSED")

                return {
                    "status": "PAUSED",
                    "summary": "Task paused for human review",
                    "data": {
                        "task_uuid": str(task_uuid),
                        "email_uuid": str(email_uuid),
                        "thread_id": thread_id,
                        "task_status": "PAUSED",
                    },
                }
            else:
                # Task failed or incomplete - raise exception to trigger retry
                logger.warning(
                    f"Task execution unsuccessful: task_id={task_uuid}, status={task_status}"
                )
                raise TaskExecutionError(reason=task_status)

    except SoftTimeLimitExceeded:
        logger.warning(f"Task execution timeout: task_id={task_uuid}")
        raise TaskExecutionError(reason="TIMEOUT")

    except Exception as e:
        error_msg = e.reason if isinstance(e, TaskExecutionError) else str(e)
        disable_auto_retry = task_data.get("disable_auto_retry", False)

        # Check if INCOMPLETE task should not retry based on agent config
        is_incomplete_no_retry = (
            isinstance(e, TaskExecutionError)
            and e.reason == "INCOMPLETE"
            and not agent_config.get("retry_incomplete_tasks", False)
        )

        # Retry if we haven't exhausted retries and should retry
        if (
            self.request.retries < self.max_retries
            and not disable_auto_retry
            and not is_incomplete_no_retry
        ):
            logger.warning(
                f"Task execution failed, retrying: task_id={task_uuid}, email_uuid={email_uuid}, thread_id={thread_id}, error={error_msg}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted or auto-retry disabled
        logger.error(
            f"Task execution failed after all retries, finalizing: task_id={task_uuid}, email_uuid={email_uuid}, thread_id={thread_id}, retries_exhausted={self.request.retries}/{self.max_retries}, auto_retry_disabled={disable_auto_retry}, error={error_msg}"
        )

        # Trigger email finalization if needed
        if task_data.get("finalize_email", False):
            logger.info(
                f"Triggering email status finalization: email_uuid={email_uuid}"
            )
            finalize_email.delay(organization_schema, str(email_uuid))

        # Always notify task failure and return failure response
        # update_status=False since finalize_email handles email status
        return handle_task_failure(
            organization_schema=organization_schema,
            email_uuid=str(email_uuid),
            error=e,
            failure_type="Task Execution",
            task_uuid=task_uuid,
            update_status=False,
            thread_id=thread_id,
        )


@shared_task(
    name="finalize_email",
    queue="agent_queue",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def finalize_email(self, organization_schema: str, email_uuid: str):
    """
    Finalize function that updates email status based on all task execution results.
    This is the CALLBACK from dispatch_task's chord.
    Retry config: max_retries=1 (2 total attempts), default_retry_delay=30s.
    """
    logger.info(
        f"Chord callback triggered - Finalizing email execution: email_uuid={email_uuid}"
    )

    try:
        email_uuid_obj = UUID(str(email_uuid))

        with db_pool.get_session(organization_schema) as db:
            details = finalize_email_status(db, email_uuid_obj)
            if details is None:
                raise RuntimeError("Unable to finalize email status")

            details["email_uuid"] = email_uuid
            status = details["final_status"]
            successful = details["successful_tasks"]
            failed = details["failed_tasks"]
            total = details["total_tasks"]

            # event_map = {
            #     "SUCCESSFUL": EmailEventType.AGENT_TASK_SUCCESSFUL,
            #     "FAILED": EmailEventType.AGENT_TASK_FAILED,
            #     "INCOMPLETE": EmailEventType.AGENT_TASK_INCOMPLETE,
            # }
            # event = event_map.get(status)
            # if event:
            #     create_email_event(db, email_uuid_obj, event)

            logger.info(f"Email UUID {email_uuid} finalized with status: {status}")

            # Update task execution time
            update_task_execution_time(db, email_uuid_obj)
            logger.info(f"Task execution time updated for email: {email_uuid}")

            # Update execution time (only if requested)
            # if update_exec_time:
            #     exec_time_details = update_execution_time(db, email_uuid_obj)
            #     if exec_time_details:
            #         details["execution_time"] = exec_time_details.get("execution_time")
            #         logger.info(
            #             f"Email UUID {email_uuid} execution time: {details['execution_time']} seconds"
            #         )

            return {
                "status": "SUCCESS",
                "summary": f"Email {status}: {successful}/{total} tasks",
                "data": details,
            }

    except Exception as e:
        logger.error(f"Error in finalize_email: {e}")

        # Retry if attempts remaining
        if self.request.retries < self.max_retries:
            logger.warning(
                f"Finalize failed, retrying: email_uuid={email_uuid}, "
                f"retry={self.request.retries + 1}/{self.max_retries + 1}, error={str(e)}"
            )
            raise self.retry(exc=e)

        # Final failure - retries exhausted
        logger.error(
            f"Finalize failed after all retries: email_uuid={email_uuid}, "
            f"retries={self.request.retries}/{self.max_retries}"
        )
        return handle_task_failure(
            organization_schema=organization_schema,
            email_uuid=email_uuid,
            error=e,
            failure_type="Email Finalization",
        )
