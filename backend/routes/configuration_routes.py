# Custom libraries
from logger import configure_logging
from schemas.configuration_schema import (
    ConfigurationCreate,
    ConfigurationDetail,
    StorageMount,
    GrafanaAlertRequest,
)
from utils.common_utils import (
    get_storage_region,
    sanitize_data_store,
    get_human_reviewers_by_uuid,
)
from utils.notification import Notification
from utils.schema_utils import get_schema_db

# Default libraries
import json
import os
from typing import Literal, Optional

# Database modules
from repository.configuration_repository import ConfigurationRepository
from sqlalchemy.orm import Session

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Path


logger = configure_logging(__name__)

configuration_router = APIRouter(tags=["Configurations"])


@configuration_router.get(
    "/configurations", response_model=Optional[ConfigurationDetail]
)
def get_configuration(
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves the latest configuration information.
    On GET, ``platform_alert_recipients`` (user UUIDs) is expanded to
    ``{user_id, name, email_id}`` via ``get_user_summaries_by_ids`` (same
    pattern as ``agent_config.human_review_users`` on agents).
    """
    try:
        configuration_repository = ConfigurationRepository(db)
        configuration = configuration_repository.get_configuration()
        if not configuration:
            return None

        data = ConfigurationDetail.model_validate(configuration).model_dump()
        preferences = dict(data.get("preferences") or {})
        user_summaries = get_human_reviewers_by_uuid(
            db, preferences.get("platform_alert_recipients") or []
        )
        if user_summaries:
            preferences["platform_alert_recipients"] = user_summaries
        data["preferences"] = preferences
        return ConfigurationDetail.model_validate(data)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@configuration_router.get("/storage-mounts", response_model=StorageMount)
def get_storage_mounts():
    """
    Retrieves storage mount points from "STORAGE_MOUNT_POINTS" defined in the .env file.
    """
    try:
        environment_storage_mounts = os.getenv("STORAGE_MOUNT_POINTS")

        storage_mount_points = []
        if environment_storage_mounts:
            mounts = json.loads(environment_storage_mounts)
            # Handle double-encoded JSON
            if isinstance(mounts, str):
                mounts = json.loads(mounts)
            storage_mount_points = [
                mount["host"]
                for mount in mounts
                if isinstance(mount, dict) and "host" in mount
            ]

        return StorageMount(storage_mount_points=storage_mount_points)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred in get_storage_mounts: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@configuration_router.post("/configurations", response_model=ConfigurationDetail)
def create_configuration(
    configuration_data: ConfigurationCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates a new configuration.
    """
    try:

        configuration_repository = ConfigurationRepository(db)

        # Get only explicitly provided preferences (exclude fields with default values)
        new_preferences = configuration_data.preferences.model_dump(exclude_unset=True)

        # Check for existing configuration and merge preferences
        existing_config = configuration_repository.get_configuration()
        if existing_config and existing_config.preferences:
            # Merge: existing preferences + new preferences (new values override)
            merged_preferences = dict(existing_config.preferences)
            merged_preferences.update(new_preferences)
        else:
            merged_preferences = new_preferences

        configuration = configuration_repository.create_or_update_configuration(
            {"preferences": merged_preferences}
        )

        if configuration:
            logger.info(f"Configurations set successfully")
            return ConfigurationDetail.model_validate(configuration)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Configuration.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@configuration_router.post("/grafana-alerts")
def receive_grafana_alert(
    alert_payload: GrafanaAlertRequest = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Receives Grafana alert webhooks and forwards them to configured platform alert recipients.
    """
    try:
        # Get configuration and platform alert recipients
        configuration_repository = ConfigurationRepository(db)
        configuration = configuration_repository.get_configuration()

        if not configuration:
            raise HTTPException(
                status_code=404,
                detail="Configuration not found",
            )

        platform_alert_recipients = (
            configuration.preferences.get("platform_alert_recipients", [])
            if configuration.preferences
            else []
        )

        if not platform_alert_recipients:
            raise HTTPException(
                status_code=400,
                detail="No platform alert recipients configured",
            )

        # Send notification
        notification = Notification(db)
        email_sent = notification.send_platform_alert_notification(
            platform_alert_recipients, alert_payload.model_dump()
        )

        if not email_sent:
            raise HTTPException(
                status_code=500,
                detail="Failed to send alert notification email",
            )

        logger.info(
            f"Grafana alert notification sent successfully to {platform_alert_recipients}"
        )
        return {
            "status": "success",
            "message": "Alert notification sent successfully",
            "recipients": platform_alert_recipients,
        }

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred in receive_grafana_alert: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@configuration_router.post(
    "/assistant/status/{action}", response_model=ConfigurationDetail
)
def toggle_assistant(
    action: Literal["enable", "disable"] = Path(
        ..., description="Action to perform: 'enable' or 'disable'"
    ),
    db: Session = Depends(get_schema_db),
):
    """
    Enables or disables the assistant by updating the 'assistant_enabled' preference.
    Only updates this specific key without overwriting other configuration preferences.
    """
    try:
        configuration_repository = ConfigurationRepository(db)
        existing_config = configuration_repository.get_configuration()

        if not existing_config:
            raise HTTPException(
                status_code=404,
                detail="Configuration not found. Please create a configuration first.",
            )

        # Get existing preferences as a new dict copy (required for SQLAlchemy to detect changes)
        current_preferences = (
            dict(existing_config.preferences) if existing_config.preferences else {}
        )

        # Update only the assistant_enabled key
        current_preferences["assistant_enabled"] = action == "enable"

        # Update configuration with merged preferences
        configuration = configuration_repository.create_or_update_configuration(
            {"preferences": current_preferences}
        )

        if configuration:
            logger.info(
                f"Assistant {'enabled' if action == 'enable' else 'disabled'} successfully"
            )
            return ConfigurationDetail.model_validate(configuration)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to {action} assistant.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred in toggle_assistant: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
