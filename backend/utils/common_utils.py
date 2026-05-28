# Custom libraries
from integrations.aws.aws_s3 import AWSS3
from logger import configure_logging
from schemas.agent_output_schema import AgentOutputDetail
from schemas.task_event_schema import TaskEventBase
from utils.schema_utils import get_current_schema, get_schema_db, get_async_schema_db

# Database modules
from repository.agent_tool_repository import AgentToolRepository
from repository.task_event_repository import TaskEventRepository
from repository.user_repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User

# Default libraries
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID
import json
import os
import random
import string

# Installed libraries
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import decode
from sqlalchemy import asc, desc, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import rsa

logger = configure_logging(__name__)


def get_new_items(
    existing_items: List[dict], new_items: List[dict], key_field: str = "name"
) -> List[dict]:
    """
    Generic utility function to identify new items by comparing existing and new item lists.
    Returns only the items that are new (present in new list but not in existing list).

    Args:
        existing_items: List of existing items (dicts)
        new_items: List of new items (dicts)
        key_field: The field name to use for comparison (default: 'name')

    Returns:
        List of items that are new (only in new_items, not in existing_items)
    """
    # Create a set of existing item keys for fast lookup
    existing_keys = {
        item.get(key_field) for item in existing_items if item.get(key_field)
    }

    # Filter new items that don't exist in the existing set
    new_only_items = []
    for item in new_items:
        item_key = item.get(key_field)
        if item_key and item_key not in existing_keys:
            new_only_items.append(item)

    return new_only_items


def add_task_event(db, task_event: dict):
    task_event_repo = TaskEventRepository(db)

    try:
        validated_data = TaskEventBase(**task_event).model_dump(exclude_unset=True)
        saved_event = task_event_repo.create_task_event(validated_data)
        if saved_event is None:
            logger.error("Failed to create a new task event in the database.")
            return None
        return saved_event
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        return None


def configure_data_parsing_configs(polling_config: dict) -> Optional[dict]:
    try:
        if polling_config.get("data_parsing") is False:
            polling_config["max_pdf_pages"] = 50
            polling_config["ocr_page_limit"] = None
            data_parsing_configs = [
                "ocr_parser",
                "split_pdf_pages",
                "fix_page_rotation",
                "preserve_page_layout",
                # "vision_correction",
            ]
            for config in data_parsing_configs:
                polling_config[config] = False
        return polling_config
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        return None


def decrypt_license_token(private_key_pem, encoded_string) -> Optional[dict]:
    try:
        # Convert the PEM format private key string to a PrivateKey object
        private_key = rsa.PrivateKey.load_pkcs1(private_key_pem.encode())

        # Decode the encoded string from hex
        encrypted_data = bytes.fromhex(encoded_string)

        # Decrypt the encoded data using the private key
        decrypted_data = rsa.decrypt(encrypted_data, private_key).decode()

        # Convert to python 🐍 dictionary and return
        return json.loads(decrypted_data)
    except Exception as e:
        # Catch exceptions
        logger.error(f"An error occurred: {e}")
        return {}


def generate_short_id(length: Optional[int] = 4):
    characters = string.ascii_lowercase + string.digits  # a-z, 0-9
    return "".join(random.choice(characters) for _ in range(length))


def get_integration_actions(
    db: Session, integration_type: str, integration_key: str
) -> list:
    """
    Get integration actions based on type.
    Returns a list of formatted action dictionaries.
    """
    try:
        if integration_type not in ("tool", "agent_llm"):
            return []

        # Initialize appropriate repository based on type
        if integration_type == "tool":
            repository = AgentToolRepository(db)
            agent_tools = repository.get_agent_tools_by_integration(
                integration_key=integration_key
            )
            bound_items = [agent_tool.__dict__ for agent_tool in agent_tools]
        elif integration_type == "agent_llm":
            from repository.agent_llm_repository import AgentLLMRepository

            agent_llm_repo = AgentLLMRepository(db)
            llms = agent_llm_repo.get_all_agent_llms()
            bound_items = [
                {
                    "id": str(llm.id),
                    "llm_key": llm.llm_key,
                    "name": llm.data.get("name") if llm.data else "",
                    "description": llm.data.get("description") if llm.data else "",
                }
                for llm in llms
                if llm.data and llm.data.get("integration_key") == integration_key
            ]

        # Define common action attributes based on type
        type_config = {
            "tool": {
                "type": "agent_tools",
                "action_field": lambda x: x.get("action"),
                "icon_field": lambda x: x.get("icon"),
            },
            "agent_llm": {
                "type": "agent_llm",
                "action_field": lambda x: x.get("llm_key"),
                "icon_field": lambda x: None,
            },
        }[integration_type]

        return [
            {
                "id": item.get("id", None),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "action": type_config["action_field"](item),
                "icon": type_config["icon_field"](item),
                "type": type_config["type"],
            }
            for item in bound_items
        ]

    except Exception as e:
        logger.error(f"An error occurred in get_integration_actions: {e}")


def get_storage_region(db: Session, data_store: Dict) -> str:
    """
    Retrieves the storage region for the given S3 bucket.
    """
    try:
        # Get the current schema
        organization_schema = get_current_schema(db)

        # Initialize the S3 utility with the schema and data store details
        aws_s3 = AWSS3(organization_schema, data_store)

        # Retrieve the storage region
        storage_region = aws_s3.get_bucket_region(data_store["storage_bucket"])

        return storage_region

    except Exception as e:
        logger.error(f"An error occurred in get_storage_region: {e}")


def sanitize_data_store(data_store: Dict) -> Dict:
    try:
        # Strip whitespace from all string fields in data_store
        for field in [
            "storage_type",
            "storage_bucket",
            "storage_folder",
        ]:
            if field in data_store:
                data_store[field] = data_store[field].strip()

        # Set default storage_folder if it's empty after stripping, else remove trailing slash
        data_store["storage_folder"] = data_store.get("storage_folder", "files").rstrip(
            "/"
        )

        return data_store

    except Exception as e:
        logger.error(f"An error occurred in sanitize_data_store: {e}")


def parse_identifier(identifier):
    # If already a UUID object, return as-is
    if isinstance(identifier, UUID):
        return identifier

    try:
        # Check if the string representation matches the original
        return UUID(identifier)
    except (ValueError, AttributeError):
        # If an error is raised, it is not a valid UUID
        return identifier


def get_current_user(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="authorize")),
    db: Session = Depends(get_schema_db),
) -> Dict[str, Any]:
    """
    FastAPI dependency that extracts and returns the current authenticated user context.

    Args:
        token: JWT token from OAuth2 scheme
        db: Database session

    Returns:
        Dictionary containing:
            - user: User model object
            - user_uuid: UUID of the user
            - user_name: Full name (first_name + last_name) or None

    Raises:
        HTTPException: If token is invalid or user not found
    """
    try:
        # Decode JWT token
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise HTTPException(status_code=500, detail="JWT secret not configured")

        decoded_token = decode(token, jwt_secret, algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])

        # Get user from repository
        user = UserRepository(db).get_user_by_id(user_uuid)

        # Build user_name
        user_name = None
        if user:
            names = filter(None, [user.first_name, user.last_name])
            user_name = (
                " ".join(names) if any([user.first_name, user.last_name]) else None
            )

        return {"user": user, "user_uuid": user_uuid, "user_name": user_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")


async def get_current_user_async(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="authorize")),
    db: AsyncSession = Depends(get_async_schema_db),  # ← Keep AsyncSession
) -> Dict[str, Any]:
    try:
        # Decode JWT token
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise HTTPException(status_code=500, detail="JWT secret not configured")

        decoded_token = decode(token, jwt_secret, algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])

        # Query user directly with async session (no repository)
        result = await db.execute(select(User).filter(User.id == user_uuid))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Build user_name
        user_name = None
        if user:
            names = filter(None, [user.first_name, user.last_name])
            user_name = (
                " ".join(names) if any([user.first_name, user.last_name]) else None
            )

        return {"user_uuid": user_uuid, "user_name": user_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user_async: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")


def transform_agent_actions(agent_output: AgentOutputDetail) -> AgentOutputDetail:
    """
    Helper function to transform agent_actions and execution_log based on the structure of agent_actions.
    If agent_actions contains a 'role' key, it copies agent_actions to execution_log and sets agent_actions to None.
    If agent_actions contains an 'action' key, no changes are made.

    Args:
        agent_output (AgentOutputDetail): The agent output object to transform.

    Returns:
        AgentOutputDetail: The modified agent output object.

    Raises:
        HTTPException: If agent_actions is a string but cannot be parsed as JSON.
    """
    if agent_output.agent_actions:
        try:
            # Parse agent_actions if it's a string
            if isinstance(agent_output.agent_actions, str):
                actions = json.loads(agent_output.agent_actions)
            else:
                actions = agent_output.agent_actions

            # Check if the first element has a "role" key
            if actions and isinstance(actions, list) and len(actions) > 0:
                first_action = actions[0]
                if "role" in first_action:
                    # Copy agent_actions to execution_log and set agent_actions to None
                    agent_output.execution_log = agent_output.agent_actions
                    agent_output.agent_actions = None
                # If "action" key is present, no changes are needed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse agent_actions: {e}")
            return agent_output

    return agent_output


def restructure_agent_llms(agent_llms: List) -> List[Dict]:
    """Transform AGENT_LLMS nested config to flat database format."""
    db_records = []
    for provider_group in agent_llms:
        for provider, models in provider_group.items():
            for model in models:
                db_records.append(
                    {
                        "llm_key": model.get("llm_key"),
                        "data": {
                            "name": model.get("name"),
                            "description": model.get("description"),
                            "model_name": model.get("model_name"),
                            "provider": model.get("provider"),
                            "integration_key": model.get("integration_key"),
                            "llm_config": model.get("llm_config", {}),
                            "metadata": model.get("metadata", {}),
                        },
                    }
                )
    return db_records


def get_human_reviewers_by_uuid(
    db: Session, raw_values: Optional[List[Any]]
) -> List[Dict[str, Any]]:
    """
    Parse user UUIDs from *raw_values*, load rows from ``users`` in one query,
    and return ``[{user_id, name, email_id}, ...]`` in the same order as
    successfully parsed UUIDs. Used for GET responses (human review
    recipients, alert recipients, etc.).

    Invalid / non-UUID entries are skipped. Returns ``[]`` if nothing
    could be parsed.
    """
    if not raw_values:
        return []
    uuids: List[UUID] = []
    for raw in raw_values:
        try:
            uuids.append(UUID(str(raw)))
        except (ValueError, TypeError):
            pass
    if not uuids:
        return []
    users_by_id = UserRepository(db).get_user_summaries_by_ids(uuids)
    return [
        (
            dict(user_summary)
            if (user_summary := users_by_id.get(uid))
            else {
                "user_id": str(uid),
                "name": None,
                "email_id": None,
            }
        )
        for uid in uuids
    ]
