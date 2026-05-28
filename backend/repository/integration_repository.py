# Custom libraries
from configs.integrations import AUTH_SCHEMA_FIELDS
from logger import configure_logging
from utils.crypto_utils import encrypt_string, decrypt_string
from utils.environment import environment
from utils.schema_utils import get_current_schema

# Database modules
from models.integration import Integration
from schemas.integration_schema import DefaultIntegration

# Default libraries
from typing import Optional, Tuple, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException
from sqlalchemy import asc, desc, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    def _encrypt_credentials(self, credentials: dict) -> dict:
        try:
            res = {key: encrypt_string(value) for key, value in credentials.items()}
            return res
        except Exception as e:
            logger.error(f"Error encrypting credentials: {e}")
            return {}

    def _decrypt_credentials(self, credentials: dict) -> dict:
        try:
            res = {key: decrypt_string(value) for key, value in credentials.items()}
            return res
        except Exception as e:
            logger.error(f"Error decrypting credentials: {e}")
            return {}

    def _update_redis(self, integration: Integration):
        # Get schema once and reuse
        org_schema = get_current_schema(self.db)

        # Get and update environment data in one operation using dict.update()
        env_data = environment.get_environment(organization_schema=org_schema) or {}
        env_data[integration.key.upper()] = integration.credentials

        # Set updated environment data
        environment.set_environment(
            environment_data=env_data, organization_schema=org_schema
        )

    def create_integration(self, integration_data: Dict) -> Optional[Integration]:
        try:
            new_integration = Integration(**integration_data)
            self.db.add(new_integration)
            self.db.commit()
            self.db.refresh(new_integration)
            return new_integration
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Integration with the same key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_integration(self, update_data: dict) -> Optional[Integration]:
        try:
            key_to_update = update_data.get("key")

            integration = (
                self.db.query(Integration)
                .filter(Integration.key == key_to_update)
                .first()
            )

            if integration:
                # Update the fields based on the provided data
                for field, value in update_data.items():
                    setattr(integration, field, value)
            else:
                # Create a new integration if the key is missing
                integration = Integration(**update_data)
                self.db.add(integration)

            self.db.commit()
            self.db.refresh(integration)
            return integration

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Integration with the same key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_integration_by_id(self, update_data: dict) -> Optional[Integration]:

        try:
            identifier = update_data.get("integration_uuid")
            query_filter = Integration.id == identifier
            integration = self.db.query(Integration).filter(query_filter).first()
            if not integration:
                return None
            if "credentials" in update_data:
                # Check if we want to clear credentials
                if update_data["credentials"] is None:
                    integration.credentials = None
                else:
                    # Handle normal credential updates
                    update_data["credentials"] = self._encrypt_credentials(
                        update_data["credentials"]
                    )
                    if integration.credentials:
                        integration.credentials = {
                            **integration.credentials,
                            **update_data["credentials"],
                        }
                    else:
                        integration.credentials = update_data["credentials"]
                update_data.pop("credentials")

            for key, value in update_data.items():
                if hasattr(integration, key):
                    setattr(integration, key, value)
            self.db.commit()
            self.db.refresh(integration)
            self._update_redis(integration)
            return integration
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy IntegrityError: {e}")
            raise HTTPException(
                status_code=409,
                detail="Integration with the same key already exists. Please check and retry.",
            )
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_integration(
        self, integration_data: dict
    ) -> Optional[Integration]:
        key = integration_data.get("key")
        if not key:
            return None
        integration = self.db.query(Integration).filter(Integration.key == key).first()
        if integration:
            return self.update_integration(integration_data)
        else:
            return self.create_integration(integration_data)

    def get_integration(
        self, identifier: Union[UUID, str], decrypt_credentials: Optional[bool] = False
    ) -> Optional[Integration]:
        if isinstance(identifier, UUID):
            query_filter = Integration.id == identifier
        elif isinstance(identifier, str):
            query_filter = Integration.key == identifier
        else:
            raise ValueError("Identifier must be a UUID or a string.")
        try:
            integration = self.db.query(Integration).filter(query_filter).first()
            if not integration:
                return None

            # Set auth schema fields
            integration.auth_schema_fields = AUTH_SCHEMA_FIELDS.get(
                integration.auth_schema
            )

            # Handle credentials
            if integration.credentials:
                decrypted_credentials = self._decrypt_credentials(
                    integration.credentials
                )
                if decrypt_credentials:
                    # Detach the integration from the session to prevent accidental commits
                    # of decrypted credentials when we modify the credentials attribute
                    self.db.expunge(integration)
                    integration.credentials = decrypted_credentials

            return integration
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_integration_tags(self) -> List[str]:
        try:
            tags_query = self.db.query(Integration.tags).distinct().all()
            unique_tags = {tag for tags in tags_query for tag in tags[0]}
            return list(unique_tags)
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_all_integrations(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Integration], int]:
        query = self.db.query(Integration)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Integration, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Integration, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Integration, key) == values)

        # Apply sorting
        if hasattr(Integration, sort_by):
            order = (
                asc(getattr(Integration, sort_by))
                if sort_order == "asc"
                else desc(getattr(Integration, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                integrations = query.offset(skip).limit(page_size).all()
            else:
                integrations = query.all()

            return integrations, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def search_integrations(
        self,
        keyword: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Integration], int]:
        query = self.db.query(Integration)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Integration, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Integration, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Integration, key) == values)

        # Apply search
        if keyword:
            query = query.filter(
                or_(
                    Integration.name.ilike(f"%{keyword}%"),
                    Integration.key.ilike(f"%{keyword}%"),
                    Integration.description.ilike(f"%{keyword}%"),
                )
            )

        # Apply sorting
        if hasattr(Integration, sort_by):
            order = (
                asc(getattr(Integration, sort_by))
                if sort_order == "asc"
                else desc(getattr(Integration, sort_by))
            )
            query = query.order_by(order)

        try:
            total = query.count()

            # Only apply pagination if both page and page_size are provided
            if page and page_size:
                skip = (page - 1) * page_size
                integrations = query.offset(skip).limit(page_size).all()
            else:
                integrations = query.all()

            return integrations, total
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def get_active_agent_llm(self) -> List[Dict]:
        """
        Retrieves full LLM configuration objects from active and validated agent_llm integrations.

        Returns:
            List[Dict]: List of complete LLM configuration dictionaries
        """
        from configs.integrations import INTEGRATIONS
        from utils.integration_utils import IntegrationValidator
        from repository.agent_llm_repository import AgentLLMRepository

        active_llms = []

        try:
            # Fetch active agent_llm integrations that are active
            agent_llm_integrations = (
                self.db.query(Integration)
                .filter(
                    Integration.integration_config["integration_type"].astext
                    == "agent_llm",
                    Integration.is_active == True,
                )
                .all()
            )

            if not agent_llm_integrations:
                return []

            # Get all LLMs from database
            agent_llm_repo = AgentLLMRepository(self.db)
            all_llms = agent_llm_repo.get_all_agent_llms()

            for integration in agent_llm_integrations:
                provider_key = integration.key

                # Skip if no credentials
                if not integration.credentials:
                    continue

                # Decrypt credentials
                decrypted_credentials = self._decrypt_credentials(
                    integration.credentials
                )
                if not decrypted_credentials:
                    logger.error(f"Failed to decrypt credentials for '{provider_key}'")
                    continue

                # Get auth schema
                auth_schema_fields = AUTH_SCHEMA_FIELDS.get(integration.auth_schema)
                if not auth_schema_fields:
                    continue

                # Validate credentials
                validator = IntegrationValidator(
                    auth_schema=AUTH_SCHEMA_FIELDS,
                    preset=auth_schema_fields.get("preset", {}),
                    integrations=INTEGRATIONS,
                )

                is_valid, error_message = validator.validate_credentials(
                    provider_key, decrypted_credentials
                )

                if not is_valid:
                    continue

                # Get LLMs for this provider from database
                provider_llms = [
                    {
                        "id": llm.id,
                        "llm_key": llm.llm_key,
                        "name": llm.data.get("name") if llm.data else "",
                        "description": llm.data.get("description") if llm.data else "",
                        "model_name": llm.data.get("model_name") if llm.data else "",
                        "provider": llm.data.get("provider") if llm.data else "",
                        "integration_key": llm.data.get("integration_key") if llm.data else "",
                        "llm_config": llm.data.get("llm_config", {}) if llm.data else {},
                        "metadata": llm.data.get("metadata", {}) if llm.data else {},
                        "created_at": llm.created_at,
                        "updated_at": llm.updated_at,
                    }
                    for llm in all_llms
                    if llm.data and llm.data.get("provider") == provider_key
                ]
                if provider_llms:
                    active_llms.extend(provider_llms)

            return active_llms

        except SQLAlchemyError as e:
            logger.error(f"Database error while fetching active agent LLMs: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching active agent LLMs: {e}")
            return []
