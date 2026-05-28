# Custom libraries
from logger import configure_logging

# Database modules
from models.authentication import Authentication

# Default libraries
from typing import Optional
from uuid import UUID

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class AuthenticationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_authentication(self, user_uuid: UUID, authentication_data: dict):
        authentication_instance = Authentication(
            user_uuid=user_uuid,
            access_token=authentication_data["access_token"],
            refresh_token=authentication_data["refresh_token"],
        )

        try:
            self.db.add(authentication_instance)
            self.db.commit()
            self.db.refresh(authentication_instance)
            return authentication_instance
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def update_authentication(self, old_refresh_token: str, update_data: dict):
        authentication_instance = (
            self.db.query(Authentication)
            .filter(Authentication.refresh_token == old_refresh_token)
            .first()
        )

        if not authentication_instance:
            return None

        try:
            for key, value in update_data.items():
                if hasattr(authentication_instance, key):
                    setattr(authentication_instance, key, value)

            self.db.commit()
            self.db.refresh(authentication_instance)
            return authentication_instance
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    # def create_or_update_authentication(self, user_uuid: UUID, data: dict):
    #     query_filter = Authentication.user_uuid == user_uuid
    #     existing_auth = self.db.query(Authentication).filter(query_filter).first()

    #     if existing_auth:
    #         return self.update_authentication(user_uuid, data)
    #     else:
    #         return self.create_authentication(user_uuid, data)

    def get_user_by_uuid(self, user_uuid: UUID) -> Optional[Authentication]:
        try:
            query_filter = Authentication.user_uuid == user_uuid
            authentication_instance = (
                self.db.query(Authentication).filter(query_filter).all()
            )
            return authentication_instance
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def delete_authentication(self, user_uuid: UUID) -> bool:
        try:
            deleted_count = (
                self.db.query(Authentication)
                .filter(Authentication.user_uuid == user_uuid)
                .delete()
            )

            if deleted_count == 0:
                logger.warning(f"No authentication found for user {user_uuid}")
                return False

            self.db.commit()
            return True
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return False
