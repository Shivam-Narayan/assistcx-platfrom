# Custom libraries
from logger import configure_logging

# Database modules
from models.agent_task import AgentTask
from models.email import Email
from models.issue import Issue
from models.tag import Tag

# Default libraries
from typing import Optional, List, Dict, Union
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import desc, asc, or_


logger = configure_logging(__name__)


class TagRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_tag(self, tag_data: Dict) -> Optional[Tag]:
        tag = Tag(**tag_data)
        try:
            self.db.add(tag)
            self.db.commit()
            self.db.refresh(tag)
            return tag
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Tag with same name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_tag_by_id(self, update_data: Dict) -> Optional[Tag]:
        identifier = update_data.get("tag_uuid")
        tag = self.db.query(Tag).filter(Tag.id == identifier).first()
        if not tag:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(tag, key):
                    setattr(tag, key, value)
            self.db.commit()
            self.db.refresh(tag)
            return tag
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f" SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Tag with same name already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_tag_by_id(self, identifier: Union[UUID, str]) -> Optional[Tag]:
        try:
            if isinstance(identifier, UUID):
                query_filter = Tag.id == identifier
            elif isinstance(identifier, str):
                query_filter = Tag.name == identifier
            else:
                raise ValueError("Identifier must be a UUID or a name string")

            return self.db.query(Tag).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_tags_by_ids(self, tag_ids: List[str]) -> List[Tag]:
        """
        Batch fetch multiple tags by their IDs.

        OPTIMIZED: Single query with IN clause instead of N separate queries.
        Used by get_all_emails() to eliminate N+1 query problem.

        Args:
            tag_ids: List of tag ID strings (UUIDs)

        Returns:
            List of Tag objects
        """
        if not tag_ids:
            return []

        try:
            # Convert string IDs to UUIDs
            uuid_ids = [UUID(tid) for tid in tag_ids if tid]

            # Single query with IN clause
            tags = (
                self.db.query(Tag)
                .filter(Tag.id.in_(uuid_ids))
                .all()
            )

            return tags

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching tags by IDs: {e}")
            return []
        except ValueError as e:
            logger.error(f"Invalid UUID in tag_ids: {e}")
            return []

    def get_all_tags(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, Union[str, List[str], UUID]]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[Tag]:
        query = self.db.query(Tag)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Tag, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(Tag, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Tag, key) == values)

        # Apply sorting
        if hasattr(Tag, sort_by):
            order = (
                asc(getattr(Tag, sort_by))
                if sort_order.lower() == "asc"
                else desc(getattr(Tag, sort_by))
            )
            query = query.order_by(order)

        try:
            # Apply pagination only if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                return query.offset(skip).limit(page_size).all()
            else:
                return query.all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_tags(
        self,
        keyword: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, Union[str, List[str]]]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[Tag]:
        query = self.db.query(Tag)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Tag, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(Tag, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Tag, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    Tag.name.ilike(f"%{keyword}%"),
                    Tag.description.ilike(f"%{keyword}"),
                )
            )

        # Apply sorting
        if hasattr(Tag, sort_by):
            order = (
                asc(getattr(Tag, sort_by))
                if sort_order == "asc"
                else desc(getattr(Tag, sort_by))
            )
            query = query.order_by(order)

        try:
            # Apply pagination only if both are provided
            if page and page_size:
                skip = (page - 1) * page_size
                return query.offset(skip).limit(page_size).all()
            else:
                return query.all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def delete_tag_by_id(self, identifier: UUID) -> bool:
        """
        Deletes an existing tag based on its UUID.
        """
        tag = self.db.query(Tag).filter(Tag.id == identifier).first()
        if not tag:
            return False

        try:
            deleted_tag_id = str(identifier)

            # Remove deleted tag id from all emails that reference it
            emails_with_tag = (
                self.db.query(Email)
                .filter(Email.tag_ids.contains([deleted_tag_id]))
                .all()
            )
            for email in emails_with_tag:
                if email.tag_ids and deleted_tag_id in email.tag_ids:
                    email.tag_ids = [
                        tag_id
                        for tag_id in email.tag_ids
                        if tag_id != deleted_tag_id
                    ]

            # Remove deleted tag id from all agent_tasks that reference it
            agent_tasks_with_tag = (
                self.db.query(AgentTask)
                .filter(AgentTask.tag_ids.contains([deleted_tag_id]))
                .all()
            )
            for agent_task in agent_tasks_with_tag:
                if agent_task.tag_ids and deleted_tag_id in agent_task.tag_ids:
                    agent_task.tag_ids = [
                        tag_id
                        for tag_id in agent_task.tag_ids
                        if tag_id != deleted_tag_id
                    ]

            # Remove deleted tag id from all issues that reference it
            issues_with_tag = (
                self.db.query(Issue)
                .filter(Issue.tag_ids.contains([deleted_tag_id]))
                .all()
            )
            for issue in issues_with_tag:
                if issue.tag_ids and deleted_tag_id in issue.tag_ids:
                    issue.tag_ids = [
                        tag_id
                        for tag_id in issue.tag_ids
                        if tag_id != deleted_tag_id
                    ]

            self.db.delete(tag)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return False
