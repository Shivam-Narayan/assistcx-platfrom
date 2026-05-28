# Custom libraries
from logger import configure_logging
from utils.environment import environment
from utils.crypto_utils import encrypt_string
from utils.schema_utils import get_current_schema

# Database modules
from models.configuration import Configuration

# Default libraries
from typing import Optional

# Installed libraries
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class ConfigurationRepository:
    def __init__(self, db: Session):
        self.db = db

    def _update_redis(self, schema: str, config: Configuration):
        # Set the environment preferences in Redis
        environment.set_preferences(config.preferences, schema)

    def _update_existing_config(
        self, existing_config: Configuration, new_config: dict
    ) -> Configuration:
        for key, value in new_config.items():
            setattr(existing_config, key, value)

        return existing_config

    def create_or_update_configuration(
        self, configuration_data: dict
    ) -> Optional[Configuration]:
        try:
            organization_schema = get_current_schema(self.db)
            existing_config = self.db.query(Configuration).first()

            if existing_config:
                config = self._update_existing_config(
                    existing_config, configuration_data
                )
            else:
                config = Configuration(**configuration_data)
                self.db.add(config)

            self.db.commit()
            self.db.refresh(config)
            self._update_redis(organization_schema, config)
            return config

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            self.db.rollback()
            return None

    def get_configuration(self) -> Optional[Configuration]:
        try:
            return (
                self.db.query(Configuration)
                .order_by(Configuration.created_at.desc())
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None
