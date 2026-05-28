# Custom libraries
from logger import configure_logging
from models.connection_v4 import Connection
from models.user import User

# Default libraries
from typing import Optional, Dict, List, Any
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import select, asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


# Schema imports
from schemas.connection_schema_v4 import ConnectionCreate


logger = configure_logging(__name__)


class ConnectionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _attach_user_name(self, connection: Connection) -> None:
        if connection.created_by:
            user_result = await self.db.execute(
                select(User.first_name, User.last_name).filter(User.id == connection.created_by)
            )
            user = user_result.one_or_none()
            if user:
                connection.user_name = " ".join(filter(None, [user.first_name, user.last_name]))

    async def create_connection(self, data: dict) -> Optional[Connection]:
        """
        Create a connection. Expects data dict with encrypted_credentials (JSON string
        of encrypted credential values), created_by, and other connection fields.
        """
        connection = Connection(**data)
        try:
            self.db.add(connection)
            await self.db.commit()
            await self.db.refresh(connection)
            await self._attach_user_name(connection)
            return connection
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating Connection: {e}")
            return None

    async def update_connection(self, update_data: dict) -> Optional[Connection]:
        connection_id = update_data.get("connection_id")
        result = await self.db.execute(
            select(Connection).filter(
                Connection.id == connection_id, Connection.deleted_at.is_(None)
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(connection, key):
                    setattr(connection, key, value)
            await self.db.commit()
            await self.db.refresh(connection)
            await self._attach_user_name(connection)
            return connection
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while updating Connection: {e}")
            return None

    async def get_connection_by_id(self, connection_id: UUID) -> Optional[Connection]:
        try:
            result = await self.db.execute(
                select(Connection).filter(
                    Connection.id == connection_id, Connection.deleted_at.is_(None)
                )
            )
            connection = result.scalar_one_or_none()

            if connection:
                await self._attach_user_name(connection)

            return connection
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching Connection: {e}")
            return None

    async def get_all_connections(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[Connection]:
        query = select(Connection).filter(Connection.deleted_at.is_(None))

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Connection, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(Connection, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Connection, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    Connection.name.ilike(f"%{keyword}%"),
                    Connection.provider_key.ilike(f"%{keyword}%"),
                    Connection.auth_schema_key.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(Connection, sort_by):
            order = (
                asc(getattr(Connection, sort_by))
                if sort_order == "asc"
                else desc(getattr(Connection, sort_by))
            )
            query = query.order_by(order)

        try:
            # Apply pagination if provided
            if page and page_size:
                skip = (page - 1) * page_size
                query = query.offset(skip).limit(page_size)

            result = await self.db.execute(query)
            connections = result.scalars().all()

            for connection in connections:
                await self._attach_user_name(connection)

            return connections

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching connections: {e}")
            return []

    async def delete_connection(self, connection_id: UUID) -> bool:
        try:
            result = await self.db.execute(
                select(Connection).filter(
                    Connection.id == connection_id, Connection.deleted_at.is_(None)
                )
            )
            connection = result.scalar_one_or_none()

            if not connection:
                return False

            # Hard delete: remove the row from the database.
            await self.db.delete(connection)
            await self.db.commit()
            return True

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while deleting Connection: {e}")
            await self.db.rollback()
            return False
