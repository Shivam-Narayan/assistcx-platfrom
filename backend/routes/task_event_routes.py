# Custom libraries
from logger import configure_logging
from utils.schema_utils import get_schema_db

# Database modules
from repository.task_event_repository import TaskEventRepository
from sqlalchemy.orm import Session

# Default libraries
from uuid import UUID

# installed libraries
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session


logger = configure_logging(__name__)

task_event_router = APIRouter(tags=["Task Events"])


@task_event_router.get("/task-events/{email_uuid}")
def get_task_event(
    email_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves task event information for a specific email.
    """
    try:
        task_event_repository = TaskEventRepository(db)

        # Fetch all task progress for an email
        task_event = task_event_repository.get_task_events_by_email(
            email_uuid=email_uuid
        )

        return task_event

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
