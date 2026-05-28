# Custom libraries
from logger import configure_logging

# Database modules
from models.activity_log import ActivityLog
from repository.configuration_repository import ConfigurationRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, List, Dict
from uuid import UUID

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, asc, or_


logger = configure_logging(__name__)


class ActivityLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_activity_log(self, activity_log_data: Dict) -> Optional[ActivityLog]:
        """
        Create a new activity log from activity_log_data.
        """
        new_activity_log = ActivityLog(**activity_log_data)
        try:
            self.db.add(new_activity_log)
            self.db.commit()
            self.db.refresh(new_activity_log)
            return new_activity_log
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def bulk_create_activity_logs(self, activity_logs_data: List[Dict]) -> bool:
        """
        Bulk create multiple activity logs in a single transaction.
        This is optimized for batch operations to reduce database roundtrips.

        Args:
            activity_logs_data: List of dictionaries containing activity log data

        Returns:
            True if successful, False otherwise
        """
        if not activity_logs_data:
            logger.warning("No activity logs data provided for bulk creation")
            return True

        try:
            activity_log_objects = [
                ActivityLog(**log_data) for log_data in activity_logs_data
            ]
            self.db.bulk_save_objects(activity_log_objects)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error in bulk_create_activity_logs: {e}")
            return False

    def get_activity_log_by_id(self, identifier: UUID) -> Optional[ActivityLog]:
        """
        Retrieve an activity log based on its identifier.
        """
        try:
            return (
                self.db.query(ActivityLog).filter(ActivityLog.id == identifier).first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_activity_logs(
        self,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ActivityLog]:
        """
        Retrieve activity logs with optional filters and sorting.
        """
        try:
            query = self.db.query(ActivityLog)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ActivityLog, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ActivityLog, key).in_(value))
                        else:
                            query = query.filter(getattr(ActivityLog, key) == value)

            # Apply sorting
            if hasattr(ActivityLog, sort_by):
                order = (
                    asc(getattr(ActivityLog, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ActivityLog, sort_by))
                )
                query = query.order_by(order)

            return query.offset((page - 1) * page_size).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_activity_logs(
        self,
        keyword: str,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ActivityLog]:
        """
        Search activity logs with optional filters and sorting.
        """
        try:
            query = self.db.query(ActivityLog)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ActivityLog, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ActivityLog, key).in_(value))
                        else:
                            query = query.filter(getattr(ActivityLog, key) == value)

            # Apply keyword search
            if keyword:
                query = query.filter(
                    or_(
                        ActivityLog.note.ilike(f"%{keyword}%"),
                    )
                )

            # Apply sorting
            if hasattr(ActivityLog, sort_by):
                order = (
                    asc(getattr(ActivityLog, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ActivityLog, sort_by))
                )
                query = query.order_by(order)

            return query.offset((page - 1) * page_size).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_activity_logs_by_entity_id(
        self,
        entity_id: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ActivityLog]:
        """
        Retrieve activity logs for a specific entity with optional filters and sorting.
        """
        try:
            query = self.db.query(ActivityLog).filter(
                ActivityLog.entity_id == entity_id
            )

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ActivityLog, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ActivityLog, key).in_(value))
                        else:
                            query = query.filter(getattr(ActivityLog, key) == value)

            # Apply sorting
            if hasattr(ActivityLog, sort_by):
                order = (
                    asc(getattr(ActivityLog, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ActivityLog, sort_by))
                )
                query = query.order_by(order)

            activity_logs = query.all()

            config = ConfigurationRepository(self.db).get_configuration()
            prefs = (config.preferences or {}) if config else {}
            default_email = prefs.get("default_email")
            fallback_user_name = str(default_email).strip() if default_email else "External system"

            for activity_log in activity_logs:
                if activity_log.user_id:
                    user_id = (
                        activity_log.user_id
                        if isinstance(activity_log.user_id, UUID)
                        else UUID(activity_log.user_id)
                    )
                    user = UserRepository(self.db).get_user_by_id(user_id)
                    if user:
                        names = filter(None, [user.first_name, user.last_name])
                        activity_log.user_name = " ".join(names)
                else:
                    activity_log.user_name = fallback_user_name

            return activity_logs

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_activity_logs_by_user_id(
        self,
        user_id: str,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ActivityLog]:
        """
        Retrieve activity logs for a specific user with optional filters and sorting.
        """
        try:
            query = self.db.query(ActivityLog).filter(ActivityLog.user_id == user_id)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ActivityLog, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ActivityLog, key).in_(value))
                        else:
                            query = query.filter(getattr(ActivityLog, key) == value)

            # Apply sorting
            if hasattr(ActivityLog, sort_by):
                order = (
                    asc(getattr(ActivityLog, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ActivityLog, sort_by))
                )
                query = query.order_by(order)

            return query.offset((page - 1) * page_size).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_activity_logs_by_user_id(
        self,
        user_id: str,
        keyword: str,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "updated_at",
        sort_order: Optional[str] = "desc",
    ) -> List[ActivityLog]:
        """
        Search activity logs for a specific user with optional filters and sorting.
        """
        try:
            query = self.db.query(ActivityLog).filter(ActivityLog.user_id == user_id)

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(ActivityLog, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(ActivityLog, key).in_(value))
                        else:
                            query = query.filter(getattr(ActivityLog, key) == value)

            # Apply keyword search
            if keyword:
                query = query.filter(
                    or_(
                        ActivityLog.note.ilike(f"%{keyword}%"),
                    )
                )

            # Apply sorting
            if hasattr(ActivityLog, sort_by):
                order = (
                    asc(getattr(ActivityLog, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(ActivityLog, sort_by))
                )
                query = query.order_by(order)

            return query.offset((page - 1) * page_size).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []
