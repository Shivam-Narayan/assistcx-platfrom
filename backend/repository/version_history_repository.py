# Custom libraries
from logger import configure_logging

# Database modules
from models.version_history import VersionHistory
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, List, Dict, Union
from uuid import UUID

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc, asc, func


logger = configure_logging(__name__)


class VersionHistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_version_history(
        self, version_history_data: Dict
    ) -> Optional[VersionHistory]:
        """
        Creates a new version history based on version_history_data.
        """
        new_version_history = VersionHistory(**version_history_data)
        try:
            self.db.add(new_version_history)
            self.db.commit()
            self.db.refresh(new_version_history)
            return new_version_history
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_version_history_by_id(
        self, identifier: Union[UUID, str]
    ) -> Optional[VersionHistory]:
        """
        Retrieves version history information based on identifier.
        """
        if isinstance(identifier, UUID):
            target_id = identifier
        else:
            target_id = UUID(identifier)

        try:
            # Create subquery with window function for ALL rows first
            version_number_col = (
                func.row_number()
                .over(
                    partition_by=[VersionHistory.entity_type, VersionHistory.entity_id],
                    order_by=VersionHistory.created_at.asc(),
                )
                .label("version_number")
            )

            # Subquery calculates version numbers for all rows
            subquery = self.db.query(
                VersionHistory.id,
                VersionHistory.entity_type,
                VersionHistory.entity_id,
                VersionHistory.config_data,
                VersionHistory.user_id,
                VersionHistory.created_at,
                version_number_col,
            ).subquery()

            # THEN filter by target_id in outer query
            result = self.db.query(subquery).filter(subquery.c.id == target_id).first()

            if result:
                # Construct VersionHistory object from subquery result
                version_history = VersionHistory(
                    id=result.id,
                    entity_type=result.entity_type,
                    entity_id=result.entity_id,
                    config_data=result.config_data,
                    user_id=result.user_id,
                    created_at=result.created_at,
                )
                version_history.version_number = result.version_number

                # Fetch user information
                user = UserRepository(self.db).get_user_by_id(
                    UUID(version_history.user_id)
                )
                if user:
                    version_history.user_name = " ".join(
                        name for name in (user.first_name, user.last_name) if name
                    )
                    version_history.user_email = user.email
                return version_history

            return None

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_version_histories(
        self,
        filters: Optional[Dict[str, any]] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
    ) -> List[VersionHistory]:
        """
        Retrieves version history information with optional filters, pagination and sorting.
        """
        try:
            # Start with base query and apply filters FIRST (before window function)
            base_query = self.db.query(VersionHistory)

            # Apply filters to base query to reduce dataset
            if filters:
                for key, value in filters.items():
                    if hasattr(VersionHistory, key):
                        if isinstance(value, list):
                            base_query = base_query.filter(
                                getattr(VersionHistory, key).in_(value)
                            )
                        else:
                            base_query = base_query.filter(
                                getattr(VersionHistory, key) == value
                            )

            # Create filtered subquery with version numbers
            version_number_col = (
                func.row_number()
                .over(
                    partition_by=[VersionHistory.entity_type, VersionHistory.entity_id],
                    order_by=VersionHistory.created_at.asc(),
                )
                .label("version_number")
            )

            subquery = base_query.add_columns(version_number_col).subquery()

            # Query from the subquery with all columns
            query = self.db.query(subquery)

            # Apply sorting
            if hasattr(subquery.c, sort_by):
                order = (
                    asc(getattr(subquery.c, sort_by))
                    if sort_order == "asc"
                    else desc(getattr(subquery.c, sort_by))
                )
                query = query.order_by(order)

            # Apply pagination only if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                query = query.offset(skip).limit(page_size)

            results = query.all()

            # Convert results to VersionHistory objects with version_number
            version_histories = []
            for row in results:
                # Construct VersionHistory object from row data
                version_history = VersionHistory(
                    id=row.id,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    config_data=row.config_data,
                    user_id=row.user_id,
                    created_at=row.created_at,
                )
                version_history.version_number = row.version_number

                # Fetch user information
                user = UserRepository(self.db).get_user_by_id(
                    UUID(version_history.user_id)
                )
                if user:
                    names = filter(None, [user.first_name, user.last_name])
                    version_history.user_name = " ".join(names)
                    version_history.user_email = user.email

                version_histories.append(version_history)

            return version_histories

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []
