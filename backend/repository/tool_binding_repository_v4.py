# Custom libraries
from logger import configure_logging
from models.tool_binding_v4 import ToolBinding

# Default libraries
from typing import Optional, Dict, List, Any
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import select, asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# Schema imports
from schemas.tool_binding_schema_v4 import ToolBindingCreate


logger = configure_logging(__name__)


class ToolBindingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tool_binding(
        self, data: ToolBindingCreate
    ) -> Optional[ToolBinding]:
        binding = ToolBinding(**data.model_dump())
        try:
            self.db.add(binding)
            await self.db.commit()
            await self.db.refresh(binding)
            return binding
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Tool binding with same agent_id and tool_key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating ToolBinding: {e}")
            return None

    async def update_tool_binding(self, update_data: dict) -> Optional[ToolBinding]:
        tool_binding_id = update_data.get("tool_binding_id")
        result = await self.db.execute(
            select(ToolBinding).where(ToolBinding.id == tool_binding_id)
        )
        binding = result.scalar_one_or_none()
        if not binding:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(binding, key):
                    setattr(binding, key, value)
            await self.db.commit()
            await self.db.refresh(binding)
            return binding
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Tool binding with same agent_id and tool_key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"SQLAlchemy Error while updating ToolBinding: {e}")
            return None

    async def get_tool_binding_by_id(
        self, tool_binding_id: UUID
    ) -> Optional[ToolBinding]:
        try:
            result = await self.db.execute(
                select(ToolBinding).where(ToolBinding.id == tool_binding_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching ToolBinding: {e}")
            return None

    async def get_tool_bindings_by_agent_id(self, agent_id: UUID) -> List[ToolBinding]:
        """Fetch all tool bindings for an agent (tool_key -> connection_id). Used by executor to build connection_by_tool."""
        try:
            result = await self.db.execute(
                select(ToolBinding).where(ToolBinding.agent_id == agent_id)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(
                f"SQLAlchemy Error while fetching tool bindings for agent {agent_id}: {e}"
            )
            return []

    async def get_all_tool_bindings(
        self,
        keyword: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[ToolBinding]:
        query = select(ToolBinding)
        if filters:
            for key, values in filters.items():
                if hasattr(ToolBinding, key):
                    if isinstance(values, list):
                        condition = or_(
                            *(getattr(ToolBinding, key) == value for value in values)
                        )
                        query = query.where(condition)
                    else:
                        query = query.where(getattr(ToolBinding, key) == values)
        if keyword:
            query = query.where(
                or_(
                    ToolBinding.provider_key.ilike(f"%{keyword}%"),
                    ToolBinding.tool_key.ilike(f"%{keyword}%"),
                )
            )
        if hasattr(ToolBinding, sort_by):
            order = (
                asc(getattr(ToolBinding, sort_by))
                if sort_order == "asc"
                else desc(getattr(ToolBinding, sort_by))
            )
            query = query.order_by(order)
        if page and page_size:
            query = query.offset((page - 1) * page_size).limit(page_size)
        try:
            result = await self.db.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while fetching tool bindings: {e}")
            return []

    async def delete_tool_binding(self, tool_binding_id: UUID) -> bool:
        try:
            result = await self.db.execute(
                select(ToolBinding).where(ToolBinding.id == tool_binding_id)
            )
            binding = result.scalar_one_or_none()
            if not binding:
                return False
            await self.db.delete(binding)
            await self.db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error while deleting ToolBinding: {e}")
            await self.db.rollback()
            return False
