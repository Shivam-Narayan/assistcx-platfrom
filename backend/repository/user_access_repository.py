# Custom libraries
from logger import configure_logging

# Database modules
from models.user_access import UserAccess
from models.user_role import UserRole

# Default libraries
from typing import Dict, Optional
from uuid import UUID

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(logger_name=__name__)


class UserAccessRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_user_access(self):
        try:
            return self.db.query(UserAccess).all()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_user_access_by_user_id(self, user_uuid: UUID) -> Optional[UserAccess]:
        try:
            return (
                self.db.query(UserAccess)
                .filter(UserAccess.user_id == user_uuid)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_role_by_user_id(self, user_uuid: UUID) -> Optional[UserRole]:
        try:
            return (
                self.db.query(UserRole)
                .join(UserAccess, UserRole.id == UserAccess.role_id)
                .filter(UserAccess.user_id == user_uuid)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def remove_permissions_user_access(self, permission_key: str):
        try:
            # Fetch all user accesses
            user_accesses = self.get_all_user_access()

            # Iterate through user accesses
            for user_access in user_accesses:
                if user_access.data_access:
                    # Filter out keys that don't match the permission_key
                    user_access.data_access = {
                        key: value
                        for key, value in user_access.data_access.items()
                        if key != permission_key
                    }

            # Commit changes
            self.db.commit()
            logger.info(f"Removed permission '{permission_key}' from all user accesses")

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Error removing permissions from user accesses: {e}")

    def update_user_access_by_user_id(
        self,
        user_id: UUID,
        update_data: Dict
    ) -> Optional[UserAccess]:
        try:
            user_access = (
                self.db.query(UserAccess)
                .filter(UserAccess.user_id == user_id)
                .first()
            )

            if not user_access:
                return None

            for key, value in update_data.items():
                setattr(user_access, key, value)

            self.db.commit()
            self.db.refresh(user_access)
            return user_access

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None
