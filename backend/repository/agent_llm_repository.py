# Custom libraries
from models.agent_llm import AgentLLM
from logger import configure_logging

# Default libraries
from typing import Optional, List, Dict, Union
from uuid import UUID

# Installed libraries
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import desc, asc, or_, cast, String
from fastapi import HTTPException

logger = configure_logging(__name__)


class AgentLLMRepository:
    """Repository class for managing AgentLLM database operations."""

    def __init__(self, db: Session):
        """Initialize the repository with a database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def create_agent_llm(self, agent_llm_data: Dict) -> Optional[AgentLLM]:
        """Create a new AgentLLM record in the database.

        Args:
            agent_llm_data: Dictionary containing AgentLLM field values

        Returns:
            Created AgentLLM instance or None if creation fails

        Raises:
            HTTPException: If an AgentLLM with the same llm_key already exists
        """
        agent_llm = AgentLLM(**agent_llm_data)
        try:
            self.db.add(agent_llm)
            self.db.commit()
            self.db.refresh(agent_llm)
            return agent_llm
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent LLM with same llm_key already exists.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error while creating AgentLLM: {e}")
            return None

    def create_or_update_agent_llm(self, update_data: Dict) -> Optional[AgentLLM]:
        """Create a new AgentLLM or update an existing one based on llm_key.

        Args:
            update_data: Dictionary containing AgentLLM field values, must include 'llm_key'

        Returns:
            Created or updated AgentLLM instance, or None if operation fails

        Raises:
            HTTPException: If update fails due to integrity constraint violation
        """
        try:
            llm_key_to_update = update_data.get("llm_key")

            agent_llm = (
                self.db.query(AgentLLM)
                .filter(AgentLLM.llm_key == llm_key_to_update)
                .first()
            )

            if agent_llm:
                for field, value in update_data.items():
                    if hasattr(agent_llm, field):
                        setattr(agent_llm, field, value)
            else:
                agent_llm = AgentLLM(**update_data)
                self.db.add(agent_llm)

            self.db.commit()
            self.db.refresh(agent_llm)
            return agent_llm

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent LLM update failed due to integrity constraint.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_agent_llm_by_id(self, update_data: Dict) -> Optional[AgentLLM]:
        """Update an existing AgentLLM record by its UUID.

        Args:
            update_data: Dictionary containing update fields, must include 'agent_llm_uuid'

        Returns:
            Updated AgentLLM instance, or None if not found or update fails

        Raises:
            HTTPException: If an AgentLLM with the same llm_key already exists
        """
        identifier = update_data.get("agent_llm_uuid")
        agent_llm = self.db.query(AgentLLM).filter(AgentLLM.id == identifier).first()
        if not agent_llm:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(agent_llm, key):
                    setattr(agent_llm, key, value)
            self.db.commit()
            self.db.refresh(agent_llm)
            return agent_llm
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Agent LLM with same llm_key already exists.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error updating Agent LLM: {e}")
            return None

    def get_agent_llm_by_id(self, agent_llm_uuid: UUID) -> Optional[AgentLLM]:
        """Retrieve an AgentLLM record by its UUID.

        Args:
            agent_llm_uuid: UUID of the AgentLLM to retrieve

        Returns:
            AgentLLM instance if found, None otherwise
        """
        try:
            return self.db.query(AgentLLM).filter(AgentLLM.id == agent_llm_uuid).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching Agent LLM: {e}")
            return None

    def get_all_agent_llms(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[AgentLLM]:
        """Retrieve all AgentLLM records with optional filtering, sorting, and pagination.

        Args:
            page: Page number for pagination (1-indexed)
            page_size: Number of records per page
            filters: Dictionary of field-value pairs to filter by
            sort_by: Field name to sort by (default: 'updated_at')
            sort_order: Sort order, 'asc' or 'desc' (default: 'desc')

        Returns:
            List of AgentLLM instances matching the criteria
        """
        query = self.db.query(AgentLLM)

        if filters:
            for key, value in filters.items():
                if hasattr(AgentLLM, key):
                    if isinstance(value, list):
                        query = query.filter(getattr(AgentLLM, key).in_(value))
                    else:
                        query = query.filter(getattr(AgentLLM, key) == value)

        if hasattr(AgentLLM, sort_by):
            order = (
                asc(getattr(AgentLLM, sort_by))
                if sort_order.lower() == "asc"
                else desc(getattr(AgentLLM, sort_by))
            )
            query = query.order_by(order)

        try:
            if page and page_size:
                skip = (page - 1) * page_size
                return query.offset(skip).limit(page_size).all()
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error fetching agent LLMs: {e}")
            return []

    def search_agent_llms(
        self,
        keyword: str,
        filters: Optional[Dict[str, Union[str, List[str]]]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[AgentLLM]:
        """Search AgentLLM records by keyword with optional filtering, sorting, and pagination.

        Searches in llm_key, name, and provider fields using case-insensitive pattern matching.

        Args:
            keyword: Search term to match against llm_key, name, or provider
            filters: Dictionary of field-value pairs to filter by
            page: Page number for pagination (1-indexed)
            page_size: Number of records per page
            sort_by: Field name to sort by (default: 'updated_at')
            sort_order: Sort order, 'asc' or 'desc' (default: 'desc')

        Returns:
            List of AgentLLM instances matching the search criteria
        """
        query = self.db.query(AgentLLM)

        if filters:
            for key, value in filters.items():
                if hasattr(AgentLLM, key):
                    if isinstance(value, list):
                        query = query.filter(getattr(AgentLLM, key).in_(value))
                    else:
                        query = query.filter(getattr(AgentLLM, key) == value)

        if keyword:
            query = query.filter(
                or_(
                    AgentLLM.llm_key.ilike(f"%{keyword}%"),
                    cast(AgentLLM.data["name"], String).ilike(f"%{keyword}%"),
                    cast(AgentLLM.data["provider"], String).ilike(f"%{keyword}%"),
                )
            )

        if hasattr(AgentLLM, sort_by):
            order = (
                asc(getattr(AgentLLM, sort_by))
                if sort_order.lower() == "asc"
                else desc(getattr(AgentLLM, sort_by))
            )
            query = query.order_by(order)

        try:
            if page and page_size:
                skip = (page - 1) * page_size
                return query.offset(skip).limit(page_size).all()
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error during agent LLM search: {e}")
            return []

    def delete_agent_llm(self, agent_llm_uuid: UUID) -> bool:
        """Delete an AgentLLM record by its UUID.

        Args:
            agent_llm_uuid: UUID of the AgentLLM to delete

        Returns:
            True if deletion was successful, False if record not found or deletion fails
        """
        try:
            agent_llm = (
                self.db.query(AgentLLM).filter(AgentLLM.id == agent_llm_uuid).first()
            )

            if not agent_llm:
                return False

            self.db.delete(agent_llm)
            self.db.commit()
            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error deleting Agent LLM: {e}")
            return False
