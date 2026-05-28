# Custom libraries
from models.class_group import ClassGroup
from logger import configure_logging

# Default libraries
from datetime import datetime
from typing import Optional, List, Dict, Union
from uuid import UUID

# Installed libraries
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import desc, asc, or_
from fastapi import HTTPException
logger = configure_logging(__name__)


class ClassGroupRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_class_group(self, class_group_data: Dict) -> Optional[ClassGroup]:
        """Creates a new class group."""
        class_group = ClassGroup(**class_group_data)
        try:
            self.db.add(class_group)
            self.db.commit()
            self.db.refresh(class_group)
            return class_group
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Class Group with same key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating ClassGroup: {e}")
            return None

    def update_class_group_by_id(self, update_data: Dict) -> Optional[ClassGroup]:
        """Updates a class group by UUID."""
        identifier = update_data.get("class_group_uuid")
        class_group = self.db.query(ClassGroup).filter(ClassGroup.id == identifier).first()
        if not class_group:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(class_group, key):
                    setattr(class_group, key, value)
            self.db.commit()
            self.db.refresh(class_group)
            return class_group
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Class Group with same key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error updating Class Group: {e}")
            return None

    def get_class_group_by_id(self, identifier: Union[UUID, str]) -> Optional[ClassGroup]:
        """Get a class group using UUID"""
        try:
            if isinstance(identifier, UUID):
                query_filter = ClassGroup.id == identifier
            elif isinstance(identifier, str):
                query_filter = ClassGroup.key == identifier
            else:
                raise ValueError("Identifier must be a UUID or a key string")

            return self.db.query(ClassGroup).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching Class Group by identifier {identifier}: {e}")
            return None

    def get_all_class_groups(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[ClassGroup]:
        """Fetches all class groups with pagination, filters, and sorting."""
        query = self.db.query(ClassGroup)

        if filters:
            for key, value in filters.items():
                if hasattr(ClassGroup, key):
                    query = query.filter(getattr(ClassGroup, key) == value)

        if hasattr(ClassGroup, sort_by):
            order = (
                asc(getattr(ClassGroup, sort_by))
                if sort_order.lower() == "asc"
                else desc(getattr(ClassGroup, sort_by))
            )
            query = query.order_by(order)

        try:
            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                class_groups = query.offset(skip).limit(page_size).all()
            else:
                class_groups = query.all()
            return class_groups
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching class groups: {e}")
            return []

    def search_class_groups(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Union[str, List[str]]]] = None,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[ClassGroup]:
        """Searches class groups by keyword and filters with pagination and sorting."""
        skip = (page - 1) * page_size
        keyword = f"%{keyword}%" if keyword else None
        query = self.db.query(ClassGroup)
    
        if filters:
            for key, value in filters.items():
                if hasattr(ClassGroup, key):
                    if isinstance(value, list):
                        query = query.filter(getattr(ClassGroup, key).in_(value))
                    else:
                        query = query.filter(getattr(ClassGroup, key) == value)

        if keyword:
            query = query.filter(
                or_(
                    ClassGroup.name.ilike(keyword),
                    ClassGroup.key.ilike(keyword),
                    ClassGroup.description.ilike(keyword),
                )
            )

        if hasattr(ClassGroup, sort_by):
            order = (
                asc(getattr(ClassGroup, sort_by))
                if sort_order.lower() == "asc"
                else desc(getattr(ClassGroup, sort_by))
            )
            query = query.order_by(order)

        try:
            return query.offset(skip).limit(page_size).all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error during class group search: {e}")
            return []
 
    def delete_class_group(self, identifier: Union[UUID, str]) -> bool:
        """Deletes a class group using UUID ."""
        try:
            if isinstance(identifier, UUID):
                query_filter = ClassGroup.id == identifier
            elif isinstance(identifier, str):
                query_filter = ClassGroup.key == identifier
            else:
                raise ValueError("Identifier must be a UUID or a key string")

            class_group = self.db.query(ClassGroup).filter(query_filter).first()

            if not class_group:
                return False

            self.db.delete(class_group)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error deleting Class Group with identifier {identifier}: {e}")
            return False