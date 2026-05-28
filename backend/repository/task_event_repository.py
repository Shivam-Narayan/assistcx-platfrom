# Custom libraries
from logger import configure_logging

# Database modules
from models.task_event import TaskEvent

# Default libraries
from typing import Dict, List, Optional
from uuid import UUID

# Installed libraries
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class TaskEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_task_event(self, event_data: dict) -> Optional[TaskEvent]:
        new_event = TaskEvent(**event_data)
        try:
            self.db.add(new_event)
            self.db.commit()
            self.db.refresh(new_event)
            return new_event
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_task_event(
        self, event_uuid: UUID, update_data: dict
    ) -> Optional[TaskEvent]:
        event = self.db.query(TaskEvent).filter(TaskEvent.id == event_uuid).first()
        if not event:
            return None
        try:
            for key, value in update_data.items():
                setattr(event, key, value)
            self.db.commit()
            self.db.refresh(event)
            return event
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_task_event_by_id(self, event_uuid: UUID) -> Optional[TaskEvent]:
        try:
            return self.db.query(TaskEvent).filter(TaskEvent.id == event_uuid).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_task_event_by_email_and_key(
        self, email_uuid: UUID, key: str
    ) -> Optional[TaskEvent]:
        try:
            return (
                self.db.query(TaskEvent)
                .filter(TaskEvent.email_data_id == email_uuid, TaskEvent.key == key)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_task_events_by_email(
        self,
        email_uuid: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[TaskEvent]:
        query = self.db.query(TaskEvent)

        # Fetch data for specific email
        query = query.filter(TaskEvent.email_data_id == email_uuid)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(TaskEvent, key):
                    if key == "tag_ids":
                        # Use overlap for ARRAY-based filtering
                        query = query.filter(TaskEvent.tag_ids.overlap(values))
                    elif isinstance(values, list):
                        condition = or_(
                            *(getattr(TaskEvent, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(TaskEvent, key) == values)

        # Apply sorting
        if hasattr(TaskEvent, sort_by):
            order = (
                asc(getattr(TaskEvent, sort_by))
                if sort_order == "asc"
                else desc(getattr(TaskEvent, sort_by))
            )
            query = query.order_by(order)

        try:
            events = query.all()
            return [self.extract_event_type(event) for event in events]
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def extract_event_type(self, task_event: TaskEvent) -> dict:
        try:
            event_dict = task_event.__dict__.copy()

            # Extract event_type from additional_data
            additional_data = event_dict.get("additional_data")
            event_dict["event_type"] = (
                additional_data.get("event_type")
                if isinstance(additional_data, dict)
                else None
            )

            return event_dict

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return {}

    def get_all_task_events(
        self, page: int, page_size: int, filters: dict
    ) -> List[TaskEvent]:
        query = self.db.query(TaskEvent)
        for attr, value in filters.items():
            query = query.filter(getattr(TaskEvent, attr) == value)
        try:
            return (
                query.order_by(desc(TaskEvent.created_at))
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []
