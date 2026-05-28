# Custom libraries
from logger import configure_logging
from utils.schema_utils import run_alembic_migration
from agents.shared_utils.checkpointer import run_checkpointer_migrations

# Database modules
from models.organization import Organization

# Default libraries
from typing import Optional, Union, Dict, List
from uuid import UUID


# Installed libraries
from asgiref.sync import async_to_sync
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema


logger = configure_logging(__name__)


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_organization(self, organization_data: dict) -> Optional[Organization]:

        try:
            new_organization = Organization(**organization_data)
            self.db.add(new_organization)
            self.db.commit()
            self.db.refresh(new_organization)
            self.db.execute(
                CreateSchema(str(new_organization.db_schema), if_not_exists=True)
            )
            self.db.commit()
            # Run Alembic migration
            run_alembic_migration(new_organization.db_schema)
            # Convert async function to sync using async_to_sync
            async_to_sync(run_checkpointer_migrations)(str(new_organization.db_schema))
            return new_organization
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Organization with the given name or tenant code already exists.",
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_organization(self, update_data: dict) -> Optional[Organization]:
        identifier = update_data.get("organization_uuid")
        query_filter = (
            Organization.id == identifier
            if isinstance(identifier, UUID)
            else Organization.db_schema == identifier
        )
        organization = self.db.query(Organization).filter(query_filter).first()
        if not organization:
            return None
        try:
            for key, value in update_data.items():
                if hasattr(organization, key):
                    setattr(organization, key, value)
            self.db.commit()
            self.db.refresh(organization)
            return organization
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Organization with the given name or tenant code already exists.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_organization(self, identifier: Union[UUID, str]) -> Optional[Organization]:
        if isinstance(identifier, UUID):
            query_filter = Organization.id == identifier
        elif isinstance(identifier, str):
            query_filter = Organization.name == identifier
        else:
            raise ValueError("Identifier must be a UUID or a name string")
        try:
            return self.db.query(Organization).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_all_organizations(
        self,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[Organization]:
        query = self.db.query(Organization)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Organization, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Organization, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Organization, key) == values)

        # Apply sorting
        if hasattr(Organization, sort_by):
            order = (
                asc(getattr(Organization, sort_by))
                if sort_order == "asc"
                else desc(getattr(Organization, sort_by))
            )
            query = query.order_by(order)

        try:
            organizations = query.all()
            return organizations
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_organization_by_tenant_code(
        self, tenant_code: str
    ) -> Optional[Organization]:
        if not isinstance(tenant_code, str):
            raise ValueError("Tenant code must be a string")

        try:
            return (
                self.db.query(Organization)
                .filter(Organization.tenant_code == tenant_code)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_organization_by_db_schema(self, db_schema: str) -> Optional[Organization]:
        if not isinstance(db_schema, str):
            raise ValueError("DB Schema must be a string")

        try:
            return (
                self.db.query(Organization)
                .filter(Organization.db_schema == db_schema)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None
