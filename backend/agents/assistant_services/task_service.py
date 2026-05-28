# Custom libraries
from celery_worker import celery as celery_app
from logger import configure_logging

# Default libraries
from datetime import datetime
from typing import Literal, Union

# Installed libraries
from celery.schedules import crontab
from redbeat import RedBeatSchedulerEntry


logger = configure_logging(__name__)


class AssistantTaskService:
    """Service class for Assistant task operations"""
    
    def toggle_scheduler_entry(self, task_name: str, enabled: bool):
        """
        Enable or disable a RedBeat scheduler entry.

        Args:
            task_name: Name of the scheduled task
            enabled: True to enable, False to disable
        """
        try:
            # Get the scheduler entry by name with correct RedBeat key format
            redbeat_key = f"redbeat:{task_name}"
            entry = RedBeatSchedulerEntry.from_key(redbeat_key, app=celery_app)
            entry.enabled = enabled
            entry.save()
            logger.info(
                f"Scheduler entry '{task_name}' {'enabled' if enabled else 'disabled'}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to toggle scheduler entry '{task_name}': {e}")
            return False

    def detect_schedule_type(self, schedule: str) -> Literal["cron", "timestamp"]:
        """Detect if schedule is cron expression or Unix timestamp"""
        schedule = schedule.strip()
        
        # Unix timestamp: numeric string (10 digits for seconds, 13 for milliseconds)
        if schedule.isdigit() and len(schedule) in [10, 13]:
            return "timestamp"
        # Cron: space-separated (5 parts)
        elif len(schedule.split()) == 5:
            return "cron"
        else:
            raise ValueError("Invalid schedule format. Must be cron expression (5 parts) or Unix timestamp (10-13 digits)")

    def parse_schedule(self, schedule: str) -> Union[crontab, datetime]:
        """Parse schedule string (cron or timestamp) and return appropriate schedule object"""
        schedule_type = self.detect_schedule_type(schedule)
        
        if schedule_type == "cron":
            return self.parse_cron_expression(schedule)
        elif schedule_type == "timestamp":
            return self.parse_timestamp_schedule(schedule)

    def parse_timestamp_schedule(self, timestamp_str: str) -> datetime:
        """Convert Unix timestamp to datetime for eta-based execution"""
        try:
            timestamp = int(timestamp_str)
            
            # Handle both seconds and milliseconds
            if len(timestamp_str) == 13:  # milliseconds
                timestamp = timestamp / 1000
            
            target_datetime = datetime.fromtimestamp(timestamp)
            current_time = datetime.now()
            
            if target_datetime <= current_time:
                raise ValueError("Timestamp must be in the future")
            
            return target_datetime
            
        except (ValueError, OSError) as e:
            raise ValueError(f"Invalid timestamp: {e}")

    def parse_cron_expression(self, cron_expr: str):
        """
        Parse cron expression and return celery crontab object.
        Format: minute hour day month day_of_week
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "Cron expression must have exactly 5 parts: minute hour day month day_of_week"
            )

        minute, hour, day, month, day_of_week = parts

        # Convert '*' to '*' (keep as string) for celery crontab
        def convert_field(field):
            if field == "*":
                return "*"
            return field

        return crontab(
            minute=convert_field(minute),
            hour=convert_field(hour),
            day_of_month=convert_field(day),
            month_of_year=convert_field(month),
            day_of_week=convert_field(day_of_week),
        )