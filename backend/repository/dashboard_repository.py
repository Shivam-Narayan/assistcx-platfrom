# Custom libraries
from logger import configure_logging

# Database modules
from models.email import Email
from models.agent_task import AgentTask
from models.agent import Agent

# Default libraries
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import calendar
from uuid import UUID


# Installed libraries
from sqlalchemy import and_, func, text, case, cast, Float
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import pytz


logger = configure_logging(__name__)


class DashboardRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_task_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """
        OPTIMIZED VERSION: Aggregates task statistics with a single comprehensive query.
        Eliminates multiple query round trips by combining all aggregations and calculations

        Example improvement:
        Before: 1 (main stats) + 1 (archived count) + 1 (time saved subquery) + 1 (time saved sum) = 4 queries
        After: 1 (combined aggregation) + 1 (email count) = 2 queries
        """
        try:
            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            # Build base query with all aggregations including archived in a single query
            query = self.db.query(
                func.count(AgentTask.id).label("total_tasks"),
                func.count(func.distinct(Agent.id)).label("unique_agents"),
                func.sum(
                    case(
                        (text("progress -> -1 ->> 'status' = 'SUCCESSFUL'"), 1), else_=0
                    )
                ).label("successful_count"),
                func.sum(
                    case((text("progress -> -1 ->> 'status' = 'RESOLVED'"), 1), else_=0)
                ).label("resolved_count"),
                func.sum(
                    case(
                        (text("progress -> -1 ->> 'status' = 'EXECUTING'"), 1), else_=0
                    )
                ).label("executing_count"),
                func.sum(
                    case(
                        (text("progress -> -1 ->> 'status' = 'INCOMPLETE'"), 1), else_=0
                    )
                ).label("incomplete_count"),
                func.sum(
                    case((text("progress -> -1 ->> 'status' = 'FAILED'"), 1), else_=0)
                ).label("failed_count"),
                func.sum(
                    case((text("progress -> -1 ->> 'status' = 'QUEUED'"), 1), else_=0)
                ).label("queued_count"),
                func.sum(
                    case((text("progress -> -1 ->> 'status' = 'ARCHIVED'"), 1), else_=0)
                ).label("archived_count"),
                # Calculate time saved in the same query
                func.sum(
                    case(
                        (
                            text("progress -> -1 ->> 'status' != 'ARCHIVED'"),
                            func.coalesce(
                                func.cast(
                                    Agent.agent_config["average_time_per_task"].astext,
                                    Float,
                                ),
                                0.0,
                            ),
                        ),
                        else_=0,
                    )
                ).label("time_saved"),
            ).join(Agent, Agent.id == AgentTask.agent_id)

            # Apply date filters
            if from_date and to_date:
                query = query.filter(
                    AgentTask.created_at >= from_date,
                    AgentTask.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                query = query.filter(AgentTask.created_at >= thirty_days_ago)

            # Apply filters
            if filters:
                for key, values in filters.items():
                    if hasattr(AgentTask, key):
                        if isinstance(values, list):
                            query = query.filter(getattr(AgentTask, key).in_(values))
                        else:
                            query = query.filter(getattr(AgentTask, key) == values)

            # Execute the single aggregation query
            result = query.first()

            # Calculate success rate
            total_tasks = (
                (result.total_tasks or 0)
                - (result.archived_count or 0)
                - (result.resolved_count or 0)
            )
            successful_tasks = result.successful_count or 0
            success_rate = (
                round((successful_tasks / total_tasks * 100), 2) if total_tasks else 0.0
            )

            # Extract agent_ids from filters if provided
            filter_agent_ids = None
            if filters and "agent_id" in filters:
                agent_id_values = filters["agent_id"]
                filter_agent_ids = (
                    agent_id_values
                    if isinstance(agent_id_values, list)
                    else [agent_id_values]
                )

            # Build result
            task_counts = {
                "email_count": self.get_email_count(
                    from_date, to_date, agent_ids=filter_agent_ids
                ),
                "task_count": total_tasks,
                "successful_count": successful_tasks,
                "resolved_count": result.resolved_count or 0,
                "executing_count": result.executing_count or 0,
                "incomplete_count": result.incomplete_count or 0,
                "failed_count": result.failed_count or 0,
                "queued_count": result.queued_count or 0,
                "archived_count": result.archived_count or 0,
                "success_rate": success_rate,
                "time_saved": result.time_saved or 0.0,
            }

            return task_counts

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {}

    def get_task_volume_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_timezone: str = "UTC",
    ) -> List[Dict]:
        """
        OPTIMIZED VERSION: Aggregates task volume statistics with efficient date truncation.
        Formats dates in user's timezone for proper display.

        CRITICAL: The date_trunc must be performed in the user's timezone to correctly
        aggregate tasks by the user's local day/week/month, not the database server's timezone.

        Args:
            from_date: Start date (should be UTC-aware)
            to_date: End date (should be UTC-aware)
            filters: Optional filters
            user_timezone: User's timezone identifier (e.g., 'America/New_York', 'Asia/Kolkata')
        """
        try:
            # Validate and get user's timezone
            try:
                user_tz = pytz.timezone(user_timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone: {user_timezone}, defaulting to UTC")
                user_timezone = "UTC"
                user_tz = pytz.UTC

            # Determine date range
            if not from_date or not to_date:
                if not to_date:
                    to_date = datetime.now(pytz.UTC)
                if not from_date:
                    from_date = to_date - timedelta(days=30)

            range_days = (to_date - from_date).days

            # Decide granularity based on range
            if range_days <= 30:
                truncate_unit = "day"
            elif range_days <= 90:
                truncate_unit = "week"
            else:
                truncate_unit = "month"

            # CRITICAL FIX: Perform date_trunc in user's timezone, not database timezone.
            # This ensures tasks are grouped by the user's local day, not UTC day.
            # The expression: date_trunc('day', created_at AT TIME ZONE 'UTC' AT TIME ZONE 'user_tz')
            # 1. First treats created_at as UTC (AT TIME ZONE 'UTC' converts to timestamptz)
            # 2. Then converts to user's timezone (AT TIME ZONE 'user_tz')
            # 3. Finally truncates in the user's local timezone
            period_expr = func.date_trunc(
                truncate_unit,
                text(f"created_at AT TIME ZONE 'UTC' AT TIME ZONE '{user_timezone}'"),
            ).label("period")

            # Build optimized query for agent tasks
            query = self.db.query(
                period_expr,
                func.count().label("count"),
            ).filter(
                text("progress -> -1 ->> 'status' != 'ARCHIVED'"),
                AgentTask.created_at >= from_date,
                AgentTask.created_at <= (to_date + timedelta(seconds=1)),
            )

            # Apply filters
            if filters:
                for key, values in filters.items():
                    if hasattr(AgentTask, key):
                        if isinstance(values, list):
                            query = query.filter(getattr(AgentTask, key).in_(values))
                        else:
                            query = query.filter(getattr(AgentTask, key) == values)

            # Group and order
            query = query.group_by("period").order_by("period")

            result = query.all()

            # Format results - period is now already in user's timezone (naive datetime)
            stats = []
            for row in result:
                # The period is now a naive datetime in user's local timezone
                local_period = row.period

                if truncate_unit == "day":
                    label = local_period.strftime("%d-%b-%Y")
                elif truncate_unit == "week":
                    start_of_week = local_period
                    # Calculate end of week, but don't exceed the to_date
                    to_date_local = (
                        to_date.astimezone(user_tz)
                        if to_date.tzinfo
                        else pytz.UTC.localize(to_date).astimezone(user_tz)
                    )
                    end_of_week = min(
                        start_of_week + timedelta(days=6),
                        to_date_local.replace(tzinfo=None),
                    )
                    label = f"{start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d, %Y')}"
                else:  # month
                    label = local_period.strftime("%b %Y")

                stats.append({"time_period": label, "count": row.count})

            return stats

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_task_agent_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict]]:
        """
        OPTIMIZED VERSION: Aggregates agent statistics with efficient query structure.
        Eliminates redundant calculations and streamlines data transformation.

        Example improvement:
        Before: Complex CASE statement + multiple post-query calculations + temporary field cleanup
        After: Simplified aggregations + cleaner data flow + no temporary field overhead
        """
        try:
            # Determine date range once at the start
            if from_date and to_date:
                date_filter = and_(
                    AgentTask.created_at >= from_date,
                    AgentTask.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                # Default: last 30 days using Python datetime
                thirty_days_ago = func.now() - text("INTERVAL '30 days'")
                date_filter = AgentTask.created_at >= thirty_days_ago

            # Query agent task counts with average execution time
            query = (
                self.db.query(
                    Agent.id.label("agent_id"),
                    Agent.name.label("agent_name"),
                    func.count(AgentTask.id).label("total_count"),
                    func.sum(
                        case(
                            (
                                AgentTask.progress[-1]["status"].astext == "SUCCESSFUL",
                                1,
                            ),
                            else_=0,
                        )
                    ).label("successful_count"),
                    func.avg(
                        cast(AgentTask.additional_data["execution_time"].astext, Float)
                    ).label("avg_time"),
                )
                .join(AgentTask, Agent.id == AgentTask.agent_id)
                .filter(
                    AgentTask.progress[-1]["status"].astext != "ARCHIVED",
                    AgentTask.progress[-1]["status"].astext != "RESOLVED",
                    date_filter,
                )
            )

            # Apply filters
            if filters:
                for key, values in filters.items():
                    if hasattr(AgentTask, key):
                        if isinstance(values, list):
                            query = query.filter(getattr(AgentTask, key).in_(values))
                        else:
                            query = query.filter(getattr(AgentTask, key) == values)

            query = (
                query.group_by(Agent.id, Agent.name)
                .having(func.count(AgentTask.id) > 0)
                .order_by(func.count(AgentTask.id).desc())
            )

            result = query.all()

            # Check if aggregation is needed for "Others"
            needs_aggregation = (not filters or "name" not in filters) and len(
                result
            ) > 5

            # Transform results
            stats = []
            others_data = {"count": 0, "successful": 0, "total_time": 0.0}

            for idx, row in enumerate(result):
                success_rate = (
                    round((row.successful_count / row.total_count * 100), 2)
                    if row.total_count
                    else 0.0
                )
                avg_time = round(row.avg_time, 2) if row.avg_time else 0.0

                # Top 5 agents
                if not needs_aggregation or idx < 5:
                    stats.append(
                        {
                            "agent_name": row.agent_name,
                            "count": row.total_count,
                            "success_rate": success_rate,
                            "average_time": avg_time,
                        }
                    )
                else:
                    # Aggregate remaining agents
                    others_data["count"] += row.total_count
                    others_data["successful"] += row.successful_count
                    others_data["total_time"] += avg_time * row.total_count

            # Add "Others" entry if applicable
            if needs_aggregation and others_data["count"] > 0:
                others_avg_time = round(
                    others_data["total_time"] / others_data["count"], 2
                )
                others_success_rate = round(
                    (others_data["successful"] / others_data["count"] * 100), 2
                )

                stats.append(
                    {
                        "agent_name": "Others",
                        "count": others_data["count"],
                        "success_rate": others_success_rate,
                        "average_time": others_avg_time,
                    }
                )

            return stats

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_email_count(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        agent_ids: Optional[List[UUID]] = None,
    ) -> Optional[int]:
        try:
            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            # When agent_ids filter is provided, count emails that have tasks with those agents
            if agent_ids:
                # Count distinct emails that have agent tasks matching the criteria
                query = (
                    self.db.query(func.count(func.distinct(Email.id)))
                    .join(AgentTask, AgentTask.email_data_id == Email.id)
                    .filter(
                        Email.status != "ARCHIVED",
                        AgentTask.agent_id.in_(agent_ids),
                        text("progress -> -1 ->> 'status' != 'ARCHIVED'"),
                    )
                )

                # Apply date filters on AgentTask.created_at (to match task query logic)
                if from_date and to_date:
                    query = query.filter(
                        AgentTask.created_at >= from_date,
                        AgentTask.created_at <= (to_date + timedelta(seconds=1)),
                    )
                else:
                    query = query.filter(AgentTask.created_at >= thirty_days_ago)

            else:
                # No agent filter: count all emails by Email.created_at
                query = self.db.query(func.count(Email.id)).filter(
                    Email.status != "ARCHIVED"
                )

                # Apply date filters on Email.created_at
                if from_date and to_date:
                    query = query.filter(
                        Email.created_at >= from_date,
                        Email.created_at <= (to_date + timedelta(seconds=1)),
                    )
                else:
                    query = query.filter(Email.created_at >= thirty_days_ago)

            return query.scalar()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return 0

    def get_email_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, int]:
        try:
            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            # Define status and fields to get counts categorized by each status
            status = [
                "SUCCESSFUL",
                "EXECUTING",
                "INCOMPLETE",
                "FAILED",
                "QUEUED",
                "ARCHIVED",
            ]
            fields = [
                "successful_count",
                "executing_count",
                "incomplete_count",
                "failed_count",
                "queued_count",
                "archived_count",
            ]

            email_counts = {}

            # Loop through each status to get email counts categorized by status
            for index, current_status in enumerate(status):
                query = self.db.query(func.count(Email.id)).filter(
                    Email.status == current_status
                )

                # Apply date filters based on provided from_date and to_date
                if from_date and to_date:
                    query = query.filter(
                        Email.created_at >= from_date,
                        Email.created_at <= (to_date + timedelta(seconds=1)),
                    )
                else:
                    # Apply 30-days filter if no from_date and to_date are provided
                    query = query.filter(Email.created_at >= thirty_days_ago)

                email_counts[fields[index]] = query.scalar()

            # Include the total email count
            email_counts["email_count"] = self.get_email_count(from_date, to_date)

            return email_counts

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {}

    def get_email_monthly_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        user_timezone: str = "UTC",
    ) -> Optional[Dict]:
        """
        Retrieves email statistics grouped by month and year.
        Args:
            from_date: Start date (should be UTC-aware)
            to_date: End date (should be UTC-aware)
            user_timezone: User's timezone identifier (e.g., 'America/Los_Angeles')
        """
        try:
            # Validate timezone
            try:
                pytz.timezone(user_timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone: {user_timezone}, defaulting to UTC")
                user_timezone = "UTC"

            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            local_created_at = text(
                f"created_at AT TIME ZONE 'UTC' AT TIME ZONE '{user_timezone}'"
            )

            # Base query to get email statistics by month and year in user's timezone
            query = self.db.query(
                func.extract("month", local_created_at).label("month"),
                func.extract("year", local_created_at).label("year"),
                func.count().label("count"),
            ).filter(Email.status != "ARCHIVED")

            # Apply date filters based on provided from_date and to_date
            if from_date and to_date:
                query = query.filter(
                    Email.created_at >= from_date,
                    Email.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                # Apply 30-days filter if no from_date and to_date are provided
                query = query.filter(Email.created_at >= thirty_days_ago)

            # Group by month and year in user's timezone and execute the query
            result = (
                query.group_by(
                    func.extract("month", local_created_at),
                    func.extract("year", local_created_at),
                )
                .order_by(
                    func.extract("year", local_created_at),
                    func.extract("month", local_created_at),
                )
                .all()
            )

            # Convert the result to a list of dictionaries
            return [
                {
                    "month": calendar.month_abbr[int(month)],
                    "year": int(year),
                    "count": count,
                }
                for month, year, count in result
            ]

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_count_by_mailbox(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Optional[Dict]:
        try:
            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            # Base query to get counts by mailbox email
            query = self.db.query(
                Email.mailbox_email,
                func.count().label("count"),
            ).filter(Email.status != "ARCHIVED")

            # Apply date filters based on provided from_date and to_date
            if from_date and to_date:
                query = query.filter(
                    Email.created_at >= from_date,
                    Email.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                # Apply 30-days filter if no from_date and to_date are provided
                query = query.filter(Email.created_at >= thirty_days_ago)

            # Group by mailbox_email and execute the query
            result = query.group_by(Email.mailbox_email).all()

            # Convert the result to a list of dictionaries
            return [
                {"mailbox_email": mailbox_email, "count": count}
                for mailbox_email, count in result
            ]
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_task_count(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Optional[int]:
        try:
            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            # Base query to get the count of agent tasks
            query = self.db.query(func.count(AgentTask.id))

            # Apply date filters based on provided from_date and to_date
            if from_date and to_date:
                query = query.filter(
                    AgentTask.created_at >= from_date,
                    AgentTask.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                # Apply 30-days filter if no from_date and to_date are provided
                query = query.filter(AgentTask.created_at >= thirty_days_ago)

            # Exclude tasks whose last progress status is "ARCHIVED"
            query = query.filter(text("progress -> -1 ->> 'status' != 'ARCHIVED'"))

            # Execute the query and return the count
            return query.scalar()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return 0

    def get_task_monthly_stats(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        user_timezone: str = "UTC",
    ) -> Optional[List[Dict]]:
        """
        Retrieves task statistics grouped by month and year.

        Args:
            from_date: Start date (should be UTC-aware)
            to_date: End date (should be UTC-aware)
            user_timezone: User's timezone identifier (e.g., 'America/Los_Angeles')
        """
        try:
            # Validate timezone
            try:
                pytz.timezone(user_timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone: {user_timezone}, defaulting to UTC")
                user_timezone = "UTC"

            # Calculate the date 30 days ago
            thirty_days_ago = func.now() - text("INTERVAL '30 days'")

            local_created_at = text(
                f"created_at AT TIME ZONE 'UTC' AT TIME ZONE '{user_timezone}'"
            )

            # Base query with timezone-aware month/year extraction
            query = self.db.query(
                func.extract("month", local_created_at).label("month"),
                func.extract("year", local_created_at).label("year"),
                func.count().label("count"),
            )

            # Apply date filters based on provided from_date and to_date
            if from_date and to_date:
                query = query.filter(
                    AgentTask.created_at >= from_date,
                    AgentTask.created_at <= (to_date + timedelta(seconds=1)),
                )
            else:
                # Apply 30-days filter if no from_date and to_date are provided
                query = query.filter(AgentTask.created_at >= thirty_days_ago)

            # Exclude tasks whose last progress status is "ARCHIVED"
            query = query.filter(text("progress -> -1 ->> 'status' != 'ARCHIVED'"))

            # Grouping and ordering in user's timezone
            result = (
                query.group_by(
                    func.extract("month", local_created_at),
                    func.extract("year", local_created_at),
                )
                .order_by(
                    func.extract("year", local_created_at),
                    func.extract("month", local_created_at),
                )
                .all()
            )

            return [
                {
                    "month": calendar.month_abbr[int(month)],
                    "year": int(year),
                    "count": count,
                }
                for month, year, count in result
            ]

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []
