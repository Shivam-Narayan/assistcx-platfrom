# Custom libraries
import logging

# Database modules
from models.notification import Notification
from schemas.notification_schema import NotificationUpdate

# Default libraries
from typing import Optional, Dict, List, Union
from uuid import UUID
from datetime import datetime

# Installed libraries
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, asc, text
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_notification(self, notification_data: dict) -> Optional[Notification]:
        """Create a new notification from dict input."""
        new_notification = Notification(**notification_data)
        try:
            self.db.add(new_notification)
            self.db.commit()
            self.db.refresh(new_notification)
            return new_notification
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error during create_notification: {e}")
            return None

    def update_notification(
        self, notification_id: UUID, update_data: dict
    ) -> Optional[Notification]:
        """Update an existing notification by notification_id using dict data."""
        try:
            notification = (
                self.db.query(Notification)
                .filter(Notification.id == notification_id)
                .first()
            )

            if not notification:
                return None

            # Update only fields provided in the dict
            for key, value in update_data.items():
                if hasattr(notification, key):
                    setattr(notification, key, value)

            self.db.commit()
            self.db.refresh(notification)

            return notification

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error during update_notification: {e}")
            return None

    def get_notification_by_id(self, notification_id: UUID) -> Optional[Notification]:
        """Retrieve a specific notification by ID for a recipient."""
        try:
            return (
                self.db.query(Notification)
                .filter(Notification.id == notification_id)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error during get_notification_by_id: {e}")
            return None

    def get_all_notifications(
        self,
        recipient_id: str,
        filters: Optional[Dict[str, any]] = None,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[Notification]:
        """Retrieve all notifications with pagination and optional filters."""
        try:
            query = self.db.query(Notification).filter(
                Notification.recipient_id == recipient_id
            )

            # Apply filters
            if filters:
                for key, value in filters.items():
                    if hasattr(Notification, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(Notification, key).in_(value))
                        else:
                            query = query.filter(getattr(Notification, key) == value)

            if hasattr(Notification, sort_by):
                order = (
                    asc(getattr(Notification, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(Notification, sort_by))
                )
                query = query.order_by(order)

            # Pagination
            return query.offset((page - 1) * page_size).limit(page_size).all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error during get_all_notifications: {e}")
            return []

    def search_notifications(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 10,
    ) -> List[Notification]:
        """Search notifications by keyword and filter."""
        try:
            query = self.db.query(Notification).filter()

            if keyword:
                pattern = f"%{keyword}%"
                query = query.filter(
                    or_(
                        Notification.title.ilike(pattern),
                        Notification.description.ilike(pattern),
                        Notification.notification_type.ilike(pattern),
                    )
                )

            if filters:
                for key, value in filters.items():
                    if hasattr(Notification, key):
                        if isinstance(value, list):
                            query = query.filter(getattr(Notification, key).in_(value))
                        else:
                            query = query.filter(getattr(Notification, key) == value)

            if hasattr(Notification, sort_by):
                column = getattr(Notification, sort_by)
                query = query.order_by(
                    asc(column) if sort_order == "asc" else desc(column)
                )

            notifications = query.offset((page - 1) * page_size).limit(page_size).all()

            return notifications
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error during search_notifications: {e}")
            return []

    def delete_notification(self, notification_id: UUID) -> bool:
        """Delete a notification."""
        try:
            notification = (
                self.db.query(Notification)
                .filter(Notification.id == notification_id)
                .first()
            )
            if not notification:
                return False

            self.db.delete(notification)
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error during delete_notification: {e}")
            return False

