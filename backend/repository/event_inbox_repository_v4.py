from logger import configure_logging
from models.event_inbox_v4 import EventInbox

from typing import Optional, Dict, List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, or_, asc, desc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.event_inbox_schema_v4 import EventInboxCreate


logger = configure_logging(__name__)


class EventInboxRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_event_inbox(
        self, event_inbox_data: EventInboxCreate
    ) -> Optional[EventInbox]:

        data = event_inbox_data.model_dump()
        event_inbox = EventInbox(**data)

        try:
            self.db.add(event_inbox)
            await self.db.commit()
            await self.db.refresh(event_inbox)
            return event_inbox
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Event inbox dedupe_key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating EventInbox: {e}")
            return None

    async def update_event_inbox(self, update_data: dict) -> Optional[EventInbox]:
        event_inbox_id = update_data.get("event_inbox_id")
        result = await self.db.execute(
            select(EventInbox).filter(EventInbox.id == event_inbox_id)
        )
        event_inbox = result.scalar_one_or_none()
        if not event_inbox:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(event_inbox, key):
                    setattr(event_inbox, key, value)
            await self.db.commit()
            await self.db.refresh(event_inbox)
            return event_inbox
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Event inbox dedupe_key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while updating EventInbox: {e}")
            return None

    async def get_event_inbox_by_id(self, event_inbox_id: UUID) -> Optional[EventInbox]:

        try:
            result = await self.db.execute(
                select(EventInbox).filter(EventInbox.id == event_inbox_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching EventInbox: {e}")
            return None

    async def get_all_event_inbox(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[EventInbox]:
        query = select(EventInbox)

        if filters:
            for key, values in filters.items():
                if hasattr(EventInbox, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(EventInbox, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(EventInbox, key) == values)

        if keyword:
            query = query.filter(
                or_(
                    EventInbox.external_event_id.ilike(f"%{keyword}%"),
                    EventInbox.dedupe_key.ilike(f"%{keyword}%"),
                )
            )

        if hasattr(EventInbox, sort_by):
            order = (
                asc(getattr(EventInbox, sort_by))
                if sort_order == "asc"
                else desc(getattr(EventInbox, sort_by))
            )
            query = query.order_by(order)

        try:
            # Apply pagination if provided
            if page and page_size:
                skip = (page - 1) * page_size
                query = query.offset(skip).limit(page_size)

            result = await self.db.execute(query)
            return result.scalars().all()

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching EventInbox list: {e}")
            return []

    async def delete_event_inbox(self, event_inbox_id: UUID) -> bool:

        try:
            result = await self.db.execute(
                select(EventInbox).filter(EventInbox.id == event_inbox_id)
            )
            event_inbox = result.scalar_one_or_none()
            if not event_inbox:
                return False

            await self.db.delete(event_inbox)
            await self.db.commit()
            return True
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while deleting EventInbox: {e}")
            return False
