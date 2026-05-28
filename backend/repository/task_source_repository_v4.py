# Custom libraries
from logger import configure_logging
from models.task_source_v4 import TaskSource

# Default libraries
from typing import Optional, Dict, List, Any
from uuid import UUID
from datetime import datetime

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import select, asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


# Schema imports
from schemas.task_source_schema_v4 import TaskSourceCreate


logger = configure_logging(__name__)


class TaskSourceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task_source(
        self, task_source_data: TaskSourceCreate
    ) -> Optional[TaskSource]:
        task_source = TaskSource(**task_source_data.model_dump())
        try:
            self.db.add(task_source)
            await self.db.commit()
            await self.db.refresh(task_source)
            return task_source
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating TaskSource: {e}")
            return None

    async def update_task_source(self, update_data: dict) -> Optional[TaskSource]:
        task_source_id = update_data.get("task_source_id")
        result = await self.db.execute(
            select(TaskSource).filter(
                TaskSource.id == task_source_id, TaskSource.deleted_at.is_(None)
            )
        )
        task_source = result.scalar_one_or_none()
        if not task_source:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(task_source, key):
                    setattr(task_source, key, value)
            await self.db.commit()
            await self.db.refresh(task_source)
            return task_source
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while updating TaskSource: {e}")
            return None

    async def get_task_source_by_id(self, task_source_id: UUID) -> Optional[TaskSource]:
        try:
            result = await self.db.execute(
                select(TaskSource).filter(
                    TaskSource.id == task_source_id, TaskSource.deleted_at.is_(None)
                )
            )
            task_source = result.scalar_one_or_none()
            return task_source
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching TaskSource: {e}")
            return None

    async def get_all_task_sources(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[TaskSource]:
        query = select(TaskSource).filter(TaskSource.deleted_at.is_(None))

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(TaskSource, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(TaskSource, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(TaskSource, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    TaskSource.name.ilike(f"%{keyword}%"),
                    TaskSource.provider_key.ilike(f"%{keyword}%"),
                    TaskSource.trigger_key.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(TaskSource, sort_by):
            order = (
                asc(getattr(TaskSource, sort_by))
                if sort_order == "asc"
                else desc(getattr(TaskSource, sort_by))
            )
            query = query.order_by(order)

        try:
            # Apply pagination if provided
            if page and page_size:
                skip = (page - 1) * page_size
                query = query.offset(skip).limit(page_size)

            result = await self.db.execute(query)
            task_sources = result.scalars().all()

            return task_sources

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching task sources: {e}")
            return []

    async def delete_task_source(self, task_source_id: UUID) -> bool:
        try:
            result = await self.db.execute(
                select(TaskSource).filter(
                    TaskSource.id == task_source_id, TaskSource.deleted_at.is_(None)
                )
            )
            task_source = result.scalar_one_or_none()

            if not task_source:
                return False

            # Soft delete by setting deleted_at timestamp
            task_source.deleted_at = datetime.utcnow()

            await self.db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while deleting TaskSource: {e}")
            await self.db.rollback()
            return False
