# Custom libraries
from logger import configure_logging
from schemas.dashboard_schema import (
    EmailCounts,
    EmailMonthlyStats,
    AgentTaskStats,
    EmailMailboxStats,
    TaskCounts,
    TaskMonthlyStats,
    TaskVolumeStats,
)
from utils.schema_utils import get_schema_db

# Database modules
from repository.dashboard_repository import DashboardRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime, timezone
from typing import List, Optional


# Installed libraries
from fastapi import APIRouter, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

dashboard_router = APIRouter(tags=["Dashboards"])


@dashboard_router.get("/task-counts", response_model=TaskCounts)
def get_task_counts(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves the total count of emails and agent tasks along with agent task counts categorized by status(SUCCESSFUL, EXECUTING, FAILED).
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date.Please check and retry.",
            )

        dashboard_repository = DashboardRepository(db)
        filters = request.state.filters

        return dashboard_repository.get_task_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            filters=filters,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/task-volume-stats", response_model=List[TaskVolumeStats])
def get_task_volume_stats(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    user_timezone: Optional[str] = Query(
        "UTC", description="User's timezone (e.g., 'America/New_York', 'Asia/Kolkata')"
    ),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves task counts aggregated by day, week, or month based on the selected date range.
    Accepts timezone parameter to format dates in user's local timezone.
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date.Please check and retry.",
            )

        dashboard_repository = DashboardRepository(db)
        filters = request.state.filters

        return dashboard_repository.get_task_volume_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            filters=filters,
            user_timezone=user_timezone,
        )
    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/task-agent-stats", response_model=List[AgentTaskStats])
def get_agent_stats(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves agent task statistics including total count, success rate, and average execution time per agent.
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date.Please check and retry.",
            )

        dashboard_repository = DashboardRepository(db)
        filters = request.state.filters

        return dashboard_repository.get_task_agent_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            filters=filters,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/email-counts", response_model=EmailCounts)
def get_email_counts(
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves the total count of emails along with counts categorized by status(SUCCESSFUL, EXECUTING, FAILED).
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date. Please check and retry.",
            )
        dashboard_repository = DashboardRepository(db)

        return dashboard_repository.get_email_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/email-monthly-stats", response_model=List[EmailMonthlyStats])
def get_email_monthly_stats(
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    user_timezone: Optional[str] = Query(
        "UTC", description="User's timezone (e.g., 'America/New_York', 'Asia/Kolkata')"
    ),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves the total count of emails for each month for the last one year.
    Accepts timezone parameter to group emails by user's local month.
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date. Please check and retry.",
            )
        dashboard_repository = DashboardRepository(db)

        return dashboard_repository.get_email_monthly_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            user_timezone=user_timezone,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/count-by-mailbox", response_model=List[EmailMailboxStats])
def get_count_by_mailbox(
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves the total count of emails categorized by mailbox_email.
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date. Please check and retry.",
            )
        dashboard_repository = DashboardRepository(db)

        return dashboard_repository.get_count_by_mailbox(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@dashboard_router.get("/task-monthly-stats", response_model=List[TaskMonthlyStats])
def get_task_monthly_stats(
    from_date: Optional[float] = Query(
        None, description="Start date as Unix timestamp"
    ),
    to_date: Optional[float] = Query(None, description="End date as Unix timestamp"),
    user_timezone: Optional[str] = Query(
        "UTC", description="User's timezone (e.g., 'America/New_York', 'Asia/Kolkata')"
    ),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves the total count of agent tasks for each month for the last one year.
    Accepts timezone parameter to group tasks by user's local month.
    """
    try:
        if (from_date and not to_date) or (to_date and not from_date):
            raise HTTPException(
                status_code=400,
                detail="Missing start/end date. Please check and retry.",
            )
        dashboard_repository = DashboardRepository(db)

        return dashboard_repository.get_task_monthly_stats(
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            user_timezone=user_timezone,
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
